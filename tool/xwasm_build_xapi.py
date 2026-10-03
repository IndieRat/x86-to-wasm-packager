#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from xwasm.xapi import read
from xwasm.dll import pack_xapi_manifest

def main()->int:
    ap=argparse.ArgumentParser(description="Build/validate a versioned XWASM .xapi API manifest.")
    ap.add_argument("--seed",type=Path,default=ROOT/"specs/xapi/v1.seed.json")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    data=read(args.seed.resolve())
    data["generated_by"]="tool/xwasm_build_xapi.py"
    data["source"]=str(args.seed)
    pack_xapi_manifest(data, args.output.resolve())
    print(f"Created XWSC01 XWASM API manifest: {args.output.resolve()}")
    print(f"Version: {data['version']}  Libraries: {len(data['libraries'])}")
    print(f"Functions: {sum(len(v['functions']) for v in data['libraries'].values())}")
    return 0
if __name__=="__main__": raise SystemExit(main())
