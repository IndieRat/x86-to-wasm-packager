#!/usr/bin/env python3
"""Build a freestanding C++ PE32 fixture and package it as XPL."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a minimal freestanding C++ XPL fixture.")
    ap.add_argument("--clang", required=True)
    ap.add_argument("--lld-link", required=True)
    ap.add_argument("--output", type=Path, required=True, help="fixture output directory")
    a = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    src = root / "tests/fixtures/cpp_runtime_fixture.cpp"
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    exe = out / "cpp_fixture.exe"
    obj = out / "cpp_fixture.obj"

    subprocess.run([
        a.clang, "--target=i686-pc-windows-msvc", "-O0", "-ffreestanding",
        "-fno-builtin", "-fno-stack-protector", "-mno-stack-arg-probe",
        "-fno-exceptions", "-fno-rtti", "-std=c++11", "-nostdinc++",
        "-c", str(src), "-o", str(obj)
    ], check=True)

    subprocess.run([
        a.lld_link, "/machine:x86", "/subsystem:console", "/entry:main",
        "/nodefaultlib", "/base:0x400000", "/fixed", f"/out:{exe}", str(obj)
    ], check=True)

    obj.unlink(missing_ok=True)

    data = exe.read_bytes()
    if data[:2] != b"MZ":
        raise SystemExit("C++ fixture is not PE32")

    pe = int.from_bytes(data[0x3C:0x40], "little")
    signature_ok = data[pe:pe + 4] == bytes((0x50, 0x45, 0x00, 0x00))
    machine_ok = int.from_bytes(data[pe + 4:pe + 6], "little") == 0x14C
    optional_magic_ok = int.from_bytes(data[pe + 24:pe + 26], "little") == 0x10B

    if not (signature_ok and machine_ok and optional_magic_ok):
        raise SystemExit("C++ fixture is not i386 PE32")

    xpl = out / "cpp_fixture.xpl"
    subprocess.run([
        sys.executable, str(root / "tool/xwasm_pack_xpl.py"),
        str(exe), "--output", str(xpl)
    ], check=True)
    exe.unlink()

    print(f"Created C++ XPL fixture: {xpl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
