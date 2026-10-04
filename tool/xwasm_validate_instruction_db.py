#!/usr/bin/env python3
"""Validate the XWASM v0.8 x86 instruction catalog, definitions, encodings, and opcode map."""

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
VALID_KINDS = {
    "reg8", "reg16", "reg32", "rm8", "rm16", "rm32", "rm64", "rm512", "xmm",
    "imm8", "imm16", "imm32", "rel8", "rel16", "rel32",
    "moffs8", "moffs32", "st0",
    "sti",
}


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


def load_opcode_map(path: Path) -> dict:
    data = read_json(path)
    if data.get("format") != "xwasm-x86-opcode-map":
        raise ValueError("unexpected opcode map format")
    if data.get("architecture") != "i386":
        raise ValueError("opcode map must target i386")
    maps = data.get("maps")
    if not isinstance(maps, dict):
        raise ValueError("opcode map is missing maps")

    for name in ("primary", "escape_0f", "escape_0f38", "escape_0f3a"):
        slots = maps.get(name)
        if not isinstance(slots, list) or len(slots) != 256:
            raise ValueError(f"{name}: expected exactly 256 opcode slots")
        for slot in slots:
            if not isinstance(slot, dict) or slot.get("status") not in {"RESERVED", "MAPPED"}:
                raise ValueError(f"{name}: invalid opcode slot")
            if not isinstance(slot.get("encoding_ids"), list):
                raise ValueError(f"{name}: encoding_ids must be a list")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", type=Path,
                    default=Path("runtime/x86/instructions.json"))
    ap.add_argument("--definitions", type=Path,
                    default=Path("runtime/x86/instruction_definitions.json"))
    ap.add_argument("--encodings", type=Path,
                    default=Path("runtime/x86/instruction_encodings.json"))
    ap.add_argument("--opcode-map", type=Path,
                    default=Path("runtime/x86/opcode_map_i386.json"))
    ap.add_argument("--strict", action="store_true",
                    help="fail if the catalog contains non-EXECUTE entries")
    args = ap.parse_args()

    catalog = load_catalog(args.path)
    definitions = load_definitions(args.definitions)
    encodings = load_encodings(args.encodings)
    opcode_map = load_opcode_map(args.opcode_map)

    catalog_ids = {
        entry["mnemonic"].split("/")[0]
        for entries in catalog["instruction_sets"].values()
        for entry in entries
    }
    definition_ids = {item["id"] for item in definitions["instructions"]}
    encoding_instructions = {item["instruction"] for item in encodings["encodings"]}
    encoding_ids = {item["id"] for item in encodings["encodings"]}

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

    map_counts = {}
    map_references = set()
    decode_keys = set()
    for item in encodings["encodings"]:
        prefix = item.get("prefix_required")
        prefix_mask = 0x02 if prefix == "F2" else 0x04 if prefix == "F3" else 0
        prefix_value = prefix_mask
        needs_modrm = 1 if item.get("modrm", {}).get("required") else 0
        ext = item.get("modrm", {}).get("reg_extension", -1)
        key_base = (item["opcode_map"], needs_modrm, ext, prefix_mask, prefix_value)
        for opcode in item["opcode"]:
            key = key_base + (opcode.upper(),)
            if key in decode_keys:
                raise ValueError(
                    "ambiguous decode encoding for " + item["opcode_map"] +
                    " opcode 0x" + opcode.upper() + ": duplicate ModR/M/prefix slot involving " + item["id"]
                )
            decode_keys.add(key)
    for map_name, slots in opcode_map["maps"].items():
        mapped = 0
        for slot in slots:
            if slot["status"] == "MAPPED":
                mapped += 1
                for encoding_id in slot["encoding_ids"]:
                    map_references.add(encoding_id)
                    if encoding_id not in encoding_ids:
                        raise ValueError(
                            f"{map_name}: opcode slot references undefined encoding {encoding_id}"
                        )
        map_counts[map_name] = mapped

    # FCOMPP is an exact two-byte sequence (DE D9) handled by the decoder
    # rather than represented by a single opcode-map slot.
    missing_map_links = sorted(encoding_ids - map_references - {"FCOMPP"})
    if missing_map_links:
        raise ValueError("encodings missing from opcode map: " +
                         ", ".join(missing_map_links))

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
    print(f"opcode map primary:        {map_counts['primary']}")
    print(f"opcode map 0F:             {map_counts['escape_0f']}")
    print(f"opcode map 0F38:           {map_counts['escape_0f38']}")
    print(f"opcode map 0F3A:            {map_counts['escape_0f3a']}")

    if args.strict and counts["EXECUTE"] != total:
        print("STRICT: instruction catalog still contains non-executing entries")
        return 2

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
