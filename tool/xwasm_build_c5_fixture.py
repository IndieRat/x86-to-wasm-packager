#!/usr/bin/env python3
"""Build the C5 fixture and package its PE32 payload as XPL."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True, help="fixture output directory")
    ap.add_argument("--clang", default=shutil.which("clang"))
    ap.add_argument("--lld-link", default=shutil.which("lld-link"))
    args = ap.parse_args()
    if not args.clang:
        raise SystemExit("clang is required; pass --clang PATH")
    if not args.lld_link:
        raise SystemExit("lld-link is required; pass --lld-link PATH")

    root = Path(__file__).resolve().parents[1]
    source = root / "tests" / "fixtures" / "c5_game_fixture.c"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = out / "c5_fixture.exe"
    obj = out / "c5_fixture.obj"

    compile_cmd = [args.clang, "--target=i686-pc-windows-msvc", "-ffreestanding",
                   "-fno-builtin", "-fno-stack-protector", "-mno-stack-arg-probe",
                   "-O0", "-c", str(source), "-o", str(obj)]
    link_cmd = [args.lld_link, "/machine:x86", "/subsystem:console", "/entry:main",
                "/base:0x400000", "/fixed", "/nodefaultlib", "/out:" + str(exe), str(obj)]
    print("Compiling C5 fixture:", " ".join(compile_cmd))
    subprocess.run(compile_cmd, check=True)
    print("Linking C5 PE32:", " ".join(link_cmd))
    subprocess.run(link_cmd, check=True)
    obj.unlink(missing_ok=True)

    data = exe.read_bytes()
    pe_off = int.from_bytes(data[0x3C:0x40], "little")
    if data[:2] != b"MZ" or data[pe_off:pe_off + 4] != b"PE\0\0" or        int.from_bytes(data[pe_off + 4:pe_off + 6], "little") != 0x14C or        int.from_bytes(data[pe_off + 24:pe_off + 26], "little") != 0x10B:
        raise SystemExit("C5 output is not an i386 PE32 executable")

    pack = root / "tool" / "xwasm_pack_xpl.py"
    xpl = out / "c5_fixture.xpl"
    subprocess.run([sys.executable, str(pack), str(exe), "--output", str(xpl)], check=True)
    exe.unlink()
    print(f"Created C5 XPL fixture: {xpl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
