#!/usr/bin/env python3
"""Collect sub-.xapi manifests into ONE game .xapi.

Inputs may be plain JSON (.xapi / seed) or packed XWSC01 xapi containers.
Rules:
  * the same lib+function in two inputs: later input wins (reported), unless --strict
  * a numeric id used by two different functions is always an error
  * functions without an "id" get the next free id inside their library's 0x1000 block
  * top-level "dll_aliases" ({"api-ms-win-crt-math-l1-1-0.dll":"MATH.dll"}) are merged
Outputs: --output packed XWSC01 (what the shell loads), --json merged plain seed
(usable as `xwasm_build_xapi.py --seed`).
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys, zlib
from pathlib import Path

MAGIC = b"XWSC01"; KIND_XAPI = 4
TYPES = {"void", "u32", "i32", "ptr", "f32", "f64"}

def load(path: Path) -> dict:
    raw = path.read_bytes()
    if raw[:6] == MAGIC:
        kind, comp = raw[8], raw[9]
        raw_size, stored = struct.unpack_from("<QQ", raw, 14)
        if kind != KIND_XAPI: raise SystemExit(f"{path}: XWSC01 container is not an xapi (kind {kind})")
        body = raw[62:]
        if len(body) != stored: raise SystemExit(f"{path}: stored size mismatch")
        data = zlib.decompress(body) if comp == 1 else body
        if len(data) != raw_size or hashlib.sha256(data).digest() != raw[30:62]:
            raise SystemExit(f"{path}: size/sha256 mismatch")
        raw = data
    d = json.loads(raw.decode("utf-8-sig"))
    if d.get("format") != "xwasm-xapi" or "libraries" not in d:
        raise SystemExit(f"{path}: not an xwasm-xapi manifest")
    return d

def pack(data: bytes, compress: bool = True) -> bytes:
    stored = zlib.compress(data, 9) if compress else data
    comp = 1 if compress else 0
    hdr = bytearray(62)
    hdr[0:6] = MAGIC
    struct.pack_into("<H", hdr, 6, 1)
    hdr[8] = KIND_XAPI; hdr[9] = comp
    struct.pack_into("<QQ", hdr, 14, len(data), len(stored))
    hdr[30:62] = hashlib.sha256(data).digest()
    return bytes(hdr) + stored

def gather(paths):
    out = []
    for p in paths:
        p = Path(p)
        out += sorted(x for x in p.rglob("*.xapi")) if p.is_dir() else [p]
    return out

def merge(files, strict=False):
    libs: dict[str, dict] = {}; aliases: dict[str, str] = {}; owner: dict[int, str] = {}; notes = []
    for f in files:
        d = load(f)
        aliases.update(d.get("dll_aliases", {}))
        for lib, body in d["libraries"].items():
            key = next((k for k in libs if k.lower() == lib.lower()), lib)
            dst = libs.setdefault(key, {"functions": {}})
            for k, v in body.items():
                if k != "functions": dst.setdefault(k, v)
            for name, fn in body["functions"].items():
                for t in fn.get("args", []) + [fn.get("return", "void")]:
                    if t not in TYPES: raise SystemExit(f"{f}: {lib}!{name}: unknown type {t!r}")
                if fn.get("abi") not in ("stdcall", "cdecl"): raise SystemExit(f"{f}: {lib}!{name}: abi must be stdcall|cdecl")
                if "id" in fn:
                    if owner.get(fn["id"], f"{key}!{name}") != f"{key}!{name}":
                        raise SystemExit(f"{f}: id {fn['id']} already used by {owner[fn['id']]} (wanted by {key}!{name})")
                if name in dst["functions"]:
                    if strict: raise SystemExit(f"{f}: {key}!{name} defined twice (--strict)")
                    notes.append(f"override {key}!{name} from {f.name}")
                    owner.pop(dst["functions"][name].get("id"), None)
                dst["functions"][name] = dict(fn)
                if "id" in fn: owner[fn["id"]] = f"{key}!{name}"
    # assign ids for functions that lack one
    for lib, body in libs.items():
        ids = [fn["id"] for fn in body["functions"].values() if "id" in fn]
        base = (min(ids) & ~0xFFF) if ids else None
        for name, fn in body["functions"].items():
            if "id" in fn: continue
            if base is None:
                base = max([0x1000] + [i & ~0xFFF for i in owner]) + 0x1000
            nid = max([base] + [i for i in owner if (i & ~0xFFF) == base]) + 1
            fn["id"] = nid; owner[nid] = f"{lib}!{name}"; notes.append(f"assigned id {nid} to {lib}!{name}")
    for lib, body in libs.items():
        for name, fn in body["functions"].items():
            fn.setdefault("bridge", f"xw.{lib.split('.')[0].lower()}.{name}")
    out = {"format": "xwasm-xapi", "version": 1, "libraries": libs}
    if aliases: out["dll_aliases"] = aliases
    out["generated_by"] = "tool/xwasm_merge_xapi.py"
    out["sources"] = [str(f) for f in files]
    return out, notes

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="sub .xapi files or directories (later wins)")
    ap.add_argument("--output", type=Path, required=True, help="packed XWSC01 game .xapi")
    ap.add_argument("--json", type=Path, help="also write the merged plain-JSON seed")
    ap.add_argument("--strict", action="store_true", help="error instead of override on duplicate functions")
    ap.add_argument("--no-compress", action="store_true")
    a = ap.parse_args()
    files = gather(a.inputs)
    if not files: raise SystemExit("no .xapi inputs found")
    merged, notes = merge(files, a.strict)
    payload = json.dumps(merged, indent=2).encode()
    if a.json: a.json.write_bytes(payload)
    a.output.write_bytes(pack(payload, not a.no_compress))
    n = sum(len(v["functions"]) for v in merged["libraries"].values())
    print(f"Merged {len(files)} file(s) -> {a.output}  libraries={len(merged['libraries'])} functions={n} aliases={len(merged.get('dll_aliases', {}))}")
    for lib, body in merged["libraries"].items(): print(f"  {lib}: {len(body['functions'])}")
    for x in notes: print("  note:", x)
    return 0

if __name__ == "__main__": raise SystemExit(main())
