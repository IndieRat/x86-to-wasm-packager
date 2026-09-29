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

    # Deterministic CPU program. Keep the CALL displacement derived from
    # the actual instruction and target positions so this fixture cannot
    # silently break when instructions are added or removed.
    code = bytearray((
        # C0: cdecl-style stack argument + frame + direct/indirect callbacks.
        0x6A, 0x2A,                                # PUSH 42 (cdecl argument)
        0x55,                                      # PUSH EBP
        0x89, 0xE5,                                # MOV EBP,ESP
        0xE8, 0x00, 0x00, 0x00, 0x00,             # CALL helper (patched below)
        0x83, 0xC4, 0x04,                          # ADD ESP,4 (caller cleanup)
        0x6A, 0x2A,                                # PUSH 42 (second cdecl callback argument)
        0xB8, 0x00, 0x00, 0x40, 0x00,             # MOV EAX,helper address (patched below)
        0xFF, 0xD0,                                # CALL EAX (indirect callback)
        0x83, 0xC4, 0x04,                          # ADD ESP,4 (caller cleanup)
        0x89, 0xC6,                                # MOV ESI,EAX (preserve C0 result)
        0xC9,                                      # LEAVE
        0xB8, 0x05, 0x00, 0x00, 0x00,             # MOV EAX,5
        0xBB, 0x00, 0x08, 0x40, 0x00,             # MOV EBX,0x00400800
        0x89, 0x03,                                # MOV [EBX],EAX
        0x8B, 0x0B,                                # MOV ECX,[EBX]
        0x8B, 0xC1,                                # MOV EAX,ECX
        0x3D, 0x05, 0x00, 0x00, 0x00,             # CMP EAX,5
        0x74, 0x05,                                # JE skip next MOV
        0xBB, 0xEF, 0xBE, 0xAD, 0xDE,             # MOV EBX,0xDEADBEEF
        0xE8, 0x00, 0x00, 0x00, 0x00,             # CALL target (patched below)
        0x6A, 0x04,                                # PUSH PAGE_READWRITE
        0x68, 0x00, 0x30, 0x00, 0x00,             # PUSH MEM_COMMIT|MEM_RESERVE
        0x68, 0x00, 0x10, 0x00, 0x00,             # PUSH dwSize=0x1000
        0x6A, 0x00,                                # PUSH lpAddress=NULL
        0xFF, 0x15, 0x64, 0x11, 0x40, 0x00,       # CALL [0x00401164] -> KERNEL32!VirtualAlloc
        0x89, 0xC3,                                # MOV EBX,EAX (retain allocation)
        0xB9, 0x00, 0x10, 0x40, 0x00,             # MOV ECX, hello-string address (patched below)
        0xBA, 0x12, 0x00, 0x00, 0x00,             # MOV EDX, 18
        0xFF, 0x15, 0x60, 0x11, 0x40, 0x00,       # CALL [0x00401160] -> XWASMHOST!xwasm_log
        0x53,                                      # PUSH EBX (lpAddress)
        0x6A, 0x00,                                # PUSH dwSize=0 for MEM_RELEASE
        0x68, 0x00, 0x80, 0x00, 0x00,             # PUSH MEM_RELEASE
        0xFF, 0x15, 0x68, 0x11, 0x40, 0x00,       # CALL [0x00401168] -> KERNEL32!VirtualFree
        0xFF, 0x15, 0x6C, 0x11, 0x40, 0x00,       # CALL [0x0040116C] -> KERNEL32!GetTickCount
        0xF4,                                      # HLT
    ))
    call_placeholders = []
    search_from = 0
    marker = b"\xE8\x00\x00\x00\x00"
    while True:
        found = code.find(marker, search_from)
        if found < 0:
            break
        call_placeholders.append(found)
        search_from = found + len(marker)
    if not call_placeholders:
        raise AssertionError("synthetic PE CALL placeholder is missing")
    code.extend(b"\x00" * 16)
    call_target_file_offset = len(code)
    code.extend((0x55,                             # PUSH EBP
                 0x89, 0xE5,                       # MOV EBP,ESP
                 0x8B, 0x45, 0x08,                 # MOV EAX,[EBP+8] (argument)
                 0xC9,                             # LEAVE
                 0xC3))                            # RET

    hello_string_file_offset = len(code)
    code.extend(b"VirtualAlloc PASS!")
    hello_string_rva = 0x1000 + hello_string_file_offset
    hello_mov = code.find(b"\xB9\x00\x10\x40\x00")
    if hello_mov < 0:
        raise AssertionError("hello-string MOV ECX placeholder is missing")
    struct.pack_into("<I", code, hello_mov + 1, 0x00400000 + hello_string_rva)

    for call_instruction_file_offset in call_placeholders:
        call_rel = call_target_file_offset - (call_instruction_file_offset + 5)
        code[call_instruction_file_offset] = 0xE8
        code[call_instruction_file_offset + 1:call_instruction_file_offset + 5] = int(call_rel).to_bytes(4, "little", signed=True)

    helper_mov = code.find(b"\xB8\x00\x00\x40\x00")
    if helper_mov < 0:
        raise AssertionError("C0 indirect-call target placeholder is missing")
    helper_address = 0x00400000 + 0x1000 + call_target_file_offset
    struct.pack_into("<I", code, helper_mov + 1, helper_address)

    call_instruction_file_offset = call_placeholders[0]
    decoded_rel = int.from_bytes(
        code[call_instruction_file_offset + 1:call_instruction_file_offset + 5],
        "little",
        signed=True,
    )
    decoded_target = call_instruction_file_offset + 5 + decoded_rel
    assert decoded_target == call_target_file_offset, (
        f"CALL generated wrong target: expected 0x{call_target_file_offset:X}, "
        f"got 0x{decoded_target:X}"
    )
    assert code[decoded_target:decoded_target + 3] == b"\x55\x89\xE5", (
        f"CALL target does not begin with PUSH EBP; MOV EBP,ESP: "
        f"target=0x{decoded_target:X}, bytes={code[decoded_target:decoded_target + 3].hex()}"
    )
    assert code[decoded_target + 3:decoded_target + 6] == b"\x8B\x45\x08", (
        f"CALL target does not load [EBP+8]: "
        f"target=0x{decoded_target:X}, bytes={code[decoded_target + 3:decoded_target + 6].hex()}"
    )
    assert code[decoded_target + 6:decoded_target + 8] == b"\xC9\xC3", (
        f"CALL target does not end with LEAVE; RET: "
        f"target=0x{decoded_target:X}, bytes={code[decoded_target + 6:decoded_target + 8].hex()}"
    )
    # Minimal PE import directory for KERNEL32.dll!GetTickCount.
    # The runtime resolves this through its builtin Win32 seed table and
    # patches the IAT with an emulated API address.
    import_rva = 0x1100
    oft_rva = 0x1140
    iat_rva = 0x1160
    dll1_rva = 0x1180
    dll2_rva = 0x1190
    name1_rva = 0x11A0
    name2_rva = 0x11B0
    name3_rva = 0x11C0
    name4_rva = 0x11D0
    name5_rva = 0x11E0
    # XWASMHOST.dll!xwasm_log
    struct.pack_into("<IIIII", b, headers + 0x100, oft_rva, 0, 0, dll1_rva, iat_rva)
    # KERNEL32.dll!VirtualAlloc, VirtualFree, GetTickCount
    struct.pack_into("<IIIII", b, headers + 0x114, oft_rva + 8, 0, 0, dll2_rva, iat_rva + 4)
    struct.pack_into("<IIIII", b, headers + 0x128, 0, 0, 0, 0, 0)
    struct.pack_into("<II", b, headers + 0x140, name1_rva, 0)
    struct.pack_into("<IIII", b, headers + 0x148, name2_rva, name3_rva, name4_rva, 0)
    struct.pack_into("<IIII", b, headers + 0x160, name1_rva, name2_rva, name3_rva, name4_rva)
    b[headers + 0x180:headers + 0x180 + len(b"XWASMHOST.dll\0")] = b"XWASMHOST.dll\0"
    b[headers + 0x190:headers + 0x190 + len(b"KERNEL32.dll\0")] = b"KERNEL32.dll\0"
    b[headers + 0x1A0:headers + 0x1A0 + 2] = b"\0\0"
    b[headers + 0x1A2:headers + 0x1A2 + len(b"xwasm_log\0")] = b"xwasm_log\0"
    b[headers + 0x1B0:headers + 0x1B0 + 2] = b"\0\0"
    b[headers + 0x1B2:headers + 0x1B2 + len(b"VirtualAlloc\0")] = b"VirtualAlloc\0"
    b[headers + 0x1C0:headers + 0x1C0 + 2] = b"\0\0"
    b[headers + 0x1C2:headers + 0x1C2 + len(b"VirtualFree\0")] = b"VirtualFree\0"
    b[headers + 0x1D0:headers + 0x1D0 + 2] = b"\0\0"
    b[headers + 0x1D2:headers + 0x1D2 + len(b"GetTickCount\0")] = b"GetTickCount\0"

    # Import directory RVA/size.
    struct.pack_into("<II", b, oh + 96 + 8, import_rva, 0x3C)

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

    # Re-read the packaged fixture so the diagnostic describes the exact
    # bytes that were actually written to payload.exe.
    pe_off = struct.unpack_from("<I", payload, 0x3C)[0]
    optional_size = struct.unpack_from("<H", payload, pe_off + 20)[0]
    section = pe_off + 24 + optional_size
    headers = struct.unpack_from("<I", payload, section + 20)[0]
    raw_size = struct.unpack_from("<I", payload, section + 16)[0]
    code = payload[headers:headers + raw_size]

    call_instruction_file_offset = code.find(b"\xE8")
    if call_instruction_file_offset < 0:
        raise SystemExit("packaged synthetic payload has no CALL rel32 instruction")
    decoded_rel = int.from_bytes(
        code[call_instruction_file_offset + 1:call_instruction_file_offset + 5],
        "little",
        signed=True,
    )
    decoded_target = call_instruction_file_offset + 5 + decoded_rel
    if not (0 <= decoded_target < len(code)):
        raise SystemExit("packaged synthetic CALL target is outside the section")
    if code[decoded_target] != 0x8B:
        raise SystemExit(
            f"packaged synthetic CALL target opcode is 0x{code[decoded_target]:02X}, "
            "expected 0x8B"
        )

    print(
        f"Fixture CALL: from=0x{call_instruction_file_offset:X} "
        f"rel={decoded_rel:+d} target=0x{decoded_target:X} "
        f"opcode=0x{code[decoded_target]:02X}"
    )
    print("Synthetic PE32 checks: MZ=OK PE=i386 PE32=OK ModRM=OK imports=XWASMHOST!xwasm_log,KERNEL32!VirtualAlloc/VirtualFree/GetTickCount")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
