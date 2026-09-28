#!/usr/bin/env python3
"""Validate the XWASM v0.8 x86 instruction catalog, definitions, and encodings."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED_GROUPS = {
    "integer_core", "data_move", "control_flow", "bit_and_shift",
    "string", "x87", "mmx_sse", "system",
}
VALID_STATUS = {"EXECUTE", "DECODE", "PLANNED", "SYSTEM"}
VALID_ACCESS = {"r", "w", "rw"}
VALID_KINDS = {"reg32", "rm32", "imm8", "imm32", "rel8", "rel32"}

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def load_catalog(path: Path) -> dict:
    data = read_json(path)
    if data.get("format") != "xwasm-x86-instruction-db":
        raise ValueError("unexpected instruction catalog format")
    if data.get("architecture") != "i386":
        raise ValueError("instruction catalog must target i386")
    groups = data.get("instruction_sets")
    if not isinstance(groups, dict):
        raise ValueError("missing instruction_sets")
    missing = REQUIRED_GROUPS - set(groups)
    if missing:
        raise ValueError("missing groups: " + ", ".join(sorted(missing)))
    for group, entries in groups.items():
        if not isinstance(entries, list):
            raise ValueError(f"{group}: expected a list")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("mnemonic"):
                raise ValueError(f"{group}: entry missing mnemonic")
            if entry.get("status") not in VALID_STATUS:
                raise ValueError(f"{group}/{entry.get('mnemonic')}: invalid status")
    return data

def load_definitions(path: Path) -> dict:
    data = read_json(path)
    if data.get("format") != "xwasm-x86-instruction-definitions":
        raise ValueError("unexpected instruction definitions format")
    if data.get("architecture") != "i386":
        raise ValueError("instruction definitions must target i386")
    instructions = data.get("instructions")
    if not isinstance(instructions, list) or not instructions:
        raise ValueError("instruction definitions must contain instructions")
    ids = set()
    for item in instructions:
        if not isinstance(item, dict):
            raise ValueError("instruction definition must be an object")
        for field in ("id", "mnemonic", "family", "status", "forms", "flags"):
            if field not in item:
                raise ValueError(f"instruction definition missing {field}")
        if item["id"] in ids:
            raise ValueError(f"duplicate instruction definition: {item['id']}")
        ids.add(item["id"])
        if item["status"] not in VALID_STATUS:
            raise ValueError(f"{item['id']}: invalid status")
        if not isinstance(item["forms"], list) or not item["forms"]:
            raise ValueError(f"{item['id']}: forms must be a non-empty list")
        flags = item["flags"]
        if not isinstance(flags, dict):
            raise ValueError(f"{item['id']}: flags must be an object")
        for key in ("read", "write"):
            if key not in flags or not isinstance(flags[key], list):
                raise ValueError(f"{item['id']}: flags.{key} must be a list")
    return data

def load_encodings(path: Path) -> dict:
    data = read_json(path)
    if data.get("format") != "xwasm-x86-encoding-db":
        raise ValueError("unexpected instruction encoding format")
    if data.get("architecture") != "i386":
        raise ValueError("instruction encodings must target i386")
    encodings = data.get("encodings")
    if not isinstance(encodings, list) or not encodings:
        raise ValueError("instruction encodings must contain encodings")
    ids = set()
    for item in encodings:
        if not isinstance(item, dict):
            raise ValueError("encoding must be an object")
        for field in ("id", "instruction", "opcode", "opcode_map", "encoding", "operands"):
            if field not in item:
                raise ValueError(f"encoding missing {field}")
        if item["id"] in ids:
            raise ValueError(f"duplicate encoding: {item['id']}")
        ids.add(item["id"])
        if not isinstance(item["opcode"], list) or not item["opcode"]:
            raise ValueError(f"{item['id']}: opcode must be a non-empty list")
        for byte in item["opcode"]:
            if not isinstance(byte, str) or len(byte) != 2:
                raise ValueError(f"{item['id']}: opcode bytes must be two-digit hex strings")
            int(byte, 16)
        if not isinstance(item["operands"], list):
            raise ValueError(f"{item['id']}: operands must be a list")
        for operand in item["operands"]:
            if not isinstance(operand, dict):
                raise ValueError(f"{item['id']}: operand must be an object")
            if operand.get("kind") not in VALID_KINDS:
                raise ValueError(f"{item['id']}: invalid operand kind {operand.get('kind')}")
            if operand.get("access") not in VALID_ACCESS:
                raise ValueError(f"{item['id']}: invalid operand access")
        modrm = item.get("modrm")
        if modrm is not None:
            if not isinstance(modrm, dict) or not modrm.get("required"):
                raise ValueError(f"{item['id']}: modrm must be an object with required=true")
            ext = modrm.get("reg_extension")
            if ext is not None and not 0 <= ext <= 7:
                raise ValueError(f"{item['id']}: invalid ModR/M reg extension")
    return data

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", type=Path,
                    default=Path("runtime/x86/instructions.json"))
    ap.add_argument("--definitions", type=Path,
                    default=Path("runtime/x86/instruction_definitions.json"))
    ap.add_argument("--encodings", type=Path,
                    default=Path("runtime/x86/instruction_encodings.json"))
    ap.add_argument("--strict", action="store_true",
                    help="fail if the catalog contains non-EXECUTE entries")
    args = ap.parse_args()

    catalog = load_catalog(args.path)
    definitions = load_definitions(args.definitions)
    encodings = load_encodings(args.encodings)

    catalog_ids = {
        entry["mnemonic"].split("/")[0]
        for entries in catalog["instruction_sets"].values()
        for entry in entries
    }
    definition_ids = {item["id"] for item in definitions["instructions"]}
    encoding_instructions = {item["instruction"] for item in encodings["encodings"]}

    missing_definition_links = sorted(
        item["instruction"] for item in encodings["encodings"]
        if item["instruction"] not in definition_ids
    )
    if missing_definition_links:
        raise ValueError("encodings reference undefined instructions: " +
                         ", ".join(missing_definition_links))

    missing_encoding_links = sorted(
        item["id"] for item in definitions["instructions"]
        if item["status"] == "EXECUTE" and item["id"] not in encoding_instructions
    )
    if missing_encoding_links:
        raise ValueError("EXECUTE definitions without encodings: " +
                         ", ".join(missing_encoding_links))

    counts = {status: 0 for status in sorted(VALID_STATUS)}
    total = 0
    for entries in catalog["instruction_sets"].values():
        for entry in entries:
            counts[entry["status"]] += 1
            total += 1

    print("XWASM x86 instruction databases")
    print(f"catalog architecture:     {catalog['architecture']}")
    print(f"catalog version:           {catalog['version']}")
    print(f"catalog instructions:      {total}")
    for status in sorted(counts):
        print(f"{status:9}: {counts[status]}")
    print(f"semantic definitions:      {len(definition_ids)}")
    print(f"concrete encodings:        {len(encodings['encodings'])}")
    print(f"catalog mnemonic families: {len(catalog_ids)}")

    if args.strict and counts["EXECUTE"] != total:
        print("STRICT: instruction catalog still contains non-executing entries")
        return 2

    print("VALID")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
