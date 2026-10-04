#!/usr/bin/env python3
"""Package a 32-bit PE game into the basic XWASM runtime package."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import pack_file, unpack_bytes  # noqa: E402
from xwasm.dll import convert_dll, pack_xapi_manifest  # noqa: E402
from tool.xwasm_merge_xapi import merge as merge_xapi_manifests  # noqa: E402

def pe32_info(path: Path) -> dict:
    data=path.read_bytes()
    if data[:2]!=b"MZ": raise ValueError(f"{path.name} is not a PE file (missing MZ header).")
    pe=struct.unpack_from("<I",data,0x3C)[0]
    if data[pe:pe+4]!=b"PE\0\0": raise ValueError(f"{path.name} has an invalid PE signature.")
    machine=struct.unpack_from("<H",data,pe+4)[0]
    magic=struct.unpack_from("<H",data,pe+24)[0]
    if machine!=0x014C or magic!=0x10B:
        raise ValueError(f"{path.name} is not a PE32/i386 executable: machine=0x{machine:04x}, optional_magic=0x{magic:04x}")
    return {"machine":"i386","machine_id":machine,"pe_type":"PE32","size":len(data)}

def copy_tree(source:Path,dest:Path,exe:Path)->int:
    count=0
    for item in source.rglob("*"):
        if not item.is_file() or item.resolve()==exe.resolve() or item.suffix.lower()==".xapi": continue
        rel=item.relative_to(source); target=dest/rel; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(item,target); count+=1
    return count

def main()->int:
    ap=argparse.ArgumentParser(description="Package a 32-bit PE game as an XWASM x86-runtime package.")
    ap.add_argument("game_folder",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--exe",type=Path,default=None,help="Executable path relative to game_folder; otherwise auto-detect an EXE.")
    ap.add_argument("--runtime",default=None,help="Path to runtime.xwasm (or legacy runtime.wasm).")
    a=ap.parse_args()
    game=a.game_folder.resolve(); out=a.output.resolve()
    if not game.is_dir(): raise SystemExit("Input game_folder must be a directory.")
    out.mkdir(parents=True,exist_ok=True); resources=out/"resources"; resources.mkdir(parents=True,exist_ok=True)
    exe=(game/a.exe).resolve() if a.exe else None
    if exe is None:
        candidates=sorted(game.glob("*.exe")) or sorted(game.rglob("*.exe"))
        if not candidates: raise SystemExit("No EXE found.")
        exe=candidates[0]
    if not exe.is_file(): raise SystemExit(f"Executable not found: {exe}")
    info=pe32_info(exe)

    payload=out/"payload.xpl"
    pack_file(exe,payload,"xpl",compression="auto")

    count=copy_tree(game,resources,exe)
    dll_files=[x for x in sorted(game.rglob("*.dll")) if x.resolve()!=exe.resolve()]
    bundled_dlls=[str(x.relative_to(game)).replace("\\","/") for x in dll_files]
    # XAPI is a build-time translation boundary: the repository seeds describe
    # the compatibility ABI, and bundled PE32 DLLs contribute export-aware
    # manifests.  Only the merged package-local pool is shipped; the source
    # runtime/x86/dlls directory is never required by the browser package.
    seed_dir=ROOT/"runtime"/"x86"/"dlls"
    seed_xapis=sorted(seed_dir.glob("*.xapi"))
    if not seed_xapis:
        raise SystemExit(f"No XAPI seeds found in {seed_dir}")

    converted_dlls=[]
    xapi_unconverted_dlls=[]
    with tempfile.TemporaryDirectory(prefix="xwasm-xapi-build-") as temp_name:
        temp_dir=Path(temp_name)
        xapi_sources=list(seed_xapis)
        for index,dll in enumerate(dll_files):
            try:
                json_manifest=temp_dir/f"{index:04d}-{dll.stem.lower()}.xapi.json"
                convert_dll(dll,json_manifest)
                xapi_sources.append(json_manifest)
                converted_dlls.append(str(dll.relative_to(game)).replace("\\\\","/"))
            except FileNotFoundError as exc:
                # Keep the original DLL in resources/, but make the missing XAPI
                # seed explicit in the package manifest so DLL coverage is
                # auditable instead of silently disappearing.
                xapi_unconverted_dlls.append({
                    "dll": str(dll.relative_to(game)).replace("\\","/"),
                    "reason": "missing_xapi_seed",
                    "detail": str(exc),
                })
            except ValueError as exc:
                xapi_unconverted_dlls.append({
                    "dll": str(dll.relative_to(game)).replace("\\","/"),
                    "reason": "xapi_conversion_error",
                    "detail": str(exc),
                })

        merged_xapi,merge_notes=merge_xapi_manifests(xapi_sources)
        xapi_pool=out/"xapi_pool.xapi"
        pack_xapi_manifest(merged_xapi,xapi_pool)

    xapi_library_count=len(merged_xapi.get("libraries",{}))
    xapi_function_count=sum(len(v.get("functions",{})) for v in merged_xapi.get("libraries",{}).values())
    xapi_source_count=len(xapi_sources)

    runtime_source=None
    runtime_raw=None
    if a.runtime:
        candidate=Path(a.runtime)
        if not candidate.is_absolute():
            game_candidate=game/candidate
            candidate=game_candidate if game_candidate.is_file() else Path.cwd()/candidate
        runtime_source=candidate.resolve()
        if not runtime_source.is_file(): raise SystemExit(f"Runtime path does not exist: {a.runtime}")
        runtime_data=runtime_source.read_bytes()
        if runtime_data[:4]==b"\x00asm":
            runtime_raw=runtime_data
        else:
            _, runtime_raw=unpack_bytes(runtime_data,expected_kind="xwasm")

    manifest={
        "format":"xwasm-package","format_version":1,"name":game.name,"architecture":"x86",
        "runtime_kind":"x86-compatibility","runtime":"runtime.xwasm" if runtime_source else None,
        "runtime_sha256": hashlib.sha256(runtime_raw).hexdigest() if runtime_raw else None,
        "abi":"xwasm.host/1","resource_root":"resources/","payload":"payload.xpl",
        "payload_format":"XPL","payload_architecture":"i386",
        "entry":{"init":"xwasm_init","tick":"xwasm_tick","shutdown":"xwasm_shutdown"},
        "pe":info,"resource_file_count":count,"bundled_dlls":bundled_dlls,
        "xapi_pool":"xapi_pool.xapi","xapi_pool_format":"XWSC01/XAPI",
        "xapi_source_count":xapi_source_count,"xapi_library_count":xapi_library_count,
        "xapi_function_count":xapi_function_count,"xapi_converted_dlls":converted_dlls,
        "sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),
        "execution_status":"x86_runtime_bundled" if runtime_source else "requires_x86_runtime",
    }
    if runtime_source is not None:
        if runtime_source.read_bytes()[:4] == b"\x00asm":
            raise SystemExit("Runtime must be .xwasm for the new package format; pass the .xwasm output.")
        shutil.copy2(runtime_source,out/"runtime.xwasm")
    (out/"manifest.xwasm.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(f"Created XWASM x86 package: {out}")
    print(f"Payload: {payload.relative_to(out)}")
    print(f"Resources: {count}")
    print(f"XAPI pool: xapi_pool.xapi (sources={xapi_source_count}, libraries={xapi_library_count}, functions={xapi_function_count})")
    print(f"Converted bundled DLLs: {len(converted_dlls)}")
    print(f"Bundled DLLs without usable XAPI manifests: {len(xapi_unconverted_dlls)}")
    for item in xapi_unconverted_dlls:
        print(f"  XAPI missing: {item['dll']} [{item['reason']}]")
    for note in merge_notes:
        print(f"  XAPI: {note}")
    print(f"Runtime: {'bundled as runtime.xwasm' if runtime_source else 'external/host-supplied'}")
    return 0
if __name__=="__main__": raise SystemExit(main())
