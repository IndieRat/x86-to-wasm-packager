#!/usr/bin/env python3
"""Build the initial XWASM guest image from a PE32 section table.

This is not a PE loader. It materializes the preferred-address image needed by
a static-recompilation host and records section metadata in an XWGI01 container.
"""
from __future__ import annotations
import argparse, hashlib, struct
from pathlib import Path

MAGIC=b"XWGI01\0"
HEADER=struct.Struct("<8sIIIIII")
ENTRY=struct.Struct("<IIIIII")

def parse_pe(path:Path):
    data=path.read_bytes()
    if len(data)<0x40 or data[:2]!=b"MZ": raise ValueError("not MZ")
    pe=struct.unpack_from("<I",data,0x3c)[0]
    if pe+24>len(data) or data[pe:pe+4]!=b"PE\0\0": raise ValueError("bad PE signature")
    machine,sections,opt_size=struct.unpack_from("<HHH",data,pe+4)
    opt=pe+24
    if machine!=0x14c or struct.unpack_from("<H",data,opt)[0]!=0x10b: raise ValueError("expected PE32/i386")
    image_base=struct.unpack_from("<I",data,opt+28)[0]
    image_size=struct.unpack_from("<I",data,opt+56)[0]
    table=opt+opt_size
    rows=[]
    for i in range(sections):
        off=table+i*40
        if off+40>len(data): raise ValueError("truncated section table")
        name=data[off:off+8].split(b"\0",1)[0].decode("ascii","replace")
        vsize,va,rsize,rptr=struct.unpack_from("<IIII",data,off+8)
        chars=struct.unpack_from("<I",data,off+36)[0]
        if rsize and rptr+rsize>len(data): raise ValueError(f"section {name} raw data is outside the PE")
        rows.append((name,va,vsize,rsize,rptr,chars))
    return data,image_base,image_size,rows

def main()->int:
    ap=argparse.ArgumentParser(description="Build an XWASM XWGI01 guest image from PE32.")
    ap.add_argument("exe",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--keep-reloc",action="store_true",help="Keep the PE .reloc section; omitted by default for preferred-base images.")
    args=ap.parse_args()
    data,image_base,image_size,rows=parse_pe(args.exe.resolve())
    if not args.keep_reloc:
        rows=[row for row in rows if row[0].lower() != ".reloc"]
    entries=[]; payload=bytearray()
    header_size=HEADER.size+ENTRY.size*len(rows)
    cursor=header_size
    for name,va,vsize,rsize,rptr,chars in rows:
        blob=data[rptr:rptr+rsize] if rsize else b""
        entries.append((va,vsize,rsize,chars,cursor,0))
        payload.extend(blob); cursor+=len(blob)
    flags=0
    header=HEADER.pack(MAGIC,1,image_base,image_size,len(rows),header_size,flags)
    table=b"".join(ENTRY.pack(*e) for e in entries)
    out=args.output.resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(header+table+payload)
    print(f"Guest image: {out}")
    print(f"  preferred image base: 0x{image_base:08x}")
    print(f"  image size: {image_size:,}")
    print(f"  sections: {len(rows)}")
    print(f"  bytes: {out.stat().st_size:,}")
    print(f"  sha256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
    return 0
if __name__=="__main__": raise SystemExit(main())
