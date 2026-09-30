#!/usr/bin/env python3
"""Build the freestanding i386 C fixture for additional integer compiler coverage."""
from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--clang",default=shutil.which("clang")); ap.add_argument("--lld-link",default=shutil.which("lld-link")); args=ap.parse_args()
    if not args.clang: raise SystemExit("clang is required; pass --clang PATH")
    if not args.lld_link: raise SystemExit("lld-link is required; pass --lld-link PATH")
    root=Path(__file__).resolve().parents[1]; source=root/"tests"/"fixtures"/"integer_coverage_fixture.c"; out=args.output.resolve(); out.parent.mkdir(parents=True,exist_ok=True); obj=out.with_suffix(".obj")
    cc=[args.clang,"--target=i686-pc-windows-msvc","-ffreestanding","-fno-builtin","-fno-stack-protector","-mno-stack-arg-probe","-O1","-c",str(source),"-o",str(obj)]
    ld=[args.lld_link,"/machine:x86","/subsystem:console","/entry:main","/base:0x400000","/fixed","/nodefaultlib","/out:"+str(out),str(obj)]
    print("Compiling integer fixture:"," ".join(cc)); subprocess.run(cc,check=True); print("Linking integer PE32:"," ".join(ld)); subprocess.run(ld,check=True); obj.unlink(missing_ok=True)
    data=out.read_bytes(); pe=int.from_bytes(data[0x3C:0x40],"little")
    if data[:2]!=b"MZ" or data[pe:pe+4]!=b"PE\\0\\0" or int.from_bytes(data[pe+4:pe+6],"little")!=0x14C or int.from_bytes(data[pe+24:pe+26],"little")!=0x10B: raise SystemExit("integer fixture is not PE32/i386")
    print(f"Created integer coverage PE32 fixture: {out}"); print(f"Size: {len(data)} bytes"); return 0
if __name__=="__main__": raise SystemExit(main())
