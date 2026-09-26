import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List


MACHINE_I386 = 0x014C
PE_SIGNATURE = b"PE\0\0"
MZ_SIGNATURE = b"MZ"


@dataclass
class SectionInfo:
    name: str
    virtual_address: int
    virtual_size: int
    pointer_to_raw_data: int
    size_of_raw_data: int
    characteristics: int


@dataclass
class PackageManifest:
    bundle_version: str = "1.0"
    name: str = ""
    architecture: str = "x86"
    machine: str = "i386"
    file_size: int = 0
    entry_point: int = 0
    payload: str = "payload.bin"
    loader: str = "loader.js"
    html: str = "index.html"
    sha256: str = ""
    sections: List[dict] = field(default_factory=list)
    source_path: str = ""


def parse_pe32(file_path: Path) -> dict:
    data = file_path.read_bytes()
    if len(data) < 64:
        raise ValueError("File is too small to be a valid PE file")
    if not data.startswith(MZ_SIGNATURE):
        raise ValueError("Input is not a valid MZ executable")

    e_lfanew = int.from_bytes(data[0x3C:0x40], byteorder="little", signed=False)
    if e_lfanew + 24 > len(data):
        raise ValueError("PE header is truncated")

    if data[e_lfanew : e_lfanew + 4] != PE_SIGNATURE:
        raise ValueError("Input is not a valid PE32 executable")

    machine = int.from_bytes(data[e_lfanew + 4 : e_lfanew + 6], byteorder="little")
    if machine != MACHINE_I386:
        raise ValueError(f"Unsupported machine type: 0x{machine:04x}. Expected 32-bit x86 (0x014c)")

    number_of_sections = int.from_bytes(data[e_lfanew + 6 : e_lfanew + 8], byteorder="little")
    size_of_optional_header = int.from_bytes(data[e_lfanew + 20 : e_lfanew + 22], byteorder="little")
    characteristics = int.from_bytes(data[e_lfanew + 22 : e_lfanew + 24], byteorder="little")

    opt_offset = e_lfanew + 24
    data_directory_offset = opt_offset + size_of_optional_header
    if data_directory_offset > len(data):
        raise ValueError("Optional header exceeds file bounds")

    entry_point = int.from_bytes(data[opt_offset + 16 : opt_offset + 20], byteorder="little")
    image_base = int.from_bytes(data[opt_offset + 28 : opt_offset + 32], byteorder="little")
    section_alignment = int.from_bytes(data[opt_offset + 32 : opt_offset + 36], byteorder="little")
    file_alignment = int.from_bytes(data[opt_offset + 36 : opt_offset + 40], byteorder="little")

    section_table_offset = opt_offset + size_of_optional_header
    sections: List[SectionInfo] = []

    for index in range(number_of_sections):
        entry = section_table_offset + (index * 40)
        if entry + 40 > len(data):
            raise ValueError("Section table exceeds file bounds")

        name_bytes = data[entry : entry + 8].split(b"\0", 1)[0]
        name = name_bytes.decode("ascii", errors="replace")
        virtual_size = int.from_bytes(data[entry + 4 : entry + 8], byteorder="little")
        virtual_address = int.from_bytes(data[entry + 12 : entry + 16], byteorder="little")
        size_of_raw_data = int.from_bytes(data[entry + 16 : entry + 20], byteorder="little")
        pointer_to_raw_data = int.from_bytes(data[entry + 20 : entry + 24], byteorder="little")
        characteristics = int.from_bytes(data[entry + 36 : entry + 40], byteorder="little")

        sections.append(
            SectionInfo(
                name=name,
                virtual_address=virtual_address,
                virtual_size=virtual_size,
                pointer_to_raw_data=pointer_to_raw_data,
                size_of_raw_data=size_of_raw_data,
                characteristics=characteristics,
            )
        )

    return {
        "file_size": len(data),
        "entry_point": entry_point,
        "image_base": image_base,
        "section_alignment": section_alignment,
        "file_alignment": file_alignment,
        "machine": machine,
        "characteristics": characteristics,
        "sections": [asdict(section) for section in sections],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_loader_js() -> str:
    return '''
async function loadBundle(manifestUrl = './manifest.json') {
  const manifest = await fetch(manifestUrl).then((res) => {
    if (!res.ok) {
      throw new Error('Unable to fetch manifest.json');
    }
    return res.json();
  });

  const payloadUrl = manifest.payload || './payload.bin';
  const payload = await fetch(payloadUrl).then((res) => {
    if (!res.ok) {
      throw new Error('Unable to fetch payload');
    }
    return res.arrayBuffer();
  });

  return {
    manifest,
    binary: new Uint8Array(payload),
    status: 'loaded',
    boot(shell) {
      const mount = shell || document.body;
      mount.innerHTML = `
        <div style="font-family:monospace;background:#0b1020;color:#d5e7ff;padding:16px;border-radius:12px;border:1px solid #334155;max-width:960px;margin:24px auto;box-shadow:0 12px 32px rgba(0,0,0,0.25)">
          <h2 style="margin:0 0 8px 0;color:#7dd3fc;">x86 Boot Shell</h2>
          <p style="margin:0 0 12px 0;">Bundle loaded: <strong>${manifest.name}</strong></p>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">
            <div><strong>Arch</strong><div>${manifest.architecture}</div></div>
            <div><strong>Machine</strong><div>${manifest.machine}</div></div>
            <div><strong>Entry</strong><div>0x${manifest.entry_point.toString(16)}</div></div>
            <div><strong>Size</strong><div>${manifest.file_size} bytes</div></div>
          </div>
          <div style="margin-top:18px;padding:12px;border-radius:10px;background:#111827;border:1px solid #374151;white-space:pre-wrap;word-break:break-word;">
            Payload ready for an emulator bridge or WASM runner.
            Binary hash: ${manifest.sha256}
          </div>
        </div>
      `;
      return { manifest, binary: new Uint8Array(payload), status: 'booted' };
    }
  };
}

window.loadBundle = loadBundle;
'''.strip() + "\n"


def render_index_html() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>x86 Boot Loader</title>
    <style>
      body {
        margin: 0;
        font-family: system-ui, sans-serif;
        background: linear-gradient(180deg, #070b14, #101827 60%, #0f172a);
        color: #e2e8f0;
      }
      .page {
        max-width: 1100px;
        margin: 32px auto;
        padding: 24px;
      }
      .status {
        padding: 16px 18px;
        border-radius: 12px;
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid #334155;
        margin-bottom: 18px;
      }
      button {
        padding: 10px 16px;
        border-radius: 8px;
        border: 1px solid #2563eb;
        background: #2563eb;
        color: white;
        cursor: pointer;
        font-size: 14px;
      }
    </style>
  </head>
  <body>
    <div class="page">
      <div class="status" id="status">Loading package...</div>
      <button id="bootButton" type="button">Boot package</button>
    </div>

    <script src="./loader.js"></script>
    <script>
      const statusEl = document.getElementById('status');
      const bootButton = document.getElementById('bootButton');

      async function bootPackage() {
        try {
          statusEl.textContent = 'Fetching manifest and payload...';
          const bundle = await loadBundle('./manifest.json');
          statusEl.textContent = 'Bundle ready. Booting into shell...';
          bundle.boot(document.body);
        } catch (err) {
          statusEl.textContent = 'Boot failed: ' + err.message;
          console.error(err);
        }
      }

      bootButton.addEventListener('click', bootPackage);
      bootPackage();
    </script>
  </body>
</html>
'''.strip() + "\n"


def make_output_dir(output_dir: Path):
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def write_bundle(input_path: Path, output_dir: Path, bundle_name: str):
    meta = parse_pe32(input_path)
    manifest = PackageManifest(
        name=bundle_name,
        file_size=meta["file_size"],
        entry_point=meta["entry_point"],
        sha256=sha256_file(input_path),
        sections=meta["sections"],
        source_path=str(input_path),
    )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    payload_path = out_path / "payload.bin"
    shutil.copy2(input_path, payload_path)

    (out_path / "loader.js").write_text(render_loader_js(), encoding="utf-8")
    (out_path / "index.html").write_text(render_index_html(), encoding="utf-8")

    manifest_payload = {
        "bundle_version": manifest.bundle_version,
        "name": manifest.name,
        "architecture": manifest.architecture,
        "machine": "i386",
        "entry_point": manifest.entry_point,
        "file_size": manifest.file_size,
        "sections": manifest.sections,
        "payload": "payload.bin",
        "loader": "loader.js",
        "html": "index.html",
        "sha256": manifest.sha256,
        "source_path": manifest.source_path,
    }

    (out_path / "manifest.json").write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    return manifest_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package a PE32 x86 binary into an HTML/JS boot layout.")
    parser.add_argument("input", type=Path, help="Path to the source PE32 executable")
    parser.add_argument("--output", type=Path, default=Path("dist/package"), help="Directory to write the generated package")
    parser.add_argument("--name", default=None, help="Optional package name for the manifest")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"Error: input file does not exist: {args.input}", file=sys.stderr)
        return 2

    if not args.input.is_file():
        print(f"Error: input path is not a file: {args.input}", file=sys.stderr)
        return 2

    output_name = args.name or args.input.stem
    try:
        write_bundle(args.input, args.output, output_name)
    except Exception as exc:
        print(f"Packaging failed: {exc}", file=sys.stderr)
        return 1

    print(f"Package generated at: {args.output}")
    print(f"Open {args.output / 'index.html'} in a browser or serve the directory with python3 -m http.server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
