# XWASM Static Recompilation

XWASM now has a second execution model: `architecture = "x86-recompiled"`.

Instead of shipping a PE32 and interpreting it in the browser, the PE is build input:

```
PE32 + imports
    -> static x86 -> C/IR -> wasm32 backend
    -> boot.wasm
    -> guest.segs.bin
    -> resources/
    -> XWASM package
```

The browser executes ordinary WebAssembly. The original PE is recorded only as build provenance.

## Package

```
Game.xwasm/
  manifest.xwasm.json
  boot.wasm
  guest.segs.bin
  index.html
  bridge.js                 # optional
  resources/
```

The manifest uses `architecture: "x86-recompiled"`, plus `module` and `image`.

## Package existing translated artifacts

```powershell
python tool/xwasm_recomp_pack.py `
  "C:\Games\MyGame" `
  --exe "Game.exe" `
  --module ".\build\boot.wasm" `
  --image ".\build\guest.segs.bin" `
  --output ".\dist\MyGame.xwasm"

python tool/xwasm_recomp_runner.py ".\dist\MyGame.xwasm"
```

## Plug in a translator backend

The orchestration script provides a stable interface for the actual static recompiler:

```powershell
python tool/xwasm_recomp.py `
  "C:\Games\MyGame" `
  --exe "Game.exe" `
  --output ".\dist\MyGame.xwasm" `
  --backend-command "python C:\my-recompiler\build.py"
```

The backend receives:

- `XWASM_GAME_DIR`
- `XWASM_EXE`
- `XWASM_WORK_DIR`
- `XWASM_OUTPUT_WASM`
- `XWASM_OUTPUT_IMAGE`

It must emit the last two files before returning successfully.

This boundary intentionally lets the static-recompilation backend evolve separately from the package format.

## Why this model

The existing x86 package is:

```
PE32 -> XWASM x86 runtime -> browser
```

The recompiled package is:

```
PE32 -> static recompilation -> WASM -> browser host
```

This is much closer to the architecture of the working browser port that motivated this change. It also means the final game logic can run as native wasm32 code instead of interpreting every x86 instruction at runtime.

The existing x86 runtime remains useful as a fallback and as a correctness oracle while the static lifter is being developed.

## Offline

The generated shell has no CDN dependency. Package contents are local.

Use a local HTTP server rather than `file://` for WASM/fetch compatibility:

```powershell
cd .\dist\MyGame.xwasm
python -m http.server 8000
```

## Backend roadmap

1. PE analysis and import/export inventory.
2. Control-flow recovery and x86 lifting.
3. x86 machine-state representation.
4. Translation to C or typed IR.
5. wasm32 compilation with Emscripten/Clang.
6. Preferred-address guest image generation.
7. Windows API host boundary.
8. Resource packaging and browser shell.
9. Differential testing against the existing XWASM x86 runtime.
