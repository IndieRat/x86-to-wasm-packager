# XWASM x86 runtime roadmap

The x86 runtime is being developed toward running real 32-bit C/C++ Windows games in the browser. The project already has a host bridge for primitive graphics, input, and audio, so those facilities are compatibility targets rather than a new subsystem to invent.

## Existing platform foundation

- PE32 loading and image staging
- x86 integer/register/flags foundation
- decoder-owned semantic dispatch migration
- primitive graphics bridge: surface creation, clear, pixel, rectangle, present
- input bridge: message polling, quit, mouse movement/click tracking
- audio bridge: simple beep
- initial USER32/GDI32/KERNEL32 compatibility seeds
- VirtualAlloc/VirtualFree-style guest allocation path
- guest heap allocator
- deterministic CPU diagnostics and trace support

## v0.9 memory foundation — now implemented

- Explicit guest memory regions with read/write/execute permissions
- Image, heap, stack, and virtual-allocation region tracking
- WASM linear-memory growth checks for virtual allocations
- Checked memory validation API for future instruction/CRT migration
- Guest bulk copy/set primitives for CRT-style memory operations
- Virtual allocation reclamation and memory-region statistics

The existing instruction core continues using its proven low-level accessors while instruction families migrate onto the common checked memory layer. This avoids destabilizing the CPU foundation during the transition.

## Next compatibility work

1. Finish migrating CPU instruction families onto the decoder-owned dispatcher.
2. Expand the memory layer: reuse/free lists, protection transitions, larger mappings, and fault reporting.
3. Build the C runtime foundation: memcpy, memset, memcmp, allocation, basic string routines, startup/termination support, and calling-convention coverage.
4. Add a real monotonic timer host bridge and implement the common timing APIs used by games.
5. Add x87, then MMX and SSE/SSE2, using the common memory layer.
6. Expand Kernel32/User32/GDI32 compatibility around the APIs observed in real game binaries.
7. Add filesystem/resource and synchronization primitives as required by game fixtures.
8. Validate against small compiled C programs, then C++ programs, then increasingly realistic 32-bit games.

## Design goal

The intended stack is:

    C/C++ game
        -> x86/PE32 compatibility runtime
        -> CPU decoder + semantic dispatcher
        -> guest memory / CRT / Win32 compatibility
        -> XWASM host ABI
        -> browser graphics / input / audio / timers

The goal is compatibility with the assumptions made by ordinary 32-bit C/C++ software, not merely passing isolated instruction tests.
