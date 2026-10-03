#!/usr/bin/env python3
"""Package a 32-bit PE game into the basic XWASM runtime package."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import pack_file, unpack_bytes  # noqa: E402
from xwasm.dll import convert_dll, pack_xapi_file  # noqa: E402

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
        if not item.is_file() or item.resolve()==exe.resolve(): continue
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
    dll_api_manifests=[]
    dll_api_dir=out/"dll_apis"
    dll_api_dir.mkdir(parents=True,exist_ok=True)

    # Every XWASM package carries the canonical host ABI manifests, even when
    # the original game directory does not ship those Windows DLLs.  Bundled
    # DLLs are then converted against the same seeds and replace the canonical
    # copy with their export-aware manifest.
    canonical_xapis=("kernel32.xapi","user32.xapi","gdi32.xapi","opengl32.xapi","advapi32.xapi")
    seed_dir=ROOT/"runtime"/"x86"/"dlls"
    for api_name in canonical_xapis:
        seed=seed_dir/api_name
        if seed.is_file():
            pack_xapi_file(seed, dll_api_dir/api_name)
            dll_api_manifests.append("dll_apis/"+api_name)

    for dll in dll_files:
        try:
            api_name=dll.stem.lower()+".xapi"
            json_manifest=dll_api_dir/(api_name+".json")
            convert_dll(dll,json_manifest)
            pack_xapi_file(json_manifest,dll_api_dir/api_name)
            json_manifest.unlink()
            manifest_name="dll_apis/"+api_name
            if manifest_name not in dll_api_manifests:
                dll_api_manifests.append(manifest_name)
        except (FileNotFoundError,ValueError):
            pass

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
        "dll_api_format":"XWSC01/XAPI",
        "dll_api_manifests":dll_api_manifests,
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
    print(f"DLL API manifests: {len(dll_api_manifests)} (XWSC01/XAPI)")
    print(f"Runtime: {'bundled as runtime.xwasm' if runtime_source else 'external/host-supplied'}")
    return 0
if __name__=="__main__": raise SystemExit(main())
