#!/usr/bin/env python3
"""Package a statically recompiled x86 game as an XWASM recompiled package."""
from __future__ import annotations
import argparse, hashlib, json, shutil, struct, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from xwasm.format import ABI,META_SECTION,write_manifest  # noqa: E402

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def pe_info(path:Path)->dict:
    data=path.read_bytes()
    if len(data)<0x40 or data[:2]!=b"MZ": raise ValueError("source executable is not an MZ/PE file")
    pe=struct.unpack_from("<I",data,0x3c)[0]
    if pe+24>len(data) or data[pe:pe+4]!=b"PE\0\0": raise ValueError("source executable has no PE signature")
    machine=struct.unpack_from("<H",data,pe+4)[0]
    magic=struct.unpack_from("<H",data,pe+24)[0]
    if machine!=0x14c or magic!=0x10b:
        raise ValueError(f"source executable must be PE32/i386 (machine=0x{machine:04x}, magic=0x{magic:04x})")
    return {
        "machine":"i386","pe_type":"PE32","file_size":len(data),
        "sha256":hashlib.sha256(data).hexdigest(),
        "entry_rva":struct.unpack_from("<I",data,pe+24+16)[0],
        "image_base":struct.unpack_from("<I",data,pe+24+28)[0],
        "size_of_image":struct.unpack_from("<I",data,pe+24+56)[0],
    }

def copy_resources(game:Path,exe:Path,out:Path)->int:
    root=out/"resources"; count=0
    for src in game.rglob("*"):
        if not src.is_file() or src.resolve()==exe.resolve(): continue
        dst=root/src.relative_to(game); dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst); count+=1
    return count

def leb_u32(value:int)->bytes:
    out=bytearray()
    while True:
        b=value&0x7f; value>>=7
        out.append(b | (0x80 if value else 0))
        if not value: return bytes(out)

def has_meta(wasm:bytes)->bool:
    if wasm[:4]!=b"\0asm": raise ValueError("translated module is not WebAssembly")
    pos=8
    while pos<len(wasm):
        section=wasm[pos]; pos+=1
        size,pos=read_leb(wasm,pos); end=pos+size
        if end>len(wasm): raise ValueError("truncated WASM section")
        if section==0:
            nlen,npos=read_leb(wasm,pos)
            if wasm[npos:npos+nlen]==META_SECTION.encode(): return True
        pos=end
    return False

def read_leb(data:bytes,pos:int)->tuple[int,int]:
    value=0; shift=0
    while True:
        if pos>=len(data) or shift>35: raise ValueError("invalid WASM LEB128")
        b=data[pos]; pos+=1; value|=(b&0x7f)<<shift
        if not b&0x80: return value,pos
        shift+=7

def add_meta(wasm:bytes)->bytes:
    if has_meta(wasm): return wasm
    meta=json.dumps({"format":"xwasm-meta","version":1,"abi":ABI,"kind":"x86-recompiled"},separators=(",",":")).encode()
    name=META_SECTION.encode()
    payload=leb_u32(len(name))+name+meta
    return wasm+b"\0"+leb_u32(len(payload))+payload

def main()->int:
    ap=argparse.ArgumentParser(description="Package a statically recompiled x86 game.")
    ap.add_argument("game_folder",type=Path)
    ap.add_argument("--module",type=Path,required=True)
    ap.add_argument("--image",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--exe",type=Path)
    ap.add_argument("--name")
    ap.add_argument("--module-name",default="boot.wasm")
    ap.add_argument("--image-name",default="guest.segs.bin")
    a=ap.parse_args()
    game=a.game_folder.resolve(); module=a.module.resolve(); image=a.image.resolve(); out=a.output.resolve()
    if not game.is_dir(): raise SystemExit(f"game folder not found: {game}")
    if not module.is_file(): raise SystemExit(f"WASM module not found: {module}")
    if not image.is_file(): raise SystemExit(f"guest image not found: {image}")

    exe=(game/a.exe).resolve() if a.exe else None
    if exe is None:
        valid=[]
        for candidate in game.rglob("*.exe"):
            try: info=pe_info(candidate)
            except ValueError: continue
            valid.append((candidate.stat().st_size,candidate))
        if not valid: raise SystemExit("no PE32/i386 executable found; use --exe")
        exe=max(valid,key=lambda x:(x[0],str(x[1]).lower()))[1]
    if not exe.is_file(): raise SystemExit(f"executable not found: {exe}")
    source=pe_info(exe)

    out.mkdir(parents=True,exist_ok=True)
    (out/a.module_name).write_bytes(add_meta(module.read_bytes()))
    shutil.copy2(image,out/a.image_name)
    count=copy_resources(game,exe,out)

    manifest={
        "format":"xwasm-package","format_version":1,"name":a.name or game.name,
        "architecture":"x86-recompiled","module":a.module_name,"image":a.image_name,
        "bridge":None,"resource_root":"resources/","abi":ABI,
        "entry":{"init":"xwasm_init","tick":"xwasm_tick","shutdown":"xwasm_shutdown"},
        "recompilation":{
            "model":"static-recompilation",
            "source_executable":str(exe.relative_to(game)).replace("\\","/"),
            "source":source,
            "module_sha256":sha256(out/a.module_name),
            "image_sha256":sha256(out/a.image_name),
            "resource_file_count":count
        }
    }
    write_manifest(out/"manifest.xwasm.json",manifest)
    print(f"Created recompiled XWASM package: {out}")
    print(f"  module: {a.module_name} ({(out/a.module_name).stat().st_size} bytes)")
    print(f"  image:  {a.image_name} ({(out/a.image_name).stat().st_size} bytes)")
    print(f"  resources: {count}")
    return 0

if __name__=="__main__": raise SystemExit(main())
