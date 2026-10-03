#!/usr/bin/env python3
"""Build a deterministic 32-bit Win32/OpenGL compatibility Pong fixture."""
from __future__ import annotations
from pathlib import Path
import argparse, json, struct, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import pack_file
from xwasm.dll import pack_xapi_file  # noqa: E402

IMAGE_BASE=0x00400000
SECTION_RVA=0x1000
SECTION_RAW=0x200
SECTION_SIZE=0x3000

IMPORTS=[("USER32.dll",["CreateWindowExA","ShowWindow","GetDC","PeekMessageA"]),
         ("GDI32.dll",["ChoosePixelFormat","SetPixelFormat","SwapBuffers"]),
         ("OPENGL32.dll",["wglCreateContext","wglMakeCurrent","glViewport","glClearColor","glClear","glBegin","glEnd","glColor3f","glVertex2f"]),
         ("KERNEL32.dll",["Beep"])]
IAT_RVA=0x3000
# IAT slots are contiguous across DLLs (no terminators between DLLs). The
# loader walks the OFT (null-terminated per DLL) and writes IAT[i] for each
# entry, so only the OFT needs terminators. Generated code resolves slots by
# name from this table so code and import tables can never drift apart.
SLOT={}
_c=0
for _dll,_names in IMPORTS:
    for _n in _names:
        SLOT[_n]=IAT_RVA+_c; _c+=4


def pe():
    b=bytearray(SECTION_RAW+SECTION_SIZE)
    b[:2]=b"MZ"; struct.pack_into("<I",b,0x3c,0x80); b[0x80:0x84]=b"PE\0\0"
    struct.pack_into("<HHH",b,0x84,0x14c,1,0)
    struct.pack_into("<H",b,0x94,0xe0)
    oh=0x98; struct.pack_into("<H",b,oh,0x10b)
    struct.pack_into("<IIII",b,oh+16,SECTION_RVA,SECTION_RVA,SECTION_RVA,IMAGE_BASE)
    struct.pack_into("<II",b,oh+32,0x1000,0x200)
    struct.pack_into("<II",b,oh+56,0x4000,0x200)
    struct.pack_into("<I",b,oh+92,16)
    # Import data directory (index 1): the descriptor table is emitted at
    # RVA 0x1800 below. Without this directory entry the loader never scans
    # the IAT, so FF /2 would jump to the raw Hint/Name RVA instead of the
    # resolved XWASM API address.
    struct.pack_into("<II",b,oh+96+8,0x1800,0x64)
    sh=oh+0xe0; b[sh:sh+8]=b".text\0\0\0"
    struct.pack_into("<IIII",b,sh+8,SECTION_SIZE,SECTION_RVA,SECTION_SIZE,SECTION_RAW)
    struct.pack_into("<I",b,sh+36,0xe0000020)

    code=bytearray()
    def push(v): code.extend(b"\x68"+struct.pack("<I",v&0xffffffff))
    def call(name): code.extend(b"\xff\x15"+struct.pack("<I",IMAGE_BASE+SLOT[name]))

    for v in reversed([0,0,0,0x10000000,0,0,640,360,0,0,0,0]): push(v)
    call("CreateWindowExA"); code.extend(b"\x89\xc6")          # mov esi, eax (hwnd)
    push(1); code.extend(b"\x56"); call("ShowWindow")
    code.extend(b"\x56"); call("GetDC"); code.extend(b"\x89\xc3")  # mov ebx, eax (hdc)
    push(0); push(0); call("ChoosePixelFormat")
    push(0); push(0); push(0); call("SetPixelFormat")
    code.extend(b"\x53"); call("wglCreateContext"); code.extend(b"\x89\xc5")  # mov ebp, eax (hglrc)
    code.extend(b"\x53\x55"); call("wglMakeCurrent")
    for v in (360,640,0,0): push(v)
    call("glViewport")
    for bits in (0x00000000,0x00000000,0x00000000,0x3f800000): push(bits)
    call("glClearColor")
    # Three complete render/present/poll/audio frames.
    # Loop counter lives in EDI (not ECX): ECX/EDX are caller-saved in the
    # Windows ABI, so imported calls are allowed to clobber them.
    code.extend(b"\xbf\x03\x00\x00\x00")  # mov edi, 3
    loop_start = len(code)
    push(0x00004000); call("glClear")

    def color(r,g,b):
        for x in (b,g,r): push(x)
        call("glColor3f")
    def tri(x0,y0,x1,y1,x2,y2):
        push(4); call("glBegin")
        for x,y in ((x0,y0),(x1,y1),(x2,y2)):
            push(y); push(x); call("glVertex2f")
        call("glEnd")
    color(0x3f800000,0x3f800000,0x3f800000)
    tri(0xbf800000,0x3e800000,0xbf800000,0xbe800000,0xbf000000,0xbe800000)
    tri(0xbf000000,0xbe800000,0xbf000000,0x3e800000,0xbf800000,0x3e800000)
    tri(0x3f000000,0x3e800000,0x3f800000,0xbe800000,0x3f800000,0x3e800000)
    tri(0x3f000000,0x3e800000,0x3f000000,0x3e800000,0x3f000000,0xbe800000)
    color(0x3f000000,0x3f800000,0x3f000000)
    tri(0xbe800000,0xbe800000,0x00000000,0x3e800000,0x3e800000,0xbe800000)
    code.extend(b"\x53"); call("SwapBuffers")   # push ebx (hdc); SwapBuffers is stdcall(1 arg)
    push(90); push(660); call("Beep")
    for v in (1,0,0,0,0x00900000): push(v)       # PeekMessageA(lpMsg=0x900000, 0,0,0, PM_REMOVE)
    call("PeekMessageA")
    # The frame body is ~440 bytes, far beyond LOOP's rel8 reach, so use
    # dec edi / je done / jmp rel32 loop_start (all supported by the CPU).
    code.extend(b"\x4f")                    # dec edi
    code.extend(b"\x74\x05")                # je +5 (skip the jmp)
    jmp_end = len(code) + 5
    code.extend(b"\xe9" + struct.pack("<i", loop_start - jmp_end))
    code.extend(b"\xf4")                    # hlt
    b[SECTION_RAW:SECTION_RAW+len(code)]=code

    desc=0x1800; oft=0x1900; iat=IAT_RVA; names_base=0x1b00
    rva=names_base
    oft_cursor=0   # OFT: per-DLL tables, each null-terminated
    iat_cursor=0   # IAT: contiguous slots, matches SLOT[]
    for di,(dll,entries) in enumerate(IMPORTS):
        d=SECTION_RAW+(desc-SECTION_RVA)+di*20
        ot=oft+oft_cursor; it=iat+iat_cursor
        struct.pack_into("<IIIII",b,d,ot,0,0,rva,it)
        for j,name in enumerate(entries):
            assert it+j*4==SLOT[name], (name,hex(it+j*4),hex(SLOT[name]))
            struct.pack_into("<I",b,SECTION_RAW+(ot-SECTION_RVA)+j*4,rva)
            struct.pack_into("<I",b,SECTION_RAW+(it-SECTION_RVA)+j*4,rva)
            no=SECTION_RAW+(rva-SECTION_RVA); b[no:no+2]=b"\0\0"; nb=name.encode()+b"\0"; b[no+2:no+2+len(nb)]=nb
            rva += 0x40
        struct.pack_into("<I",b,SECTION_RAW+(ot-SECTION_RVA)+len(entries)*4,0)
        oft_cursor += (len(entries)+1)*4
        iat_cursor += len(entries)*4
        dll_name_rva=rva
        db=SECTION_RAW+(dll_name_rva-SECTION_RVA); dbs=dll.encode()+b"\0"; b[db:db+len(dbs)]=dbs; rva+=0x40
        struct.pack_into("<I",b,d+12,dll_name_rva)
    return bytes(b)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,default=Path("dist/xwasm-opengl-pong"))
    ap.add_argument("--runtime",type=Path,help="Existing XWASM runtime.xwasm to bundle.")
    a=ap.parse_args()

    root=a.output
    (root/"resources/__x86__").mkdir(parents=True,exist_ok=True)

    runtime=a.runtime
    if runtime is None:
        raise SystemExit("Pong requires an existing XWASM runtime. Pass --runtime PATH (the PowerShell xwasm_build command supplies xwasm-runtime).")
    runtime=runtime.resolve()
    if not runtime.is_file():
        raise SystemExit(f"XWASM runtime not found: {runtime}")

    (root/"runtime.xwasm").write_bytes(runtime.read_bytes())

    dll_api_dir=root/"dll_apis"
    dll_api_dir.mkdir(parents=True,exist_ok=True)
    canonical_xapis=("kernel32.xapi","user32.xapi","gdi32.xapi","opengl32.xapi","advapi32.xapi")
    seed_dir=ROOT/"runtime"/"x86"/"dlls"
    for api_name in canonical_xapis:
        seed=seed_dir/api_name
        if not seed.is_file():
            raise SystemExit(f"Canonical XAPI seed missing: {seed}")
        pack_xapi_file(seed,dll_api_dir/api_name)

    exe=root/"resources/__x86__/payload.exe"
    exe.write_bytes(pe())
    payload=root/"payload.xpl"
    pack_file(exe,payload,"xpl",compression="auto")
    exe.unlink()

    manifest={
        "format":"xwasm-package","format_version":1,
        "name":"XWASM-X86-OpenGL-Pong-Test","architecture":"x86",
        "runtime_kind":"x86-compatibility","runtime":"runtime.xwasm",
        "abi":"xwasm.host/1","resource_root":"resources/",
        "payload":"payload.xpl","payload_format":"XPL",
        "payload_architecture":"i386",
        "dll_api_format":"XWSC01/XAPI",
        "dll_api_manifests":["dll_apis/"+x for x in canonical_xapis],
        "bundled_dlls":["KERNEL32.dll","USER32.dll","GDI32.dll","OPENGL32.dll"],
        "execution_status":"opengl_window_input_audio_seed",
        "test_suite":{"name":"Win32/OpenGL Pong seed","tests":[
            "CreateWindowExA/ShowWindow/GetDC",
            "ChoosePixelFormat/SetPixelFormat",
            "wglCreateContext/wglMakeCurrent",
            "glViewport/glClearColor/glClear",
            "glBegin/glEnd/glColor3f/glVertex2f",
            "SwapBuffers","KERNEL32 Beep audio bridge",
            "XWASM input bridge availability"
        ]}
    }
    (root/"manifest.xwasm.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(root)
    print(f"Payload: {payload}")
    print("Payload format: XPL")
    print(f"Runtime: {root/'runtime.xwasm'}")
    print("XAPIs: " + ", ".join("dll_apis/"+x for x in canonical_xapis))


if __name__=="__main__":
    main()
