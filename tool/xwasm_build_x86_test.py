#!/usr/bin/env python3
"""Build a deterministic XWASM x86 runtime test package.

The package contains the real x86 runtime.wasm plus a tiny synthetic PE32
payload. It is deliberately not a Windows game; it exercises packaging,
manifest validation, PE loading, and the browser runner's staging path.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
import struct


def u16(v: int) -> bytes:
    return struct.pack("<H", v)


def u32(v: int) -> bytes:
    return struct.pack("<I", v)


def make_test_pe() -> bytes:
    pe_off = 0x80
    file_align = 0x200
    section_align = 0x1000
    headers = 0x200
    text_raw_size = 0x200
    image_size = 0x2000

    b = bytearray(headers + text_raw_size)
    b[0:2] = b"MZ"
    b[0x3C:0x40] = u32(pe_off)
    b[pe_off:pe_off + 4] = b"PE\0\0"

    fh = pe_off + 4
    b[fh:fh + 2] = u16(0x14C)
    b[fh + 2:fh + 4] = u16(1)
    b[fh + 16:fh + 18] = u16(0xE0)
    b[fh + 18:fh + 20] = u16(0x010F)

    oh = fh + 20
    b[oh:oh + 2] = u16(0x10B)
    b[oh + 16:oh + 20] = u32(0x1000)
    b[oh + 28:oh + 32] = u32(0x00400000)
    b[oh + 32:oh + 36] = u32(section_align)
    b[oh + 36:oh + 40] = u32(file_align)
    b[oh + 56:oh + 60] = u32(image_size)
    b[oh + 60:oh + 64] = u32(headers)
    b[oh + 68:oh + 70] = u16(3)
    b[oh + 92:oh + 96] = u32(16)

    sh = oh + 0xE0
    b[sh:sh + 8] = b".text\0\0\0"
    b[sh + 8:sh + 12] = u32(0x1000)
    b[sh + 12:sh + 16] = u32(0x1000)
    b[sh + 16:sh + 20] = u32(text_raw_size)
    b[sh + 20:sh + 24] = u32(headers)

    # Deterministic CPU program:
    #   MOV EAX,5
    #   MOV EBX,0x00400800
    #   MOV [EBX],EAX
    #   MOV ECX,[EBX]
    #   MOV EAX,ECX
    #   CMP EAX,5
    #   JE  +5             ; skip the failing EBX assignment
    #   MOV EBX,0xDEADBEEF
    #   CALL +0x13         ; call function at offset 0x32
    #   HLT
    #   padding
    # function:
    #   MOV EAX,42
    #   RET
    code = bytes((
        0xB8, 0x05, 0x00, 0x00, 0x00,
        0xBB, 0x00, 0x08, 0x40, 0x00,
        0x89, 0x03,
        0x8B, 0x0B,
        0x8B, 0xC1,
        0x3D, 0x05, 0x00, 0x00, 0x00,
        0x74, 0x05,
        0xBB, 0xEF, 0xBE, 0xAD, 0xDE,
        0xE8, 0x13, 0x00, 0x00, 0x00,
        0xF4,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0xB8, 0x2A, 0x00, 0x00, 0x00,
        0xC3,
    ))
    b[headers:headers + len(code)] = code

    payload = bytes(b)

    # Keep the synthetic fixture self-checking. If this ever changes, fail
    # before packaging so the browser cannot silently test a stale/bad PE.
    if payload[:2] != b"MZ":
        raise AssertionError("synthetic PE missing MZ signature")
    if struct.unpack_from("<I", payload, pe_off)[0] != 0x4550:
        raise AssertionError("synthetic PE missing PE signature")
    if struct.unpack_from("<H", payload, pe_off + 4)[0] != 0x14C:
        raise AssertionError("synthetic PE machine is not i386")
    if struct.unpack_from("<H", payload, pe_off + 24)[0] != 0x10B:
        raise AssertionError("synthetic PE optional header is not PE32")
    if struct.unpack_from("<H", payload, pe_off + 20)[0] != 0xE0:
        raise AssertionError("synthetic PE optional header size is not 0xE0")

    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the deterministic XWASM x86 runtime test package.")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--clang", default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        game = Path(td) / "XWASM-X86-Test"
        game.mkdir()
        (game / "Test.exe").write_bytes(make_test_pe())

        runtime = Path(td) / "runtime.wasm"
        build = root / "tool" / "xwasm_build_x86_runtime.py"
        cmd = ["python", str(build), "--output", str(runtime)]
        if args.clang:
            cmd += ["--clang", args.clang]
        subprocess.run(cmd, check=True)

        pack = root / "tool" / "xwasm_pack_x86.py"
        subprocess.run([
            "python", str(pack), str(game),
            "--output", str(out),
            "--exe", "Test.exe",
            "--runtime", str(runtime),
        ], check=True)

    manifest = json.loads((out / "manifest.xwasm.json").read_text(encoding="utf-8"))
    if manifest.get("architecture") != "x86":
        raise SystemExit("test package manifest is not architecture=x86")
    if manifest.get("runtime") != "runtime.wasm":
        raise SystemExit("test package did not bundle runtime.wasm")
    if manifest.get("payload") != "resources/__x86__/payload.exe":
        raise SystemExit("test package payload path is incorrect")

    payload = (out / "resources" / "__x86__" / "payload.exe").read_bytes()
    if struct.unpack_from("<H", payload, 0x80 + 24)[0] != 0x10B:
        raise SystemExit("packaged synthetic payload is not PE32; rebuild the package")
    if payload[:2] != b"MZ":
        raise SystemExit("packaged synthetic payload is not MZ")

    print(f"Created deterministic XWASM x86 test package: {out}")
    print("Synthetic PE32 checks: MZ=OK PE=i386 PE32=OK ModRM=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
