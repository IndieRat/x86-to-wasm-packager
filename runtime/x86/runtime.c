// XWASM X86 Runtime v0.4
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
static uint32_t requested_image_base=0,reloc_rva=0,reloc_size=0,import_rva=0,import_size=0;
static uint32_t relocation_needed=0,dll_count=0,import_count=0,load_error=0,last_load_ptr=0,last_load_size=0;
static uint32_t regs[8],eflags=0x00000002u;
static uint32_t halted=0,cpu_error=0;

/* v0.4 guest memory/import foundation. The guest-visible address space is
 * intentionally separate from the WASM allocator used for diagnostics. */
#define GUEST_HEAP_BASE 0x00800000u
#define GUEST_HEAP_LIMIT 0x01F00000u
#define API_BASE 0x70000000u
#define API_GETTICKCOUNT (API_BASE+0x00001000u)

static uint32_t guest_heap=GUEST_HEAP_BASE;
static uint32_t import_resolved=0,import_failed=0;
static uint32_t last_import_dll=0,last_import_func=0,last_import_thunk=0;

static uint32_t cstrlen(uint32_t p){
 uint32_t n=0; while(n<0x10000u && MEM8(p+n))n++; return n;
}
static int streq_ascii(uint32_t p,const char*s){
 uint32_t i=0; while(s[i]){if(MEM8(p+i)!=(uint8_t)s[i])return 0;i++;}
 return MEM8(p+i)==0;
}
static uint32_t guest_alloc_raw(uint32_t n){
 if(!n)return 0;
 uint32_t a=al4(guest_heap);
 uint32_t end=a+al4(n);
 if(end<a||end>GUEST_HEAP_LIMIT)return 0;
 guest_heap=end; return a;
}
static uint32_t resolve_builtin(uint32_t dll,uint32_t name){
 /* First compatibility seed: enough structure to grow into real Win32 DLLs. */
 if(streq_ascii(dll,"KERNEL32.dll")||streq_ascii(dll,"kernel32.dll")){
  if(streq_ascii(name,"GetTickCount"))return API_GETTICKCOUNT;
 }
 return 0;
}
static uint32_t call_builtin(uint32_t target){
 if(target==API_GETTICKCOUNT){regs[R_EAX]=1234u;return 1;}
 return 0;
}

static uint16_t rd16(uint32_t p){return (uint16_t)MEM8(p)|((uint16_t)MEM8(p+1)<<8);}
static uint32_t rd32(uint32_t p){return (uint32_t)MEM8(p)|((uint32_t)MEM8(p+1)<<8)|((uint32_t)MEM8(p+2)<<16)|((uint32_t)MEM8(p+3)<<24);}
static void wr32(uint32_t p,uint32_t v){MEM8(p)=(uint8_t)v;MEM8(p+1)=(uint8_t)(v>>8);MEM8(p+2)=(uint8_t)(v>>16);MEM8(p+3)=(uint8_t)(v>>24);}
static uint32_t al4(uint32_t x){return(x+3u)&~3u;}
static void wr8(uint32_t p,uint8_t v){MEM8(p)=v;}
static void copy_bytes(uint32_t d,uint32_t s,uint32_t n){for(uint32_t i=0;i<n;i++)wr8(d+i,MEM8(s+i));}
static void loglit(const char*s){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}
static void loghex(const char*s,uint32_t v){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);wr8(p++,'0');wr8(p++,'x');for(int i=7;i>=0;i--){uint8_t x=(v>>(i*4))&15u;wr8(p++,(uint8_t)(x<10?'0'+x:'A'+x-10));}xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}

static void set_logic_flags(uint32_t v){
 uint32_t p=v; p^=p>>4; p^=p>>2; p^=p>>1;
 eflags=(eflags&~(CF|PF|ZF|SF|OF))|((p&1u)==0?PF:0)|(v==0?ZF:0)|((v&0x80000000u)?SF:0);
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
static int modrm_ea(uint8_t m,uint32_t *ip,uint32_t *ea){
 uint8_t mod=m>>6,rm=m&7;
 if(mod==3)return 0;
 uint32_t base=0,index=0,scale=1;
 if(rm==4){
  uint8_t sib=MEM8((*ip)++);
  uint8_t ss=sib>>6,si=(sib>>3)&7,sb=sib&7;
  scale=1u<<ss;
  if(si!=4)index=regs[si]*scale;
  if(sb==5&&mod==0)base=rd32(*ip),*ip+=4;
  else base=regs[sb];
 }else if(rm==5&&mod==0){
  base=rd32(*ip);*ip+=4;
 }else{
  base=regs[rm];
 }
 if(mod==1){int8_t d=(int8_t)MEM8((*ip)++);base+=(int32_t)d;}
 else if(mod==2){int32_t d=(int32_t)rd32(*ip);*ip+=4;base+=(uint32_t)d;}
 *ea=base+index; return 1;
}
static uint32_t modrm_read32(uint8_t m,uint32_t *ip){
 uint32_t ea=0; if(!modrm_ea(m,ip,&ea))return regs[m&7]; return rd32(ea);
}
static void modrm_write32(uint8_t m,uint32_t *ip,uint32_t v){
 uint32_t ea=0; if(!modrm_ea(m,ip,&ea)){regs[m&7]=v;return;} wr32(ea,v);
}

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
  case 0x8B: { /* MOV r32,r/m32 */
   uint8_t m=MEM8(ip++); uint32_t v=modrm_read32(m,&ip); regs[(m>>3)&7]=v; eip=ip; return 0;
  }
  case 0x89: { /* MOV r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t v=regs[(m>>3)&7]; modrm_write32(m,&ip,v); eip=ip; return 0;
  }
  case 0x8D: { /* LEA r32,m */
   uint8_t m=MEM8(ip++); uint32_t ea=0; if(!modrm_ea(m,&ip,&ea)){cpu_error=0x8D;return -11;} regs[(m>>3)&7]=ea; eip=ip; return 0;
  }
  case 0x01: { /* ADD r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t ea=0,b=regs[(m>>3)&7]; uint32_t a;
   if((m>>6)==3)a=regs[m&7]; else {modrm_ea(m,&ip,&ea);a=rd32(ea);}
   uint32_t r=a+b; set_add_flags(a,b,r);
   if((m>>6)==3)regs[m&7]=r; else wr32(ea,r);
   eip=ip; return 0;
  }
  case 0x29: { /* SUB r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t ea=0,b=regs[(m>>3)&7]; uint32_t a;
   if((m>>6)==3)a=regs[m&7]; else {modrm_ea(m,&ip,&ea);a=rd32(ea);}
   uint32_t r=a-b; set_sub_flags(a,b,r);
   if((m>>6)==3)regs[m&7]=r; else wr32(ea,r);
   eip=ip; return 0;
  }
  case 0x39: { /* CMP r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t ea=0,b=regs[(m>>3)&7],a;
   if((m>>6)==3)a=regs[m&7]; else {modrm_ea(m,&ip,&ea);a=rd32(ea);}
   uint32_t r=a-b; set_sub_flags(a,b,r); eip=ip; return 0;
  }
  case 0x85: { /* TEST r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t v=modrm_read32(m,&ip)&regs[(m>>3)&7]; set_logic_flags(v); eip=ip; return 0;
  }
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
  case 0xFF: { /* CALL/JMP r/m32 subset; v0.4 uses /2 for imported APIs. */
   uint8_t m=MEM8(ip++);
   uint8_t sub=(m>>3)&7;
   if(sub!=2&&sub!=4){cpu_error=0xFF00u|sub;return -12;}
   uint32_t target=modrm_read32(m,&ip);
   uint32_t next=ip;
   if(sub==2){
    regs[R_ESP]-=4;wr32(regs[R_ESP],next);
    if(call_builtin(target)){eip=next;regs[R_ESP]+=4;return 0;}
    eip=target;return 0;
   }
   eip=target;return 0;
  }
  case 0xC3:eip=rd32(regs[R_ESP]);regs[R_ESP]+=4;return 0; /* RET */
  case 0xE8:{int32_t d=(int32_t)rd32(ip);uint32_t next=ip+4;regs[R_ESP]-=4;wr32(regs[R_ESP],next);eip=next+(uint32_t)d;return 0;} /* CALL rel32 */
  default: cpu_error=op; return -10;
 }
}

static int image_rva_valid(uint32_t rva,uint32_t size){
 return rva<=image_size && size<=image_size-rva;
}
static void scan_imports(void){
 dll_count=0; import_count=0; import_resolved=0; import_failed=0;
 if(!import_rva||!import_size||!image_rva_valid(import_rva,20))return;
 uint32_t p=image_base+import_rva;
 uint32_t max=image_base+import_rva+import_size;
 for(uint32_t n=0;p+20u<=max;n++,p+=20u){
  uint32_t oft=rd32(p),name_rva=rd32(p+12),ft=rd32(p+16);
  if(!oft&&!name_rva&&!ft)break;
  dll_count++;
  if(!name_rva||name_rva>=image_size||!ft||ft>=image_size){import_failed++;continue;}
  uint32_t thunk_rva=oft?oft:ft;
  if(thunk_rva>=image_size){import_failed++;continue;}
  uint32_t thunk=image_base+thunk_rva;
  uint32_t iat=image_base+ft;
  uint32_t dll=image_base+name_rva;
  uint32_t resolved_this_dll=0;
  for(uint32_t i=0;i<0x100000u;i++){
   uint32_t v=rd32(thunk+i*4u);
   if(!v)break;
   if(v&0x80000000u){import_failed++;continue;} /* ordinal imports are a later milestone */
   if(v+2u>=image_size){import_failed++;break;}
   uint32_t name=image_base+v+2u;
   import_count++;
   uint32_t target=resolve_builtin(dll,name);
   if(target){
    wr32(iat+i*4u,target);
    import_resolved++;
    last_import_dll=name_rva;
    last_import_func=v;
    last_import_thunk=ft+i*4u;
    resolved_this_dll++;
   }else{
    import_failed++;
   }
  }
  (void)resolved_this_dll;
 }
}


static int load_pe(uint32_t f,uint32_t sz){
 load_error=0;loaded=0;last_load_ptr=f;last_load_size=sz;
 requested_image_base=0;reloc_rva=reloc_size=import_rva=import_size=0;relocation_needed=0;dll_count=import_count=0;
 if(sz<0x40u){load_error=1;return-1;} if(rd16(f)!=0x5a4du){load_error=2;return-1;}
 uint32_t pe=rd32(f+0x3cu); if(pe>sz-4u){load_error=3;return-2;} if(pe+24u>sz){load_error=4;return-2;}
 if(rd32(f+pe)!=0x4550u){load_error=5;return-2;}
 uint16_t mach=rd16(f+pe+4),nsec=rd16(f+pe+6),optsz=rd16(f+pe+20);
 if(mach!=0x14cu){load_error=6;return-3;} if(optsz<224u){load_error=7;return-3;}
 uint32_t oh=f+pe+24u; if(oh+optsz>f+sz){load_error=8;return-3;} if(rd16(oh)!=0x10bu){load_error=9;return-3;}
 uint32_t szimg=rd32(oh+56u),szhdr=rd32(oh+60u),ep=rd32(oh+16u),reqbase=rd32(oh+28u);
 uint32_t dirs=rd32(oh+92u);
 if(szimg<0x1000u||szimg>0x10000000u){load_error=10;return-4;} if(szhdr>sz||szhdr>szimg){load_error=11;return-4;}
 requested_image_base=reqbase; image_base=IMAGE_BASE; image_size=szimg; entry=ep;
 relocation_needed=(requested_image_base!=image_base)?1u:0u;
 if(dirs>1u){import_rva=rd32(oh+96u+8u);import_size=rd32(oh+96u+12u);}
 if(dirs>5u){reloc_rva=rd32(oh+96u+40u);reloc_size=rd32(oh+96u+44u);}
 uint32_t sh=oh+optsz;
 if(sh<f||sh>f+sz||(uint64_t)nsec*40u>(uint64_t)(f+sz-sh)){load_error=12;return-5;}
 for(uint32_t i=0;i<image_size;i++)wr8(image_base+i,0);
 copy_bytes(image_base,f,szhdr);
 for(uint16_t i=0;i<nsec;i++,sh+=40u){
  uint32_t va=rd32(sh+12u),vsz=rd32(sh+8u),raw=rd32(sh+20u),rawsz=rd32(sh+16u);
  uint32_t mapped=vsz>rawsz?vsz:rawsz;
  if((uint64_t)va+mapped>(uint64_t)image_size){load_error=13;return-5;}
  if(raw>sz||rawsz>sz-raw){load_error=14;return-5;}
  if(rawsz)copy_bytes(image_base+va,f+raw,rawsz);
 }
 if(ep>=image_size){load_error=15;return-6;}
 if(import_rva&&import_size)scan_imports();
 loaded=1;eip=image_base+entry;regs[R_ESP]=0x03F00000u;guest_heap=GUEST_HEAP_BASE;halted=0;cpu_error=0;steps=0;eflags=0x2;
 loghex("X86 requested image base=",requested_image_base);
 loghex("X86 mapped image base=",image_base);
 loghex("X86 entry=",eip);
 return 0;
}

__attribute__((export_name("xwasm_init"))) int xwasm_init(void){
 heap=al4((uint32_t)(uintptr_t)__heap_base);guest_heap=GUEST_HEAP_BASE;loaded=0;requested_image_base=0;reloc_rva=reloc_size=import_rva=import_size=0;relocation_needed=0;dll_count=0;import_count=0;steps=0;load_error=0;halted=0;cpu_error=0;eflags=0x2;
 for(int i=0;i<8;i++)regs[i]=0; loglit("XWASM X86 Runtime v0.4");loglit("PE32 mapping + DLL import resolution + guest memory foundation + x86 ModRM");return 0;
}
__attribute__((export_name("x86_get_runtime_version"))) uint32_t x86_get_runtime_version(void){return 0x00040000u;}
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
__attribute__((export_name("x86_get_current_opcode")))
uint32_t x86_get_current_opcode(void){
 if(!loaded)return 0xFFFFFFFFu;
 return (uint32_t)MEM8(eip);
}
__attribute__((export_name("x86_get_current_imm32")))
uint32_t x86_get_current_imm32(void){
 if(!loaded)return 0xFFFFFFFFu;
 return rd32(eip+1u);
}
__attribute__((export_name("x86_get_requested_image_base"))) uint32_t x86_get_requested_image_base(void){return requested_image_base;}
__attribute__((export_name("x86_get_image_base"))) uint32_t x86_get_image_base(void){return image_base;}
__attribute__((export_name("x86_get_image_size"))) uint32_t x86_get_image_size(void){return image_size;}
__attribute__((export_name("x86_get_relocation_rva"))) uint32_t x86_get_relocation_rva(void){return reloc_rva;}
__attribute__((export_name("x86_get_relocation_size"))) uint32_t x86_get_relocation_size(void){return reloc_size;}
__attribute__((export_name("x86_get_import_rva"))) uint32_t x86_get_import_rva(void){return import_rva;}
__attribute__((export_name("x86_get_import_size"))) uint32_t x86_get_import_size(void){return import_size;}
__attribute__((export_name("x86_get_relocation_needed"))) uint32_t x86_get_relocation_needed(void){return relocation_needed;}
__attribute__((export_name("x86_get_dll_count"))) uint32_t x86_get_dll_count(void){return dll_count;}
__attribute__((export_name("x86_get_import_count"))) uint32_t x86_get_import_count(void){return import_count;}
__attribute__((export_name("x86_get_import_resolved"))) uint32_t x86_get_import_resolved(void){return import_resolved;}
__attribute__((export_name("x86_get_import_failed"))) uint32_t x86_get_import_failed(void){return import_failed;}
__attribute__((export_name("x86_get_last_import_dll_rva"))) uint32_t x86_get_last_import_dll_rva(void){return last_import_dll;}
__attribute__((export_name("x86_get_last_import_func_rva"))) uint32_t x86_get_last_import_func_rva(void){return last_import_func;}
__attribute__((export_name("x86_get_last_import_thunk_rva"))) uint32_t x86_get_last_import_thunk_rva(void){return last_import_thunk;}
__attribute__((export_name("x86_alloc"))) uint32_t x86_alloc(uint32_t n){return guest_alloc_raw(n);}
__attribute__((export_name("x86_get_guest_heap"))) uint32_t x86_get_guest_heap(void){return guest_heap;}
__attribute__((export_name("x86_get_loaded"))) uint32_t x86_get_loaded(void){return loaded;}
__attribute__((export_name("x86_get_load_error"))) uint32_t x86_get_load_error(void){return load_error;}
__attribute__((export_name("x86_get_load_ptr"))) uint32_t x86_get_load_ptr(void){return last_load_ptr;}
__attribute__((export_name("x86_get_load_size"))) uint32_t x86_get_load_size(void){return last_load_size;}
