#!/usr/bin/env python3
"""Build the scalar SSE/SSE2 freestanding C integration fixture as PE32."""
from __future__ import annotations
import argparse,shutil,subprocess
from pathlib import Path

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True);ap.add_argument("--clang",default=shutil.which("clang"));ap.add_argument("--lld-link",default=shutil.which("lld-link"));a=ap.parse_args()
 if not a.clang: raise SystemExit("clang is required; pass --clang PATH")
 if not a.lld_link: raise SystemExit("lld-link is required; pass --lld-link PATH")
 root=Path(__file__).resolve().parents[1];src=root/"tests/fixtures/sse_scalar_fixture.c";out=a.output.resolve();out.parent.mkdir(parents=True,exist_ok=True);obj=out.with_suffix(".obj")
 cc=[a.clang,"--target=i686-pc-windows-msvc","-ffreestanding","-fno-builtin","-fno-stack-protector","-mno-stack-arg-probe","-msse2","-mfpmath=sse","-O0","-c",str(src),"-o",str(obj)]
 ld=[a.lld_link,"/machine:x86","/subsystem:console","/entry:main","/base:0x400000","/fixed","/nodefaultlib","/out:"+str(out),str(obj)]
 print("Compiling SSE/SSE2 fixture:"," ".join(cc));subprocess.run(cc,check=True);print("Linking SSE/SSE2 PE32:"," ".join(ld));subprocess.run(ld,check=True);obj.unlink(missing_ok=True)
 data=out.read_bytes();pe=int.from_bytes(data[0x3c:0x40],"little")
 if data[:2]!=b"MZ" or data[pe:pe+4]!=b"PE\0\0" or int.from_bytes(data[pe+4:pe+6],"little")!=0x14c or int.from_bytes(data[pe+24:pe+26],"little")!=0x10b: raise SystemExit("output is not an i386 PE32 executable")
 print(f"Created SSE/SSE2 PE32 fixture: {out}");print(f"Size: {len(data)} bytes");return 0
if __name__=="__main__":raise SystemExit(main())
