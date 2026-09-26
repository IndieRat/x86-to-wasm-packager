# Usage

## Game folder

```bash
python3 tool/packager.py ./MyGame --output ./dist/MyGame
```

The tool searches the folder for a `.exe`, prefers a root-level `Game.exe` or an executable matching the folder name, validates PE32/i386, stores the selected executable as `payload.bin`, and copies every other file into `resources/`.

## Multiple executables

```bash
python3 tool/packager.py ./MyGame \
  --exe bin/GameLauncher.exe \
  --output ./dist/MyGame
```

## Add the actual execution runtime

```bash
python3 tool/packager.py ./MyGame \
  --output ./dist/MyGame \
  --runtime-wasm ./runtime.wasm \
  --bridge ./bridge.js
```

The resulting package contains `runtime.wasm` and optionally `bridge.js`.

## Package layout

```text
index.html
loader.js
manifest.json
payload.bin
runtime.wasm   # if supplied
bridge.js      # if supplied
resources/     # copied game files
```

## What is and is not converted

The packager converts the **folder layout** into the package format and validates/extracts PE metadata. It does not itself translate x86 instructions to WASM.

The runtime must provide actual x86 execution and the compatibility layer needed by the target game.
