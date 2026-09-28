#!/usr/bin/env python3
"""Generate the compact C x86 decoder table from the JSON encoding database."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=Path("runtime/x86/instruction_encodings.json"))
    ap.add_argument("--output", type=Path, default=Path("runtime/x86/generated_decode_table.h"))
    args = ap.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    rows = []
    for item in data["encodings"]:
        for opcode in item["opcode"]:
            rows.append({
                "map": {"primary":0, "escape_0f":1, "escape_0f38":2, "escape_0f3a":3}[item["opcode_map"]],
                "opcode": int(opcode, 16),
                "needs_modrm": 1 if item.get("modrm", {}).get("required") else 0,
                "ext": item.get("modrm", {}).get("reg_extension", -1),
                "id": item["id"],
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* Generated from runtime/x86/instruction_encodings.json. Do not edit manually. */",
        "#ifndef XWASM_X86_DECODE_TABLE_H",
        "#define XWASM_X86_DECODE_TABLE_H",
        "typedef struct {",
        "  uint8_t map;",
        "  uint8_t opcode;",
        "  uint8_t needs_modrm;",
        "  int8_t modrm_ext;",
        "  const char *id;",
        "} x86_decode_entry_t;",
        "static const x86_decode_entry_t x86_decode_table[] = {",
    ]
    for row in rows:
        lines.append(
            f'  {{{row["map"]},0x{row["opcode"]:02X},{row["needs_modrm"]},{row["ext"]},"{row["id"]}"}},'
        )
    lines += [
        "};",
        "#define X86_DECODE_TABLE_COUNT (sizeof(x86_decode_table)/sizeof(x86_decode_table[0]))",
        "#endif",
        "",
    ]
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {len(rows)} opcode entries: {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
