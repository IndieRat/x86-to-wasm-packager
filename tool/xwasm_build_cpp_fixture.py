#!/usr/bin/env python3
"""Build a freestanding C++ PE32 fixture without linking a host C++ runtime."""
from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path

def main()->int:
    ap=argparse.ArgumentParser(description="Build a minimal freestanding C++ PE32 fixture.")
    ap.add_argument("--clang",required=True); ap.add_argument("--lld-link",required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    src=root/"tests/fixtures/cpp_runtime_fixture.cpp"; out=a.output.resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    obj=out.with_suffix(".obj")
    subprocess.run([a.clang,"--target=i386-pc-windows-msvc","-O0","-ffreestanding","-fno-exceptions","-fno-rtti","-fno-builtin","-nostdinc++","-c",str(src),"-o",str(obj)],check=True)
    subprocess.run([a.lld_link,"/subsystem:console","/entry:main","/nodefaultlib",f"/out:{out}",str(obj)],check=True)
    if out.read_bytes()[:2]!=b"MZ": raise SystemExit("C++ fixture is not PE32")
    print(f"Created C++ PE32 fixture: {out}")
    return 0
if __name__=="__main__": raise SystemExit(main())
