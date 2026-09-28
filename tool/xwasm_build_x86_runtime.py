#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path
def main() -> int:
 ap=argparse.ArgumentParser(description="Build the XWASM x86 compatibility runtime.")
 ap.add_argument("--output",type=Path,default=Path("dist/x86-runtime-v0.1/runtime.wasm"))
 ap.add_argument("--clang",default=shutil.which("clang"))
 a=ap.parse_args()
 if not a.clang: raise SystemExit("clang is required (install LLVM/Clang or pass --clang PATH).")
 root=Path(__file__).resolve().parents[1]; src=root/"runtime/x86/runtime.c"; generator=root/"tool/xwasm_generate_x86_decode_table.py"
 subprocess.run([__import__("sys").executable,str(generator)],check=True,cwd=root)
 a.output.parent.mkdir(parents=True,exist_ok=True)
 cmd=[a.clang,"--target=wasm32","-O1","-nostdlib","-fno-builtin",str(src),"-o",str(a.output),
      "-Wl,--no-entry","-Wl,--export-all","-Wl,--import-memory",
      "-Wl,--initial-memory=67108864","-Wl,--max-memory=268435456","-Wl,--allow-undefined"]
 print("Building:"," ".join(map(str,cmd))); subprocess.run(cmd,check=True)
 print(f"Built {a.output.resolve()}"); return 0
if __name__=="__main__": raise SystemExit(main())
