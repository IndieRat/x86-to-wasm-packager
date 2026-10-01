#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
src=ROOT/"runtime/x86/instruction_encodings.json"
out=ROOT/"runtime/x86/opcode_map_i386.json"

data=json.loads(src.read_text(encoding="utf-8"))
names=("primary","escape_0f","escape_0f38","escape_0f3a")
maps={n:[{"byte":f"{i:02X}","status":"RESERVED","encoding_ids":[]} for i in range(256)] for n in names}
def prefix_bits(e):
    p=e.get("prefix_required")
    if p == "F2": return 0x02,0x02
    if p == "F3": return 0x04,0x04
    return 0,0

for e in data["encodings"]:
    # FCOMPP is an exact two-byte x87 form (DE D9) handled by the decoder
    # as a special sequence rather than a single opcode-map slot.
    if e["id"] == "FCOMPP":
        continue
    op=e["opcode"]
    mp=e.get("opcode_map","primary")
    if mp not in maps:
        raise ValueError(f"unknown opcode map: {mp}")
    if not op:
        raise ValueError(f"empty opcode: {e['id']}")
    # The database uses opcode arrays for alternative single-byte opcodes
    # (for example B8..BF). Add every alternative to the map.
    prefix_mask,prefix_value=prefix_bits(e)
    for opcode in op:
        if len(opcode) != 2:
            raise ValueError(f"opcode map requires single-byte opcodes: {e['id']}={opcode}")
        b=int(opcode,16)
        slot=maps[mp][b]
        slot["status"]="MAPPED"
        if e["id"] not in slot["encoding_ids"]:
            slot["encoding_ids"].append(e["id"])
result={
 "format":"xwasm-x86-opcode-map","version":1,"architecture":"i386",
 "source":"XWASM-maintained map generated from instruction_encodings.json",
 "notes":["Generated; do not hand-edit. RESERVED does not assert Intel reservation in every mode.",
          "All four legacy/escape maps are represented as 256-slot tables."],
 "maps":maps
}
out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
counts={k:sum(x["status"]=="MAPPED" for x in v) for k,v in maps.items()}
print("Generated opcode maps:",", ".join(f"{k}={v}" for k,v in counts.items()))
