# XWASM v0.8 CPU Foundation

## Goal

v0.8 starts by making the 32-bit x86 CPU layer measurable and expandable before adding the next Windows subsystems.

The target is i386 user-mode compatibility, not a claim that privileged IA-32 instructions can run inside a browser. Intel's instruction reference covers general-purpose instructions, x87, MMX/SSE-family instructions, and system instructions; XWASM catalogs those families while implementing them according to their usefulness to ordinary Win32 applications.

## Instruction database

The file runtime/x86/instructions.json is the source-of-truth catalog.

Each instruction has a status:

- EXECUTE: implemented and covered by a runtime test.
- DECODE: decoder work exists but semantics are incomplete.
- PLANNED: catalogued but not implemented yet.
- SYSTEM: exists architecturally but is privileged/system-facing.

Validate it with:

    python3 tool/xwasm_validate_instruction_db.py

For a strict coverage check:

    python3 tool/xwasm_validate_instruction_db.py --strict

Strict mode is expected to fail during v0.8 development; it becomes a release gate only when the required user-mode baseline is complete.

## CPU expansion order

1. Decoder correctness
   - prefixes
   - opcode maps (00-FF, 0F xx, later additional maps)
   - ModR/M
   - SIB
   - displacement/immediate sizes
   - operand/address-size behavior

2. Integer execution
   - arithmetic and flags
   - logic
   - shifts/rotates
   - multiply/divide
   - stack
   - comparisons
   - conditional control flow

3. Memory operands
   - every supported integer instruction must work with register and memory forms
   - unaligned 8/16/32-bit accesses
   - page/permission faults routed through the exception layer

4. x87
   - stack/register model
   - control/status words
   - common game math instructions

5. SIMD
   - implement only after instruction traces show a real need
   - keep MMX/SSE state separate from the integer register file

## Failure diagnostics

An unsupported instruction is a CPU compatibility event, not a generic WASM crash.

The runtime should report:

    CPU UNSUPPORTED
    EIP
    opcode bytes
    prefix bytes
    ModR/M
    SIB
    registers
    EFLAGS
    instruction-db family/status

That diagnostic is what will let us move from "the game crashed" to "the game reached this exact x86 instruction."

## Memory boundary

The CPU layer will not use the host WASM linear memory as if it were the guest's entire Windows address space.

A 32-bit process has a 4 GB virtual address space, while Windows normally divides that space between user and system regions, and virtual memory is page-based. XWASM therefore needs a guest address-space abstraction rather than tying guest allocation directly to the host machine's physical RAM.

The first CPU bundle establishes the interface:

    x86 instruction
          |
          v
    guest memory access
          |
          +--> mapped page
          |       |
          |       +--> host backing
          |
          +--> unmapped/protection fault
                  |
                  v
             exception dispatcher

This is the seam that later bundles for CRT, files, threads, and Win32 APIs will use.

## Release gate for CPU foundation

Before calling the CPU portion of v0.8 complete, the fixture suite should be able to prove:

- PE32 load and relocation
- complete register/flag diagnostics
- ModR/M + SIB addressing
- integer arithmetic/logic
- shifts/rotates
- multiply/divide
- stack and calls
- all common conditional branches
- byte/word/dword memory operands
- deliberate invalid/unsupported opcode reporting
- deterministic instruction-db validation

The real-game gate is separate: a game is allowed to expose missing instructions and drive the next implementation slice.


## JSON definition layers

The high-level catalog remains at `runtime/x86/instructions.json`. v0.8 now also has two machine-readable layers:

- `runtime/x86/instruction_definitions.json` — one semantic definition per instruction, including instruction family, supported forms, operand kinds, and flag effects.
- `runtime/x86/instruction_encodings.json` — concrete legacy i386 encodings, including opcode bytes, opcode maps, ModR/M requirements and extensions, operand sources, immediate widths, sign extension, and relative branches.

The intended pipeline is:

    instructions.json
          |
          +--> instruction_definitions.json
          |       semantic identity / forms / flags
          |
          +--> instruction_encodings.json
                  exact byte-level encoding
                          |
                          v
                    compiled lookup tables
                          |
                          v
                       decoder
                          |
                          v
                    execution handler

The JSON files are the authoring/source format. The runtime should eventually compile them into compact lookup tables rather than parse JSON for every guest instruction.

The encoding structure follows the same useful separation used by Intel XED: decoded instructions have structured operands and encoding data, while the byte-level encoding rules select the concrete form. Intel documents ModR/M, operand encoding, and opcode-map information separately in Volume 2. 


## Full encoding map and Intel-assisted authoring

The v0.8 CPU data model now separates the semantic instruction list from the byte-space map.

- `runtime/x86/opcode_map_i386.json` materializes 256 slots for the primary map, 256 for `0F`, 256 for `0F 38`, and 256 for `0F 3A`.
- `runtime/x86/encoding_schema.json` defines the byte-level pieces the decoder must understand: legacy prefixes, opcode maps, ModR/M, SIB, displacement, immediates, relative branches, operand size, address size, implicit operands, and encoding constraints.
- `tool/xwasm_import_xed_isa.py` is an optional build-time importer for Intel XED's machine-readable ISA patterns.

Intel's current SDM identifies Volume 2 as the full instruction-set reference and explicitly documents instruction format, prefixes, ModR/M, SIB, displacement/immediate bytes, and opcode maps. Intel XED is an encoder/decoder library and its source uses generated machine-readable instruction tables. XWASM uses those resources as authoring/verification input; the browser runtime does not contact Intel.

### Offline/reproducible workflow

Download or otherwise provide an `xed-isa.txt` snapshot, then run:

    python3 tool/xwasm_import_xed_isa.py --input path/to/xed-isa.txt

This writes:

    runtime/x86/xed_isa_patterns.json

For a one-shot source refresh, the importer can use its configured Intel XED source URL:

    python3 tool/xwasm_import_xed_isa.py

The generated XED snapshot is reference data. It does not automatically mark XWASM instructions executable. An instruction still needs a semantic definition, an XWASM encoding record, decoder support, execution semantics, and a fixture test before it becomes `EXECUTE`.

Validate all current layers with:

    python3 tool/xwasm_validate_instruction_db.py

The next decoder implementation can therefore consume the four-level pipeline:

    XED/SDM reference
             |
             v
      XWASM JSON authoring
             |
             +--> semantic definitions
             +--> concrete encodings
             +--> complete opcode maps
             |
             v
       generated decoder tables
             |
             v
          x86 CPU
