#!/usr/bin/env python3
"""Build/package pipeline for XWASM static recompilation."""
from __future__ import annotations
import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from xwasm_recomp_pack import main as package_main

def main()->int:
    ap=argparse.ArgumentParser(description="Build a game using the XWASM static-recompilation formula.")
    ap.add_argument("game_folder",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--exe",type=Path)
    ap.add_argument("--module",type=Path)
    ap.add_argument("--image",type=Path)
    ap.add_argument("--backend-command")
    ap.add_argument("--name")
    ap.add_argument("--keep-work",action="store_true")
    a=ap.parse_args()
    game=a.game_folder.resolve(); out=a.output.resolve()
    if not game.is_dir(): raise SystemExit(f"game folder not found: {game}")
    if bool(a.module)!=bool(a.image): raise SystemExit("--module and --image must be supplied together")

    work=Path(tempfile.mkdtemp(prefix="xwasm-recomp-"))
    try:
        module=a.module.resolve() if a.module else None
        image=a.image.resolve() if a.image else None
        if module is None:
            if not a.backend_command:
                raise SystemExit("Supply --module/--image, or --backend-command for the translator.")
            exe=(game/a.exe).resolve() if a.exe else None
            env=os.environ.copy()
            env.update({
                "XWASM_GAME_DIR":str(game),
                "XWASM_EXE":str(exe) if exe else "",
                "XWASM_WORK_DIR":str(work),
                "XWASM_OUTPUT_WASM":str(work/"boot.wasm"),
                "XWASM_OUTPUT_IMAGE":str(work/"guest.segs.bin"),
            })
            print("Running static-recompilation backend...")
            subprocess.run(a.backend_command,shell=True,check=True,env=env,cwd=game)
            module=work/"boot.wasm"; image=work/"guest.segs.bin"
            if not module.is_file() or not image.is_file():
                raise SystemExit("Backend did not emit XWASM_OUTPUT_WASM and XWASM_OUTPUT_IMAGE.")

        argv=["xwasm_recomp_pack.py",str(game),"--module",str(module),"--image",str(image),"--output",str(out)]
        if a.exe: argv += ["--exe",str(a.exe)]
        if a.name: argv += ["--name",a.name]
        old=sys.argv; sys.argv=argv
        try: return package_main()
        finally: sys.argv=old
    finally:
        if a.keep_work: print(f"Backend work directory: {work}")
        else: shutil.rmtree(work,ignore_errors=True)

if __name__=="__main__": raise SystemExit(main())
