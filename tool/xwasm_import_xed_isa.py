#!/usr/bin/env python3
"""Import Intel XED's machine-readable ISA patterns into an XWASM source snapshot.

This is an OPTIONAL build-time tool. The browser runtime never contacts Intel.
The default source is Intel's public XED repository. Use --input for an
offline/reproducible build after downloading the source once.
"""

from __future__ import annotations
import argparse, json, re
from pathlib import Path
from urllib.request import urlopen

DEFAULT_URL = "https://raw.githubusercontent.com/intelxed/xed/main/datafiles/xed-isa.txt"
BLOCK_RE = re.compile(r"\{\s*(.*?)\s*\}", re.S)

def load_text(args):
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    with urlopen(args.url, timeout=30) as r:
        return r.read().decode("utf-8")

def parse_block(block):
    fields = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    if "ICLASS" not in fields or "PATTERN" not in fields:
        return None
    return {
        "iclass": fields["ICLASS"],
        "category": fields.get("CATEGORY"),
        "extension": fields.get("EXTENSION"),
        "isa_set": fields.get("ISA_SET"),
        "attributes": fields.get("ATTRIBUTES", ""),
        "pattern": fields["PATTERN"],
        "operands": fields.get("OPERANDS", ""),
        "iform": fields.get("IFORM"),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path,
                    help="offline xed-isa.txt snapshot; avoids network access")
    ap.add_argument("--url", default=DEFAULT_URL,
                    help="XED ISA source URL used when --input is omitted")
    ap.add_argument("--output", type=Path,
                    default=Path("runtime/x86/xed_isa_patterns.json"))
    ap.add_argument("--legacy-i386", action="store_true",
                    help="keep only patterns without 64-bit-only mode markers")
    args = ap.parse_args()

    text = load_text(args)
    records = []
    for block in BLOCK_RE.findall(text):
        item = parse_block(block)
        if item is None:
            continue
        if args.legacy_i386 and "mode64" in item["pattern"] and "mode32" not in item["pattern"]:
            continue
        records.append(item)

    out = {
        "format": "xwasm-x86-xed-pattern-snapshot",
        "version": 1,
        "architecture": "i386",
        "source": args.url if not args.input else str(args.input),
        "generator": "tool/xwasm_import_xed_isa.py",
        "record_count": len(records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"XED ISA patterns: {len(records)}")
    print(f"Wrote: {args.output}")

if __name__ == "__main__":
    raise SystemExit(main())
