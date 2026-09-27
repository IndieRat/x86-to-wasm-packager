// XWASM X86 Runtime v0.2
#include <stdint.h>

extern void xwasm_log(int32_t level,int32_t ptr,int32_t len);
#define HEAP_BASE_FALLBACK 0x100000u
extern unsigned char __heap_base[];
#define IMAGE_BASE 0x00400000u
#define MEM8(p) (*(volatile uint8_t *)(uintptr_t)(p))

/* 32-bit x86 register order: EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI. */
enum { R_EAX=0,R_ECX,R_EDX,R_EBX,R_ESP,R_EBP,R_ESI,R_EDI };
#define CF 0x00000001u
#define PF 0x00000004u
#define ZF 0x00000040u
#define SF 0x00000080u
#define OF 0x00000800u

static uint32_t heap=HEAP_BASE_FALLBACK,image_base=0,image_size=0,entry=0,eip=0,steps=0,loaded=0;
static uint32_t dll_count=0,import_count=0,load_error=0,last_load_ptr=0,last_load_size=0;
static uint32_t regs[8],eflags=0x00000002u;
static uint32_t halted=0,cpu_error=0;

static uint16_t rd16(uint32_t p){return (uint16_t)MEM8(p)|((uint16_t)MEM8(p+1)<<8);}
static uint32_t rd32(uint32_t p){return (uint32_t)MEM8(p)|((uint32_t)MEM8(p+1)<<8)|((uint32_t)MEM8(p+2)<<16)|((uint32_t)MEM8(p+3)<<24);}
static void wr32(uint32_t p,uint32_t v){MEM8(p)=(uint8_t)v;MEM8(p+1)=(uint8_t)(v>>8);MEM8(p+2)=(uint8_t)(v>>16);MEM8(p+3)=(uint8_t)(v>>24);}
static uint32_t al4(uint32_t x){return(x+3u)&~3u;}
static void wr8(uint32_t p,uint8_t v){MEM8(p)=v;}
static void copy_bytes(uint32_t d,uint32_t s,uint32_t n){for(uint32_t i=0;i<n;i++)wr8(d+i,MEM8(s+i));}
static void loglit(const char*s){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}
static void loghex(const char*s,uint32_t v){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);wr8(p++,'0');wr8(p++,'x');for(int i=7;i>=0;i--){uint8_t x=(v>>(i*4))&15u;wr8(p++,(uint8_t)(x<10?'0'+x:'A'+x-10));}xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}

static void set_logic_flags(uint32_t v){
 eflags=(eflags&~(CF|PF|ZF|SF|OF))|(v==0?ZF:0)|((v&0x80000000u)?SF:0);
}
static void set_add_flags(uint32_t a,uint32_t b,uint32_t r){
 uint32_t f=eflags&~(CF|PF|ZF|SF|OF);
 if(r<a)f|=CF;
 if(r==0)f|=ZF;
 if(r&0x80000000u)f|=SF;
 if(((~(a^b))&(a^r)&0x80000000u)!=0)f|=OF;
 eflags=f;
}
static void set_sub_flags(uint32_t a,uint32_t b,uint32_t r){
 uint32_t f=eflags&~(CF|PF|ZF|SF|OF);
 if(a<b)f|=CF;
 if(r==0)f|=ZF;
 if(r&0x80000000u)f|=SF;
 if(((a^b)&(a^r)&0x80000000u)!=0)f|=OF;
 eflags=f;
}
static int cond(uint8_t op){
 switch(op){
  case 0x74:return (eflags&ZF)!=0; /* JE/JZ */
  case 0x75:return (eflags&ZF)==0; /* JNE/JNZ */
  case 0x72:return (eflags&CF)!=0; /* JB/JC */
  case 0x73:return (eflags&CF)==0; /* JAE/JNC */
  case 0x77:return (eflags&CF)==0&&(eflags&ZF)==0; /* JA */
  case 0x76:return (eflags&CF)!=0||(eflags&ZF)!=0; /* JBE */
  case 0x7C:return ((eflags&SF)!=0)!=((eflags&OF)!=0); /* JL */
  case 0x7D:return ((eflags&SF)!=0)==((eflags&OF)!=0); /* JGE */
  case 0x7E:return (eflags&ZF)!=0||(((eflags&SF)!=0)!=((eflags&OF)!=0)); /* JLE */
  case 0x7F:return (eflags&ZF)==0&&(((eflags&SF)!=0)==((eflags&OF)!=0)); /* JG */
  default:return 0;
 }
}
static uint32_t reg_from_modrm(uint8_t m){return regs[(m>>3)&7];}

static int cpu_step(void){
 uint32_t ip=eip; uint8_t op=MEM8(ip++); steps++;
 switch(op){
  case 0x90: eip=ip; return 0; /* NOP */
  case 0xF4: eip=ip; halted=1; return 1; /* HLT */
  case 0x31: { /* XOR r/m32,r32; v0.2 supports register form */
   uint8_t m=MEM8(ip++);
   if((m>>6)!=3){cpu_error=2;return -2;}
   uint32_t *dst=&regs[m&7]; uint32_t src=regs[(m>>3)&7];
   *dst^=src; set_logic_flags(*dst); eip=ip; return 0;
  }
  case 0x33: { /* XOR r32,r/m32 register form */
   uint8_t m=MEM8(ip++);
   if((m>>6)!=3){cpu_error=3;return -3;}
   uint32_t *dst=&regs[(m>>3)&7]; *dst^=regs[m&7]; set_logic_flags(*dst); eip=ip; return 0;
  }
  case 0xB8:case 0xB9:case 0xBA:case 0xBB:case 0xBC:case 0xBD:case 0xBE:case 0xBF:
   regs[op-0xB8]=rd32(ip); eip=ip+4; return 0; /* MOV r32,imm32 */
  case 0x05: {uint32_t b=rd32(ip);uint32_t r=regs[R_EAX]+b;set_add_flags(regs[R_EAX],b,r);regs[R_EAX]=r;eip=ip+4;return 0;}
  case 0x2D: {uint32_t b=rd32(ip);uint32_t r=regs[R_EAX]-b;set_sub_flags(regs[R_EAX],b,r);regs[R_EAX]=r;eip=ip+4;return 0;}
  case 0x3D: {uint32_t b=rd32(ip);uint32_t r=regs[R_EAX]-b;set_sub_flags(regs[R_EAX],b,r);eip=ip+4;return 0;} /* CMP EAX,imm32 */
  case 0x40:case 0x41:case 0x42:case 0x43:case 0x44:case 0x45:case 0x46:case 0x47:
   {uint32_t r=regs[op-0x40]+1;regs[op-0x40]=r; /* INC does not modify CF */
    uint32_t old=eflags;set_add_flags(regs[op-0x40]-1,1,r);eflags=(eflags&~CF)|(old&CF);eip=ip;return 0;}
  case 0x48:case 0x49:case 0x4A:case 0x4B:case 0x4C:case 0x4D:case 0x4E:case 0x4F:
   {uint32_t r=regs[op-0x48]-1;uint32_t old=eflags;set_sub_flags(regs[op-0x48]+1,1,r);eflags=(eflags&~CF)|(old&CF);regs[op-0x48]=r;eip=ip;return 0;}
  case 0xE9:{int32_t d=(int32_t)rd32(ip);eip=ip+4+(uint32_t)d;return 0;} /* JMP rel32 */
  case 0xEB:{int8_t d=(int8_t)MEM8(ip);eip=ip+1+(int32_t)d;return 0;} /* JMP rel8 */
  case 0x74:case 0x75:case 0x72:case 0x73:case 0x77:case 0x76:case 0x7C:case 0x7D:case 0x7E:case 0x7F:{
   int8_t d=(int8_t)MEM8(ip++);eip=cond(op)?ip+(int32_t)d:ip;return 0;
  }
  case 0x68:{uint32_t v=rd32(ip);ip+=4;regs[R_ESP]-=4;wr32(regs[R_ESP],v);eip=ip;return 0;} /* PUSH imm32 */
  case 0x6A:{int8_t v=(int8_t)MEM8(ip++);regs[R_ESP]-=4;wr32(regs[R_ESP],(uint32_t)(int32_t)v);eip=ip;return 0;} /* PUSH imm8 */
  case 0x58:case 0x59:case 0x5A:case 0x5B:case 0x5C:case 0x5D:case 0x5E:case 0x5F:
   regs[op-0x58]=rd32(regs[R_ESP]);regs[R_ESP]+=4;eip=ip;return 0;
  case 0x50:case 0x51:case 0x52:case 0x53:case 0x54:case 0x55:case 0x56:case 0x57:
   regs[R_ESP]-=4;wr32(regs[R_ESP],regs[op-0x50]);eip=ip;return 0;
  case 0xC3:eip=rd32(regs[R_ESP]);regs[R_ESP]+=4;return 0; /* RET */
  case 0xE8:{int32_t d=(int32_t)rd32(ip);uint32_t next=ip+4;regs[R_ESP]-=4;wr32(regs[R_ESP],next);eip=next+(uint32_t)d;return 0;} /* CALL rel32 */
  default: cpu_error=op; return -10;
 }
}

static int load_pe(uint32_t f,uint32_t sz){
 load_error=0;loaded=0;last_load_ptr=f;last_load_size=sz;
 if(sz<0x40u){load_error=1;return-1;} if(rd16(f)!=0x5a4du){load_error=2;return-1;}
 uint32_t pe=rd32(f+0x3cu); if(pe>sz-4u){load_error=3;return-2;} if(pe+24u>sz){load_error=4;return-2;}
 if(rd32(f+pe)!=0x4550u){load_error=5;return-2;}
 uint16_t mach=rd16(f+pe+4),nsec=rd16(f+pe+6),optsz=rd16(f+pe+20);
 if(mach!=0x14cu){load_error=6;return-3;} if(optsz<224u){load_error=7;return-3;}
 uint32_t oh=f+pe+24u; if(oh+optsz>f+sz){load_error=8;return-3;} if(rd16(oh)!=0x10bu){load_error=9;return-3;}
 uint32_t szimg=rd32(oh+56u),szhdr=rd32(oh+60u),ep=rd32(oh+16u);
 if(szimg<0x1000u||szimg>0x10000000u){load_error=10;return-4;} if(szhdr>sz){load_error=11;return-4;}
 image_base=IMAGE_BASE;image_size=szimg;entry=ep;copy_bytes(image_base,f,szhdr);
 uint32_t sh=oh+optsz; if(sh<f||sh>f+sz||(uint64_t)nsec*40u>(uint64_t)(f+sz-sh)){load_error=12;return-5;}
 for(uint16_t i=0;i<nsec;i++,sh+=40u){uint32_t va=rd32(sh+12u),raw=rd32(sh+20u),rawsz=rd32(sh+16u);
  if((uint64_t)image_base+va+rawsz>0x10000000ULL){load_error=13;return-5;} if(raw>sz||rawsz>sz-raw){load_error=14;return-5;}
  copy_bytes(image_base+va,f+raw,rawsz);
 }
 loaded=1;eip=image_base+entry;regs[R_ESP]=image_base+image_size-0x1000u;halted=0;cpu_error=0;steps=0;eflags=0x2;loghex("X86 entry=",eip);return 0;
}

__attribute__((export_name("xwasm_init"))) int xwasm_init(void){
 heap=al4((uint32_t)(uintptr_t)__heap_base);loaded=0;dll_count=0;import_count=0;steps=0;load_error=0;halted=0;cpu_error=0;eflags=0x2;
 for(int i=0;i<8;i++)regs[i]=0; loglit("XWASM X86 Runtime v0.2");loglit("PE32 loader + x86 fetch/decode/execute foundation");return 0;
}
__attribute__((export_name("x86_get_runtime_version"))) uint32_t x86_get_runtime_version(void){return 0x00020000u;}
__attribute__((export_name("x86_debug_probe"))) uint32_t x86_debug_probe(int32_t p){return rd16((uint32_t)p);}
__attribute__((export_name("x86_load_pe"))) int x86_load_pe(int32_t p,int32_t n){return load_pe((uint32_t)p,(uint32_t)n);}
__attribute__((export_name("x86_run"))) int x86_run(int32_t max_steps){
 if(!loaded)return -20; if(halted)return 1; if(max_steps<1)max_steps=1;
 for(int32_t i=0;i<max_steps&&!halted;i++){int r=cpu_step();if(r<0)return r;}
 return halted?1:0;
}
__attribute__((export_name("x86_get_eip"))) uint32_t x86_get_eip(void){return eip;}
__attribute__((export_name("x86_get_steps"))) uint32_t x86_get_steps(void){return steps;}
__attribute__((export_name("x86_get_eax"))) uint32_t x86_get_eax(void){return regs[R_EAX];}
__attribute__((export_name("x86_get_ecx"))) uint32_t x86_get_ecx(void){return regs[R_ECX];}
__attribute__((export_name("x86_get_edx"))) uint32_t x86_get_edx(void){return regs[R_EDX];}
__attribute__((export_name("x86_get_ebx"))) uint32_t x86_get_ebx(void){return regs[R_EBX];}
__attribute__((export_name("x86_get_esp"))) uint32_t x86_get_esp(void){return regs[R_ESP];}
__attribute__((export_name("x86_get_ebp"))) uint32_t x86_get_ebp(void){return regs[R_EBP];}
__attribute__((export_name("x86_get_esi"))) uint32_t x86_get_esi(void){return regs[R_ESI];}
__attribute__((export_name("x86_get_edi"))) uint32_t x86_get_edi(void){return regs[R_EDI];}
__attribute__((export_name("x86_get_eflags"))) uint32_t x86_get_eflags(void){return eflags;}
__attribute__((export_name("x86_get_halted"))) uint32_t x86_get_halted(void){return halted;}
__attribute__((export_name("x86_get_cpu_error"))) uint32_t x86_get_cpu_error(void){return cpu_error;}
__attribute__((export_name("x86_get_dll_count"))) uint32_t x86_get_dll_count(void){return dll_count;}
__attribute__((export_name("x86_get_import_count"))) uint32_t x86_get_import_count(void){return import_count;}
__attribute__((export_name("x86_get_loaded"))) uint32_t x86_get_loaded(void){return loaded;}
__attribute__((export_name("x86_get_load_error"))) uint32_t x86_get_load_error(void){return load_error;}
__attribute__((export_name("x86_get_load_ptr"))) uint32_t x86_get_load_ptr(void){return last_load_ptr;}
__attribute__((export_name("x86_get_load_size"))) uint32_t x86_get_load_size(void){return last_load_size;}
