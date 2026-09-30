import argparse
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests" / "fixtures" / "x87_float_fixture.c"
    output = Path(args.output).resolve()

    output.parent.mkdir(parents=True, exist_ok=True)

    llvm = Path(r"C:\Program Files\LLVM\bin")

    clang = llvm / "clang.EXE"
    lld_link = llvm / "lld-link.EXE"

    obj = output.with_suffix(".obj")

    compile_cmd = [
        str(clang),
        "--target=i686-pc-windows-msvc",
        "-ffreestanding",
        "-fno-builtin",
        "-fno-stack-protector",
        "-mno-stack-arg-probe",
        "-mno-sse",
        "-mno-sse2",
        "-mfpmath=387",
        "-O0",
        "-c",
        str(fixture),
        "-o",
        str(obj),
    ]

    print("Compiling x87 fixture:", " ".join(compile_cmd))
    subprocess.run(compile_cmd, check=True)

    link_cmd = [
        str(lld_link),
        "/machine:x86",
        "/subsystem:console",
        "/entry:main",
        "/base:0x400000",
        "/fixed",
        "/nodefaultlib",
        f"/out:{output}",
        str(obj),
    ]

    print("Linking x87 PE32:", " ".join(link_cmd))
    subprocess.run(link_cmd, check=True)

    obj.unlink(missing_ok=True)

    print(f"Created: {output}")


if __name__ == "__main__":
    raise SystemExit(main())
