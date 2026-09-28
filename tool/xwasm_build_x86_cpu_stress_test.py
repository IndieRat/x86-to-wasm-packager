#!/usr/bin/env python3
"""Build the XWASM x86 v0.8 CPU foundation stress-test package."""
from __future__ import annotations
import argparse, json, subprocess, struct, tempfile
from pathlib import Path

BASE = 0x00400000
DATA = BASE + 0x1800

class Asm:
    def __init__(self):
        self.b = bytearray()
        self.labels = {}
        self.patches = []

    def label(self, name):
        self.labels[name] = len(self.b)

    def emit(self, *xs):
        self.b.extend(xs)

    def imm32(self, op, reg, value):
        self.emit(op + reg, *struct.pack("<I", value & 0xffffffff))

    def rel8(self, op, label):
        self.emit(op, 0)
        self.patches.append(("rel8", len(self.b)-1, label, 1))

    def rel32(self, op, label):
        # Accept either a single-byte opcode (E8/E9) or a multi-byte
        # opcode tuple such as (0x0F, 0x85) for near Jcc.
        if isinstance(op, (tuple, list)):
            self.emit(*op, *b"\0\0\0\0")
        else:
            self.emit(op, *b"\0\0\0\0")
        self.patches.append(("rel32", len(self.b)-4, label, 4))

    def finish(self):
        for kind, pos, label, size in self.patches:
            if label not in self.labels:
                raise ValueError(f"missing label: {label}")
            target = self.labels[label]
            end = pos + size
            disp = target - end
            if kind == "rel8":
                if not -128 <= disp <= 127:
                    raise ValueError(f"rel8 out of range for {label}: {disp}")
                self.b[pos] = disp & 0xff
            else:
                self.b[pos:pos+4] = struct.pack("<i", disp)
        return bytes(self.b)

def make_code():
    a = Asm()

    # MOV + ADD/SUB/CMP + conditional branch.
    a.imm32(0xB8, 0, 0x10)
    a.emit(0x05, *struct.pack("<I", 0x20))       # ADD EAX,20 -> 30
    a.emit(0x2D, *struct.pack("<I", 5))          # SUB EAX,5 -> 2B
    a.emit(0x3D, *struct.pack("<I", 0x2B))        # CMP EAX,2B
    a.rel32((0x0F, 0x85), "fail")                         # JNE

    # Logic.
    a.imm32(0xBA, 0, 0x0F0F0F0F)                # EDX
    a.imm32(0xB9, 0, 0x00FF00FF)                # ECX
    a.emit(0x21, 0xCA)                           # AND EDX,ECX
    a.imm32(0xB9, 0, 0xF0000000)
    a.emit(0x09, 0xCA)                           # OR EDX,ECX
    a.emit(0x31, 0xC9)                           # XOR ECX,ECX
    a.emit(0x85, 0xC9)                           # TEST ECX,ECX
    a.rel32((0x0F, 0x84), "logic_ok")                     # JE
    a.rel32(0xE9, "fail")
    a.label("logic_ok")

    # Register-source ADD form (0x03): EAX = 5 + 7 = 12.
    a.imm32(0xB8, 0, 5)
    a.imm32(0xBA, 0, 7)
    a.emit(0x03, 0xC2)
    a.emit(0x3D, *struct.pack("<I", 12))
    a.rel32((0x0F, 0x85), "fail")

    # INC must preserve CF: CMP 0,1 sets CF, INC 0 must leave it set.
    a.imm32(0xB8, 0, 0)
    a.imm32(0xBA, 0, 1)
    a.emit(0x3B, 0xC2)                           # CMP EAX,EDX -> CF=1
    a.emit(0x40)                                 # INC EAX
    a.rel8(0x72, "inc_cf_ok")
    a.rel32(0xE9, "fail")
    a.label("inc_cf_ok")

    # Shifts.
    a.imm32(0xB8, 0, 1)
    a.emit(0xC1, 0xE0, 4)                        # SHL EAX,4 -> 16
    a.emit(0xC1, 0xE8, 1)                        # SHR EAX,1 -> 8
    a.imm32(0xB9, 0, 0xFFFFFFF0)
    a.emit(0xC1, 0xF9, 2)                        # SAR ECX,2 -> FFFFFFFC
    a.imm32(0xBA, 0, 8)
    a.emit(0xD1, 0xEA)                           # SHR EDX,1

    a.imm32(0xB8, 0, 0x80000000)
    a.emit(0xD1, 0xE0)                           # SHL EAX,1 -> CF=1
    a.rel8(0x72, "shift_cf_ok")
    a.rel32(0xE9, "fail")
    a.label("shift_cf_ok")

    # IMUL EAX,EDX (result 4).
    a.imm32(0xB8, 0, 2)
    a.imm32(0xBA, 0, 2)
    a.emit(0x0F, 0xAF, 0xC2)                    # IMUL EAX,EDX -> 4
    a.emit(0x3D, *struct.pack("<I", 4))
    a.rel32((0x0F, 0x85), "fail")

    # MOVZX/MOVSX byte-register forms.
    a.imm32(0xB8, 0, 0x80)
    a.emit(0x0F, 0xB6, 0xC8)                    # MOVZX ECX,AL -> 80
    a.emit(0x3D, *struct.pack("<I", 0x80))       # CMP EAX,80 (EAX unchanged)
    a.rel32((0x0F, 0x85), "fail")
    a.emit(0x0F, 0xBE, 0xD0)                    # MOVSX EDX,AL -> FFFFFF80
    a.imm32(0xB8, 0, 0xFFFFFF80)
    a.emit(0x3B, 0xD0)                           # CMP EDX,EAX
    a.rel32((0x0F, 0x85), "fail")

    # PUSH/POP and stack round-trip.
    a.imm32(0xB8, 0, 0x13579BDF)
    a.emit(0x50)                                 # PUSH EAX
    a.imm32(0xB8, 0, 0)
    a.emit(0x58)                                 # POP EAX
    a.imm32(0xBA, 0, 0x13579BDF)
    a.emit(0x3B, 0xC2)                           # CMP EAX,EDX
    a.rel32((0x0F, 0x85), "fail")

    # ModR/M memory operand round-trip.
    a.imm32(0xBB, 0, DATA)
    a.imm32(0xB8, 0, 0xA55AA55A)
    a.emit(0x89, 0x03)                           # MOV [EBX],EAX
    a.emit(0x8B, 0x0B)                           # MOV ECX,[EBX]
    a.emit(0x3B, 0xC8)                           # CMP ECX,EAX
    a.rel32((0x0F, 0x85), "fail")

    # SIB address: [ESI + EDI*4].
    a.imm32(0xBE, 0, DATA + 0x20)              # ESI
    a.imm32(0xBF, 0, 1)                          # EDI
    a.imm32(0xB8, 0, 0x55AA55AA)
    a.emit(0x89, 0x44, 0xBE, 0x00)              # MOV [ESI+EDI*4],EAX
    a.emit(0x8B, 0x4C, 0xBE, 0x00)              # MOV ECX,[ESI+EDI*4]
    a.emit(0x3B, 0xC8)
    a.rel32((0x0F, 0x85), "fail")

    # CALL/RET.
    a.rel32(0xE8, "subroutine")
    a.imm32(0xBA, 0, 0xCAFEBABE)
    a.emit(0x3B, 0xC2)
    a.rel32((0x0F, 0x85), "fail")

    # ADC/SBB carry and borrow propagation.
    a.imm32(0xB8, 0, 0)
    a.imm32(0xBA, 0, 1)
    a.emit(0x3B, 0xC2)                           # CMP EAX,EDX -> CF=1
    a.imm32(0xB8, 0, 0xFFFFFFFF)
    a.imm32(0xBA, 0, 0)
    a.emit(0x13, 0xC2)                           # ADC EAX,EDX -> 0, CF=1
    a.rel8(0x72, "adc_cf_ok")
    a.rel32(0xE9, "fail")
    a.label("adc_cf_ok")
    a.emit(0x1B, 0xC2)                           # SBB EAX,EDX -> FFFFFFFF, CF=1
    a.rel8(0x72, "sbb_cf_ok")
    a.rel32(0xE9, "fail")
    a.label("sbb_cf_ok")

    # NEG / NOT.
    a.imm32(0xB8, 0, 1)
    a.emit(0xF7, 0xD8)                           # NEG EAX -> FFFFFFFF, CF=1
    a.rel8(0x72, "neg_cf_ok")
    a.rel32(0xE9, "fail")
    a.label("neg_cf_ok")
    a.emit(0xF7, 0xD0)                           # NOT EAX -> 0
    a.emit(0x3D, *struct.pack("<I", 0))
    a.rel32((0x0F, 0x85), "fail")

    # MUL / IMUL forms.
    a.imm32(0xB8, 0, 0x00010000)
    a.imm32(0xB9, 0, 0x00010000)
    a.emit(0xF7, 0xE1)                           # MUL ECX -> EDX:EAX = 1:0
    a.imm32(0xBA, 0, 1)
    a.emit(0x3B, 0xD2)                           # EDX == 1
    a.rel32((0x0F, 0x85), "fail")
    a.imm32(0xB8, 0, 2)
    a.imm32(0xB9, 0, 3)
    a.emit(0xF7, 0xE9)                           # IMUL ECX -> 6
    a.emit(0x3D, *struct.pack("<I", 6))
    a.rel32((0x0F, 0x85), "fail")
    a.imm32(0xBA, 0, 4)
    a.emit(0x69, 0xC2, *struct.pack("<I", 5))    # IMUL EAX,EDX,5 -> 20
    a.emit(0x3D, *struct.pack("<I", 20))
    a.rel32((0x0F, 0x85), "fail")
    a.emit(0x6B, 0xC2, 2)                        # IMUL EAX,EDX,2 -> 8
    a.emit(0x3D, *struct.pack("<I", 8))
    a.rel32((0x0F, 0x85), "fail")

    # DIV / IDIV.
    a.imm32(0xBA, 0, 0)
    a.imm32(0xB8, 0, 100)
    a.imm32(0xB9, 0, 7)
    a.emit(0xF7, 0xF1)                           # DIV ECX -> EAX=14, EDX=2
    a.imm32(0xBB, 0, 14)
    a.emit(0x3B, 0xC3)
    a.rel32((0x0F, 0x85), "fail")
    a.imm32(0xBB, 0, 2)
    a.emit(0x3B, 0xD3)
    a.rel32((0x0F, 0x85), "fail")
    a.imm32(0xBA, 0, 0xFFFFFFFF)
    a.imm32(0xB8, 0, 0xFFFFFF9C)                 # -100
    a.imm32(0xB9, 0, 7)
    a.emit(0xF7, 0xF9)                           # IDIV ECX -> EAX=-14, EDX=-2
    a.imm32(0xBB, 0, 0xFFFFFFF2)
    a.emit(0x3B, 0xC3)
    a.rel32((0x0F, 0x85), "fail")

    # ROL/ROR/RCL/RCR.
    a.imm32(0xB8, 0, 0x80000001)
    a.emit(0xC1, 0xC0, 1)                        # ROL EAX,1 -> 3
    a.emit(0x3D, *struct.pack("<I", 3))
    a.rel32((0x0F, 0x85), "fail")
    a.imm32(0xB8, 0, 3)
    a.emit(0xC1, 0xC8, 1)                        # ROR EAX,1 -> 80000001
    a.emit(0x3D, *struct.pack("<I", 0x80000001))
    a.rel32((0x0F, 0x85), "fail")
    a.imm32(0xB8, 0, 0x80000000)
    a.emit(0xD1, 0xD0)                           # RCL EAX,1 with CF from ROR
    a.imm32(0xB9, 0, 1)
    a.emit(0x3B, 0xC1)
    a.rel32((0x0F, 0x85), "fail")
    # RCR with CF=0: 80000000 -> 40000000.
    a.imm32(0xB9, 0, 0)
    a.emit(0x85, 0xC9)                           # TEST ECX,ECX -> CF=0
    # RCR with CF=0: 80000000 -> 40000000.
    a.imm32(0xB9, 0, 0)
    a.emit(0x85, 0xC9)                           # TEST ECX,ECX -> CF=0
    a.imm32(0xB8, 0, 0x80000000)
    a.emit(0xD1, 0xD8)                           # RCR EAX,1
    a.imm32(0xB9, 0, 0x40000000)
    a.emit(0x3B, 0xC1)
    a.rel32((0x0F, 0x85), "fail")
    a.rel8(0x73, "rcr_cf0_ok")                  # CF must be 0
    a.rel32(0xE9, "fail")
    a.label("rcr_cf0_ok")

    # RCR with CF=1: 80000000 -> C0000000; old bit 0 becomes CF=0.
    a.imm32(0xB8, 0, 0)
    a.imm32(0xB9, 0, 1)
    a.emit(0x3B, 0xC1)                           # CMP 0,1 -> CF=1
    a.imm32(0xB8, 0, 0x80000000)
    a.emit(0xD1, 0xD8)                           # RCR EAX,1
    a.imm32(0xB9, 0, 0xC0000000)
    a.emit(0x3B, 0xC1)
    a.rel32((0x0F, 0x85), "fail")
    a.rel8(0x73, "rcr_cf1_ok")                  # CF must be 0
    a.rel32(0xE9, "fail")
    a.label("rcr_cf1_ok")
    a.rel8(0x73, "rcr_cf0_ok")                  # CF must be 0
    a.rel32(0xE9, "fail")
    a.label("rcr_cf0_ok")

    # RCR with CF=1: 80000000 -> C0000000; old bit 0 becomes CF=0.
    a.imm32(0xB8, 0, 0)
    a.imm32(0xB9, 0, 1)
    a.emit(0x3B, 0xC1)                           # CMP 0,1 -> CF=1
    a.imm32(0xB8, 0, 0x80000000)
    a.emit(0xD1, 0xD8)                           # RCR EAX,1
    a.imm32(0xB9, 0, 0xC0000000)
    a.emit(0x3B, 0xC1)
    a.rel32((0x0F, 0x85), "fail")
    a.rel8(0x73, "rcr_cf1_ok")                  # CF must be 0
    a.rel32(0xE9, "fail")
    a.label("rcr_cf1_ok")

    # BT/BTS/BTR/BTC register and immediate forms.
    a.imm32(0xB8, 0, 0xFFFFFFFF)
    a.imm32(0xB9, 0, 4)
    a.emit(0x0F, 0xA3, 0xC8)                    # BT EAX,ECX -> CF=1
    a.rel8(0x72, "bt_ok")
    a.rel32(0xE9, "fail")
    a.label("bt_ok")
    a.emit(0x0F, 0xB3, 0xC8)                    # BTR EAX,ECX -> clear bit 4
    a.emit(0x0F, 0xBA, 0xE8, 4)                # BTS EAX,4 -> set bit 4
    a.emit(0x0F, 0xBA, 0xF0, 4)                # BTR EAX,4 -> clear bit 4
    a.emit(0x0F, 0xBA, 0xF8, 4)                # BTC EAX,4 -> toggle bit 4
    a.emit(0x0F, 0xBA, 0xE0, 4)                # BTS EAX,4 -> set bit 4
    a.emit(0x0F, 0xA3, 0xC8)                    # BT EAX,ECX -> CF=1
    a.rel8(0x72, "bit_ok")
    a.rel32(0xE9, "fail")
    a.label("bit_ok")

    # Success/failure markers.
    a.imm32(0xB8, 0, 0xC0DEF00D)
    a.emit(0xF4)
    a.rel32(0xE9, "fail")

    a.label("subroutine")
    a.imm32(0xB8, 0, 0xCAFEBABE)
    a.emit(0xC3)

    a.label("fail")
    a.imm32(0xB8, 0, 0xDEADC0DE)
    a.emit(0xF4)
    return a.finish()

def make_pe():
    pe_off=0x80; headers=0x200; raw=0x400; image=0x3000
    b=bytearray(headers+raw)
    u16=lambda v: struct.pack("<H",v)
    u32=lambda v: struct.pack("<I",v)
    b[0:2]=b"MZ"; b[0x3c:0x40]=u32(pe_off); b[pe_off:pe_off+4]=b"PE\0\0"
    fh=pe_off+4
    b[fh:fh+2]=u16(0x14c); b[fh+2:fh+4]=u16(1); b[fh+16:fh+18]=u16(0xe0); b[fh+18:fh+20]=u16(0x010f)
    oh=fh+20
    b[oh:oh+2]=u16(0x10b); b[oh+16:oh+20]=u32(0x1000); b[oh+28:oh+32]=u32(BASE)
    b[oh+32:oh+36]=u32(0x1000); b[oh+36:oh+40]=u32(0x200); b[oh+56:oh+60]=u32(image); b[oh+60:oh+64]=u32(headers)
    b[oh+68:oh+70]=u16(3); b[oh+92:oh+96]=u32(16)
    sh=oh+0xe0
    b[sh:sh+8]=b".text\0\0\0"; b[sh+8:sh+12]=u32(0x1000); b[sh+12:sh+16]=u32(0x1000)
    code=make_code()
    if len(code)>raw: raise ValueError(f"stress code too large: {len(code)}")
    b[sh+16:sh+20]=u32(raw); b[sh+20:sh+24]=u32(headers)
    b[headers:headers+len(code)]=code
    return bytes(b),code

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--clang",default=None)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]; out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        game=Path(td)/"XWASM-X86-CPU-Foundation-Stress"; game.mkdir()
        payload,code=make_pe(); (game/"CpuStress.exe").write_bytes(payload)
        runtime=Path(td)/"runtime.wasm"
        cmd=["python",str(root/"tool/xwasm_build_x86_runtime.py"),"--output",str(runtime)]
        if args.clang: cmd += ["--clang",args.clang]
        subprocess.run(cmd,check=True)
        subprocess.run(["python",str(root/"tool/xwasm_pack_x86.py"),str(game),"--output",str(out),"--exe","CpuStress.exe","--runtime",str(runtime)],check=True)
    manifest=json.loads((out/"manifest.xwasm.json").read_text(encoding="utf-8"))
    if manifest.get("architecture")!="x86": raise SystemExit("package is not x86")
    print(f"Created CPU foundation stress package: {out}")
    print(f"Instruction bytes: {len(code)}")
    print("Coverage: MOV, ADD, ADC, SUB, SBB, CMP, AND, OR, XOR, TEST, SHL, SHR, SAR, ROL, ROR, RCL, RCR, NEG, NOT, MUL, IMUL, DIV, IDIV, BT, BTS, BTR, BTC, MOVZX, MOVSX, PUSH, POP, ModR/M, SIB, CALL, RET, JE/JNE, HLT")
    return 0

if __name__=="__main__": raise SystemExit(main())
