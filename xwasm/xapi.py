"""XWASM declarative API manifest support.

.xapi files describe guest DLL imports and map them to stable built-in bridge IDs.
They never contain executable code or arbitrary host callbacks.
"""
from __future__ import annotations
import json
from pathlib import Path

XAPI_FORMAT="xwasm-xapi"
XAPI_VERSION=1
ALLOWED_ABI={"cdecl","stdcall","fastcall"}
ALLOWED_TYPES={"void","u8","u16","u32","i8","i16","i32","u64","i64","f32","f64","ptr"}

def validate_manifest(data: dict) -> list[str]:
    errors=[]
    if not isinstance(data,dict): return ["xapi manifest is not an object"]
    if data.get("format")!=XAPI_FORMAT: errors.append(f"format must be {XAPI_FORMAT!r}")
    if data.get("version")!=XAPI_VERSION: errors.append(f"unsupported xapi version: {data.get('version')!r}")
    libs=data.get("libraries")
    if not isinstance(libs,dict) or not libs: errors.append("libraries must be a non-empty object"); return errors
    for dll,lib in libs.items():
        if not isinstance(dll,str) or not dll: errors.append("library names must be non-empty strings"); continue
        if not isinstance(lib,dict): errors.append(f"{dll}: library definition must be an object"); continue
        funcs=lib.get("functions")
        if not isinstance(funcs,dict): errors.append(f"{dll}: functions must be an object"); continue
        for name,fn in funcs.items():
            if not isinstance(fn,dict): errors.append(f"{dll}!{name}: definition must be an object"); continue
            if not isinstance(fn.get("id"),int) or fn["id"]<1: errors.append(f"{dll}!{name}: id must be a positive integer")
            if fn.get("abi","stdcall") not in ALLOWED_ABI: errors.append(f"{dll}!{name}: unsupported ABI")
            args=fn.get("args",[])
            if not isinstance(args,list) or any(a not in ALLOWED_TYPES for a in args): errors.append(f"{dll}!{name}: invalid args")
            if fn.get("return","u32") not in ALLOWED_TYPES: errors.append(f"{dll}!{name}: invalid return type")
            bridge=fn.get("bridge")
            if not isinstance(bridge,str) or not bridge or not bridge.startswith("xw."): errors.append(f"{dll}!{name}: bridge must be a built-in xw.* ID")
    return errors

def read(path:Path)->dict:
    data=json.loads(path.read_text(encoding="utf-8")); errors=validate_manifest(data)
    if errors: raise ValueError("; ".join(errors))
    return data

def write(path:Path,data:dict)->None:
    errors=validate_manifest(data)
    if errors: raise ValueError("; ".join(errors))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
