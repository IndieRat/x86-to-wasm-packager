#!/usr/bin/env python3
"""Build a deterministic 32-bit Win32/OpenGL compatibility Pong fixture."""
from pathlib import Path
import argparse, json, struct

IMAGE_BASE=0x00400000
SECTION_RVA=0x1000
SECTION_RAW=0x200
SECTION_SIZE=0x3000

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
    sh=oh+0xe0; b[sh:sh+8]=b".text\0\0\0"
    struct.pack_into("<IIII",b,sh+8,SECTION_SIZE,SECTION_RVA,SECTION_SIZE,SECTION_RAW)
    struct.pack_into("<I",b,sh+36,0xe0000020)

    code=bytearray()
    def push(v): code.extend(b"\x68"+struct.pack("<I",v&0xffffffff))
    def call(iat): code.extend(b"\xff\x15"+struct.pack("<I",IMAGE_BASE+iat))
    def mov_eax(v): code.extend(b"\xb8"+struct.pack("<I",v))
    def mov_edi(v): code.extend(b"\xbf"+struct.pack("<I",v))

    # Create/show window, obtain DC.
    for v in reversed([0,0,0,0x10000000,0,0,640,360,0,0,0,0]): push(v)
    call(0x3000); code.extend(b"\x89\xc6"); push(1); push_reg=b"\x56"; code.extend(push_reg); call(0x3004)
    code.extend(b"\x56"); call(0x3008); code.extend(b"\x89\xc3")

    # Minimal pixel-format/WGL setup.
    push(0); push(0); call(0x3010) # ChoosePixelFormat
    push(0); push(0); push(0); call(0x3014) # SetPixelFormat
    code.extend(b"\x53"); call(0x3018); code.extend(b"\x89\xc5") # wglCreateContext
    code.extend(b"\x53\x55"); call(0x301c) # wglMakeCurrent

    # Viewport + black clear.
    for v in (360,640,0,0): push(v)
    call(0x3020)
    for bits in (0x00000000,0x00000000,0x00000000,0x3f800000): push(bits)
    call(0x3024)
    push(0x00004000); call(0x3028)

    # Draw 2 paddles and a ball as triangles. GL_TRIANGLES=4.
    def color(r,g,b):
        for x in (b,g,r): push(x)
        call(0x3034)
    def tri(x0,y0,x1,y1,x2,y2):
        push(4); call(0x302c)
        for x,y in ((x0,y0),(x1,y1),(x2,y2)):
            push(y); push(x); call(0x3038)
        call(0x3030)
    color(0x3f800000,0x3f800000,0x3f800000)
    tri(0xbf800000,0x3e800000,0xbf800000,0xbe800000,0xbf000000,0xbe800000)
    tri(0xbf000000,0xbe800000,0xbf000000,0x3e800000,0xbf800000,0x3e800000)
    tri(0x3f000000,0x3e800000,0x3f800000,0xbe800000,0x3f800000,0x3e800000)
    tri(0x3f000000,0x3e800000,0x3f800000,0x3e800000,0x3f000000,0xbe800000)
    color(0x3f000000,0x3f800000,0x3f000000)
    tri(0xbe800000,0xbe800000,0x00000000,0x3e800000,0x3e800000,0xbe800000)
    call(0x3044) # SwapBuffers

    # Audio proof.
    push(90); push(660); call(0x3048)

    # Poll a small deterministic number of frames; host input wakes the bridge.
    mov_edi(0x00900000)
    # Exercise the browser input bridge once: PeekMessageA(MSG*, NULL, 0, 0, PM_REMOVE).
    for v in (1,0,0,0,0x00900000): push(v)
    call(0x300c)
    # HLT gives the shell a clean completion point after render/audio/input.
    code.extend(b"\xf4")
    b[SECTION_RAW:SECTION_RAW+len(code)]=code

    # Import table in the same section.
    desc=0x1800; oft=0x1900; iat=0x1a00; names_base=0x1b00
    dlls=[("USER32.dll",[("CreateWindowExA",0x3000),("ShowWindow",0x3004),("GetDC",0x3008),("PeekMessageA",0x300c)]),
          ("GDI32.dll",[("ChoosePixelFormat",0x3010),("SetPixelFormat",0x3014),("SwapBuffers",0x3044)]),
          ("OPENGL32.dll",[("wglCreateContext",0x3018),("wglMakeCurrent",0x301c),("glViewport",0x3020),("glClearColor",0x3024),("glClear",0x3028),("glBegin",0x302c),("glEnd",0x3030),("glColor3f",0x3034),("glVertex2f",0x3038)]),
          ("KERNEL32.dll",[("Beep",0x3048)])]
    rva=names_base; index=0
    for di,(dll,entries) in enumerate(dlls):
        d=SECTION_RAW+(desc-SECTION_RVA)+di*20
        ot=oft+di*0x100; it=iat+di*0x100
        struct.pack_into("<IIIII",b,d,ot,0,0,rva,it)
        for j,(name,_) in enumerate(entries):
            struct.pack_into("<I",b,SECTION_RAW+(ot-SECTION_RVA)+j*4,rva)
            struct.pack_into("<I",b,SECTION_RAW+(it-SECTION_RVA)+j*4,rva)
            no=SECTION_RAW+(rva-SECTION_RVA); b[no:no+2]=b"\0\0"; nb=name.encode()+b"\0"; b[no+2:no+2+len(nb)]=nb
            rva += 0x40
        # null thunk terminators
        struct.pack_into("<I",b,SECTION_RAW+(ot-SECTION_RVA)+len(entries)*4,0)
        struct.pack_into("<I",b,SECTION_RAW+(it-SECTION_RVA)+len(entries)*4,0)
        db=SECTION_RAW+(rva-SECTION_RVA); dbs=dll.encode()+b"\0"; b[db:db+len(dbs)]=dbs; rva+=0x40
        # fix descriptor DLL RVA
        struct.pack_into("<I",b,d+12,rva-0x40)
    struct.pack_into("<II",b,oh+96+8,desc,20*len(dlls)+20)
    return bytes(b)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    root=a.output; (root/"resources/__x86__").mkdir(parents=True,exist_ok=True)
    runtime=Path("dist/x86-runtime-v0.9/runtime.xwasm")
    if not runtime.exists(): raise SystemExit("build dist/x86-runtime-v0.9/runtime.xwasm first")
    (root/"runtime.xwasm").write_bytes(runtime.read_bytes())
    (root/"resources/__x86__/payload.exe").write_bytes(pe())
    manifest={"format":"xwasm-package","format_version":1,"name":"XWASM-X86-OpenGL-Pong-Test","architecture":"x86","runtime_kind":"x86-compatibility","runtime":"runtime.xwasm","abi":"xwasm.host/1","resource_root":"resources/","payload":"resources/__x86__/payload.exe","payload_format":"PE32","payload_architecture":"i386","bundled_dlls":["KERNEL32.dll","USER32.dll","GDI32.dll","OPENGL32.dll"],"execution_status":"opengl_window_input_audio_seed","test_suite":{"name":"Win32/OpenGL Pong seed","tests":["CreateWindowExA/ShowWindow/GetDC","ChoosePixelFormat/SetPixelFormat","wglCreateContext/wglMakeCurrent","glViewport/glClearColor/glClear","glBegin/glEnd/glColor3f/glVertex2f","SwapBuffers","KERNEL32 Beep audio bridge","XWASM input bridge availability"]}}
    (root/"manifest.xwasm.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(root)

if __name__=="__main__": main()
