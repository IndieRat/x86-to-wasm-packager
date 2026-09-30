#!/usr/bin/env python3
"""Build the freestanding i386 C fixture that exercises baseline x87 code generation."""
from __future__ import annotations
import argparse
import shutil
import subprocess
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--clang",default=shutil.which("clang"))
    ap.add_argument("--lld-link",default=shutil.which("lld-link"))
    args=ap.parse_args()
    if not args.clang: raise SystemExit("clang is required; pass --clang PATH")
    if not args.lld_link: raise SystemExit("lld-link is required; pass --lld-link PATH")
    root=Path(__file__).resolve().parents[1]
    source=root/"tests"/"fixtures"/"x87_float_fixture.c"
    out=args.output.resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    obj=out.with_suffix(".obj")
    compile_cmd=[args.clang,"--target=i686-pc-windows-msvc","-ffreestanding","-fno-builtin","-fno-stack-protector","-mno-stack-arg-probe","-mno-sse","-mno-sse2","-mfpmath=387","-O0","-c",str(source),"-o",str(obj)]
    link_cmd=[args.lld_link,"/machine:x86","/subsystem:console","/entry:main","/base:0x400000","/fixed","/nodefaultlib","/out:"+str(out),str(obj)]
    print("Compiling x87 fixture:"," ".join(compile_cmd)); subprocess.run(compile_cmd,check=True)
    print("Linking x87 PE32:"," ".join(link_cmd)); subprocess.run(link_cmd,check=True); obj.unlink(missing_ok=True)
    data=out.read_bytes();
    if data[:2]!=b"MZ": raise SystemExit("x87 output is not an MZ executable")
    pe=int.from_bytes(data[0x3C:0x40],"little")
    if data[pe:pe+4]!=b"PE\\0\\0": raise SystemExit("x87 output is missing the PE signature")
    if int.from_bytes(data[pe+4:pe+6],"little")!=0x14C: raise SystemExit("x87 output is not i386")
    if int.from_bytes(data[pe+24:pe+26],"little")!=0x10B: raise SystemExit("x87 output is not PE32")
    print(f"Created x87 PE32 fixture: {out}"); print(f"Size: {len(data)} bytes"); return 0
if __name__=="__main__": raise SystemExit(main())
