#!/usr/bin/env python3
"""Build a deterministic XWASM v0.7 window/message/input/audio fixture."""
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

    # CPU compatibility self-test. EBP receives XOPS when the richer
    # arithmetic/logic/shift/IMUL/MOVZX/MOVSX/branch operations all pass.
    # This runs entirely inside the guest before entering the message loop.
    code.extend(b"\xB8" + struct.pack("<I", 3))
    code.extend(b"\xB9" + struct.pack("<I", 5))
    code.extend(b"\x0F\xAF\xC1")
    code.extend(b"\xC1\xE0\x01")
    code.extend(b"\x83\xC0\x02")
    code.extend(b"\xBA" + struct.pack("<I", 0xF0))
    code.extend(b"\x0B\xD0")
    code.extend(b"\x23\xD0")
    code.extend(b"\x2B\xD0")
    code.extend(b"\x83\xFA\x00")
    jne_logic = len(code)
    code.extend(b"\x75\x00")
    code.extend(b"\xB8" + struct.pack("<I", 0x80))
    code.extend(b"\x0F\xBE\xC8")
    code.extend(b"\x83\xF9\x80")
    jne_movsx = len(code)
    code.extend(b"\x75\x00")
    code.extend(b"\x0F\xB6\xC8")
    code.extend(b"\x83\xF9\x80")
    jne_movzx = len(code)
    code.extend(b"\x75\x00")
    code.extend(b"\xBD" + struct.pack("<I", 0x584F5053))
    rich_done_jump = len(code)
    code.extend(b"\xEB\x00")
    rich_fail = len(code)
    code.extend(b"\x31\xED")
    rich_done = len(code)
    code[jne_logic + 1] = (rich_fail - (jne_logic + 2)) & 0xFF
    code[jne_movsx + 1] = (rich_fail - (jne_movsx + 2)) & 0xFF
    code[jne_movzx + 1] = (rich_fail - (jne_movzx + 2)) & 0xFF
    code[rich_done_jump + 1] = (rich_done - (rich_done_jump + 2)) & 0xFF

    # Create a real Win32-style client surface: exstyle, class, title, style,
    # x, y, width, height, parent, menu, instance, param.
    args = [0, 0, 0, 0x10000000, 0, 0, 640, 360, 0, 0, 0, 0]
    for value in reversed(args):
        code.extend(b"\x68" + struct.pack("<I", value))
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1390))
    code.extend(b"\x89\xC6")                 # ESI = HWND
    code.extend(b"\x6A\x01\x56")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1394))

    # GetDC(hwnd), draw a surface marker, then release the DC.
    code.extend(b"\x56")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x1898))
    code.extend(b"\x89\xC3")                 # EBX = HDC
    for value in (280, 520, 80, 120):
        code.extend(b"\x68" + struct.pack("<I", value))
    code.extend(b"\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x18BC))
    for value in (0x000000FF, 180, 320):
        code.extend(b"\x68" + struct.pack("<I", value))
    code.extend(b"\x53")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x18B8))
    code.extend(b"\x53\x56")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x189C))

    # KERNEL32!Beep(660, 120): browser Web Audio proof.
    code.extend(b"\x68" + struct.pack("<I", 120))
    code.extend(b"\x68" + struct.pack("<I", 660))
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x18C4))

    # Proper persistent Win32-style message loop.
    # PeekMessageA is polled continuously; each browser event wakes the loop,
    # then TranslateMessage/DispatchMessageA consume the MSG.
    code.extend(b"\xBF" + struct.pack("<I", 0x00800000))  # EDI = MSG*
    loop = len(code)
    for value in (1, 0, 0, 0):
        code.extend(b"\x6A" + struct.pack("<B", value))
    code.extend(b"\x57")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x18A0))
    code.extend(b"\x85\xC0")                 # TEST EAX,EAX
    jz = len(code)
    code.extend(b"\x74\x00")
    code.extend(b"\x57")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x18A4))
    code.extend(b"\x57")
    code.extend(b"\xFF\x15" + struct.pack("<I", IMAGE_BASE + 0x18A8))
    back = len(code)
    code.extend(b"\xEB\x00")
    code[jz + 1] = (loop - (jz + 2)) & 0xFF
    code[back + 1] = (loop - (back + 2)) & 0xFF

    b[SECTION_RAW:SECTION_RAW + len(code)] = code

    import_rva = 0x1800
    user_oft_rva = 0x1850
    gdi_oft_rva = 0x1878
    kernel_oft_rva = 0x1884
    user_iat_rva = 0x1890
    gdi_iat_rva = 0x18B8
    kernel_iat_rva = 0x18C4
    user_dll = 0x18D0
    gdi_dll = 0x18E0
    kernel_dll = 0x18F0
    names = [0x1900 + i * 0x20 for i in range(12)]
    funcs = [
        b"CreateWindowExA\0", b"ShowWindow\0", b"GetDC\0", b"ReleaseDC\0",
        b"SetPixel\0", b"Rectangle\0",
        b"Beep\0",
        b"PeekMessageA\0", b"TranslateMessage\0", b"DispatchMessageA\0",
        b"GetMessageA\0", b"DefWindowProcA\0"
    ]

    base = SECTION_RAW
    # Keep the import descriptors/data above the executable code so the
    # machine-code test can grow without corrupting its own PE metadata.
    b[base + (import_rva - SECTION_RVA):base + (import_rva - SECTION_RVA) + 0x50] = b"\0" * 0x50
    # USER32: CreateWindowExA, ShowWindow, GetDC, ReleaseDC, and five
    # message-loop functions.
    struct.pack_into("<IIIII", b, base + 0x100,
                     user_oft_rva, 0, 0, user_dll, user_iat_rva)
    # GDI32: SetPixel and Rectangle.
    struct.pack_into("<IIIII", b, base + 0x114,
                     gdi_oft_rva, 0, 0, gdi_dll, gdi_iat_rva)
    # KERNEL32: Beep.
    struct.pack_into("<IIIII", b, base + 0x128,
                     kernel_oft_rva, 0, 0, kernel_dll, kernel_iat_rva)
    # Null import descriptor terminator.
    struct.pack_into("<IIIII", b, base + (import_rva - SECTION_RVA) + 0x3C, 0, 0, 0, 0, 0)

    user_names = [names[0], names[1], names[2], names[3],
                  names[7], names[8], names[9], names[10], names[11]]
    gdi_names = [names[4], names[5]]

    # USER32 OFT/IAT.
    for i, rva in enumerate(user_names):
        struct.pack_into("<I", b, base + (user_oft_rva - SECTION_RVA) + i * 4, rva)
        struct.pack_into("<I", b, base + (user_iat_rva - SECTION_RVA) + i * 4, rva)
    # GDI32 OFT/IAT.
    for i, rva in enumerate(gdi_names):
        struct.pack_into("<I", b, base + (gdi_oft_rva - SECTION_RVA) + i * 4, rva)
        struct.pack_into("<I", b, base + (gdi_iat_rva - SECTION_RVA) + i * 4, rva)
    # KERNEL32 OFT/IAT.
    struct.pack_into("<I", b, base + (kernel_oft_rva - SECTION_RVA), names[6])
    struct.pack_into("<I", b, base + (kernel_iat_rva - SECTION_RVA), names[6])

    for rva, dll in (
        (user_dll, b"USER32.dll\0"),
        (gdi_dll, b"GDI32.dll\0"),
        (kernel_dll, b"KERNEL32.dll\0"),
    ):
        off = base + (rva - SECTION_RVA)
        b[off:off + len(dll)] = dll
    for rva, func in zip(names, funcs):
        off = base + (rva - SECTION_RVA)
        b[off:off + 2] = b"\0\0"
        b[off + 2:off + 2 + len(func)] = func

    # Data directory import RVA/size: three descriptors plus terminator.
    struct.pack_into("<II", b, oh + 96 + 8, import_rva, 0x50)
    return bytes(b)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.output
    payload = root / "resources" / "__x86__" / "payload.exe"
    runtime = root / "runtime.wasm"
    payload.parent.mkdir(parents=True, exist_ok=True)

    runtime_source = Path("dist/x86-runtime-v0.7/runtime.wasm")
    if not runtime_source.exists():
        raise SystemExit("missing dist/x86-runtime-v0.7/runtime.wasm; build the runtime first")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(runtime_source.read_bytes())
    payload.write_bytes(make_pe())

    manifest = {
        "format": "xwasm-package",
        "format_version": 1,
        "name": "XWASM-X86-Window-Input-Audio-Test",
        "architecture": "x86",
        "runtime_kind": "x86-compatibility",
        "runtime": "runtime.wasm",
        "abi": "xwasm.host/1",
        "resource_root": "resources/",
        "payload": "resources/__x86__/payload.exe",
        "payload_format": "PE32",
        "payload_architecture": "i386",
        "entry": {"init": "xwasm_init", "tick": "xwasm_tick", "shutdown": "xwasm_shutdown"},
        "bundled_dlls": ["USER32.dll", "GDI32.dll", "KERNEL32.dll"],
        "execution_status": "v0.7_compatibility_fixture",
        "test_suite": {
            "name": "XWASM v0.7 Compatibility Foundation",
            "tests": [
                "PE32 loading and image mapping",
                "x86 import resolution",
                "USER32 window creation and client surface",
                "GDI32 drawing bridge",
                "Win32 keyboard messages",
                "Win32 mouse move and button messages",
                "persistent PeekMessageA/DispatchMessageA loop",
                "KERNEL32 Beep audio bridge",
                "x86 arithmetic and logic operations",
                "x86 shifts and IMUL",
                "x86 MOVZX/MOVSX",
                "x86 conditional branches"
            ]
        }
    }
    (root / "manifest.xwasm.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(root)

if __name__ == "__main__":
    main()
