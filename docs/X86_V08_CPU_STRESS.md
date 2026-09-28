# XWASM x86 v0.8 CPU foundation stress test

The CPU foundation stress fixture is intentionally separate from the v0.7 window/input/audio regression test.

## Build

    python tool/xwasm_build_x86_cpu_stress_test.py --output dist/x86-cpu-stress

This builds a fresh runtime.wasm, creates a synthetic PE32 payload, and packages both.

## Generate the browser runner

    python tool/xwasm_x86_cpu_stress_runner.py dist/x86-cpu-stress --output dist/x86-cpu-stress-runner.html

Serve the directory:

    python -m http.server 8000 --directory dist

Open http://localhost:8000/x86-cpu-stress-runner.html and select the dist/x86-cpu-stress directory.

## Success marker

The fixture places EAX = 0xC0DEF00D at the final HLT when every self-check passes.
The failure marker is EAX = 0xDEADC0DE.

The runner also reports EIP, opcode, CPU error, instruction count, and EFLAGS if execution fails.

## Current stress coverage

- MOV register/immediate
- ADD/SUB/CMP immediate
- JE/JNE
- AND/OR/XOR/TEST
- SHL/SHR/SAR
- IMUL
- MOVZX/MOVSX byte forms
- PUSH/POP
- ModR/M memory operands
- SIB addressing
- CALL/RET
- HLT

This is a regression gate for instructions already marked EXECUTE in runtime/x86/instructions.json. It does not claim that PLANNED or SYSTEM entries are implemented.

## Next CPU milestone

After this fixture passes, make the instruction database executable metadata: JSON encoding definitions -> decoder lookup -> operand decoding -> operation dispatch.

Before adding that layer, inspect the repository and relevant existing projects for any JSON command/metadata mechanism that can be reused without forcing XWASM into an incompatible schema.