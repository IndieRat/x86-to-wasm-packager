#!/usr/bin/env python3
"""Build a deterministic XWASM v0.6 PE32 graphics fixture."""

from pathlib import Path
import json
import struct
import argparse


IMAGE_BASE = 0x00400000
SECTION_RVA = 0x1000
SECTION_RAW = 0x200
SECTION_SIZE = 0x1000


def make_pe():
    b = bytearray(0x200 + 0x1000)
    b[0:2] = b"MZ"
    struct.pack_into("<I", b, 0x3C, 0x80)
    b[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", b, 0x84, 0x014C)
    struct.pack_into("<H", b, 0x86, 1)
    struct.pack_into("<H", b, 0x94, 0xE0)

    oh = 0x98
    struct.pack_into("<H", b, oh, 0x10B)
    struct.pack_into("<I", b, oh + 16, SECTION_RVA)
    struct.pack_into("<I", b, oh + 20, SECTION_RVA)
    struct.pack_into("<I", b, oh + 24, SECTION_RVA)
    struct.pack_into("<I", b, oh + 28, IMAGE_BASE)
    struct.pack_into("<I", b, oh + 32, 0x1000)
    struct.pack_into("<I", b, oh + 36, 0x200)
    struct.pack_into("<I", b, oh + 56, 0x2000)
    struct.pack_into("<I", b, oh + 60, 0x200)
    struct.pack_into("<I", b, oh + 92, 16)

    sh = oh + 0xE0
    b[sh:sh + 8] = b".text\0\0\0"
    struct.pack_into("<I", b, sh + 8, SECTION_SIZE)
    struct.pack_into("<I", b, sh + 12, SECTION_RVA)
    struct.pack_into("<I", b, sh + 16, SECTION_SIZE)
    struct.pack_into("<I", b, sh + 20, SECTION_RAW)
    struct.pack_into("<I", b, sh + 36, 0xE0000020)

    code = bytearray()

    # CreateWindowExA: 12 stdcall arguments, all NULL for the fixture.
    code.extend(b"\x6A\x00" * 12)
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1160))
    code.extend(b"\x89\xC3")                 # EBX = HWND

    # ShowWindow(hwnd, SW_SHOW)
    code.extend(b"\x6A\x01\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1164))

    # GetDC(hwnd)
    code.extend(b"\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1168))
    code.extend(b"\x89\xC3")                 # EBX = HDC

    # Rectangle(hdc, 120, 80, 520, 280)
    for value in (280, 520, 80, 120):
        code.extend(b"\x68" + struct.pack("<I", value))
    code.extend(b"\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1174))

    # SetPixel(hdc, 320, 180, RGB(255,0,0))
    for value in (0x000000FF, 180, 320):
        code.extend(b"\x68" + struct.pack("<I", value))
    code.extend(b"\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1170))

    # ReleaseDC(hwnd, hdc)
    code.extend(b"\x53\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x116C))
    code.extend(b"\xF4")                      # HLT

    b[SECTION_RAW:SECTION_RAW + len(code)] = code

    # Import directory:
    # USER32: CreateWindowExA, ShowWindow, GetDC, ReleaseDC
    # GDI32: SetPixel, Rectangle
    import_rva = 0x1100
    oft_rva = 0x1140
    iat_rva = 0x1160
    user_dll = 0x1180
    gdi_dll = 0x1190
    # Keep every IMAGE_IMPORT_BY_NAME record far enough apart for the\n    # two-byte hint plus the complete function name and NUL terminator.\n    # CreateWindowExA is 16 bytes including NUL, so the old 0x10 spacing\n    # overlapped its final bytes with the next record.\n    names = [0x11A0, 0x11C0, 0x11E0, 0x1200, 0x1220, 0x1240]
    funcs = [
        b"CreateWindowExA\0", b"ShowWindow\0", b"GetDC\0",
        b"ReleaseDC\0", b"SetPixel\0", b"Rectangle\0"
    ]

    base = SECTION_RAW
    struct.pack_into("<IIIII", b, base + 0x100, oft_rva, 0, 0, user_dll, iat_rva)
    struct.pack_into("<IIIII", b, base + 0x114, oft_rva + 0x14, 0, 0, gdi_dll, iat_rva + 0x10)
    struct.pack_into("<IIIII", b, base + 0x128, 0, 0, 0, 0, 0)

    struct.pack_into("<IIIII", b, base + 0x140, *names[:4], 0)
    struct.pack_into("<III", b, base + 0x154, names[4], names[5], 0)
    struct.pack_into("<IIII", b, base + 0x160, *names[:4])
    struct.pack_into("<II", b, base + 0x170, names[4], names[5])
    struct.pack_into("<II", b, base + 0x178, 0, 0)

    b[base + 0x180:base + 0x180 + len(b"USER32.dll\0")] = b"USER32.dll\0"
    b[base + 0x190:base + 0x190 + len(b"GDI32.dll\0")] = b"GDI32.dll\0"

    for rva, func in zip(names, funcs):
        off = base + (rva - SECTION_RVA)
        b[off:off + 2] = b"\0\0"
        b[off + 2:off + 2 + len(func)] = func

    struct.pack_into("<II", b, oh + 96 + 8, import_rva, 0x3C)
    return bytes(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    root = args.output
    payload = root / "resources" / "__x86__" / "payload.exe"
    runtime = root / "runtime.wasm"
    payload.parent.mkdir(parents=True, exist_ok=True)

    # The runtime is built separately; copy it into the package when present.
    runtime_source = Path("dist/x86-runtime-v0.6/runtime.wasm")
    if not runtime_source.exists():
        raise SystemExit("missing dist/x86-runtime-v0.6/runtime.wasm; build the runtime first")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(runtime_source.read_bytes())

    payload.write_bytes(make_pe())
    manifest = {
        "format": "xwasm-package",
        "format_version": 1,
        "name": "XWASM-X86-Graphics-Test",
        "architecture": "x86",
        "runtime_kind": "x86-compatibility",
        "runtime": "runtime.wasm",
        "abi": "xwasm.host/1",
        "resource_root": "resources/",
        "payload": "resources/__x86__/payload.exe",
        "payload_format": "PE32",
        "payload_architecture": "i386",
        "entry": {"init": "xwasm_init", "tick": "xwasm_tick", "shutdown": "xwasm_shutdown"},
        "bundled_dlls": ["USER32.dll", "GDI32.dll"],
        "execution_status": "v0.6_graphics_fixture"
    }
    (root / "manifest.xwasm.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(root)


if __name__ == "__main__":
    main()
