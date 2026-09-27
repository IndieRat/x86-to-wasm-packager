// XWASM X86 Runtime v0.1
// Minimal PE32 loader + DLL dependency resolver + tiny x86 interpreter foundation.
#include <stdint.h>
extern void xwasm_log(int32_t level,int32_t ptr,int32_t len);
extern int32_t xwasm_resource_size(int32_t ptr,int32_t len);
extern int32_t xwasm_resource_read(int32_t ptr,int32_t len,int32_t dst,int32_t dst_len,int32_t off);
#define HEAP_BASE 0x10000u
#define IMAGE_BASE 0x00400000u
#define PAYLOAD_STAGE 0x02000000u
static uint8_t *mem=(uint8_t*)0; static uint32_t heap=HEAP_BASE,image_base=0,image_size=0,entry=0,eip=0,steps=0,loaded=0,dll_count=0,import_count=0,load_error=0;
static uint32_t regs[8];
static uint16_t rd16(uint32_t p){return mem[p]|((uint16_t)mem[p+1]<<8);}
static uint32_t rd32(uint32_t p){return mem[p]|((uint32_t)mem[p+1]<<8)|((uint32_t)mem[p+2]<<16)|((uint32_t)mem[p+3]<<24);}
static uint32_t al4(uint32_t x){return(x+3)&~3u;}
static uint32_t slen(uint32_t p){uint32_t n=0;while(n<4096&&mem[p+n])n++;return n;}
static void loglit(const char*s){uint32_t p=heap;while(*s)mem[p++]=(uint8_t)*s++;xwasm_log(1,heap,p-heap);heap=al4(p+1);}
static void loghex(const char*s,uint32_t v){uint32_t p=heap;while(*s)mem[p++]=(uint8_t)*s++;mem[p++]='0';mem[p++]='x';for(int i=7;i>=0;i--){uint8_t x=(v>>(i*4))&15;mem[p++]=(uint8_t)(x<10?'0'+x:'A'+x-10);}xwasm_log(1,heap,p-heap);heap=al4(p+1);}

static int load_pe(uint32_t f,uint32_t sz){
  load_error=0; loaded=0;
  if(sz<0x40){load_error=1;return-1;}
  if(rd16(f)!=0x5a4d){load_error=2;return-1;}
  uint32_t pe=rd32(f+0x3c);
  if(pe>sz-4){load_error=3;return-2;}
  if(pe+24>sz){load_error=4;return-2;}
  if(rd32(f+pe)!=0x4550){load_error=5;return-2;}
  uint16_t mach=rd16(f+pe+4),nsec=rd16(f+pe+6),optsz=rd16(f+pe+20);
  if(mach!=0x14c){load_error=6;return-3;}
  if(optsz<224){load_error=7;return-3;}
  uint32_t oh=pe+24;
  if(oh+optsz>sz){load_error=8;return-3;}
  if(rd16(oh)!=0x10b){load_error=9;return-3;}
  uint32_t szimg=rd32(oh+56),szhdr=rd32(oh+60),ep=rd32(oh+16);
  if(szimg<0x1000||szimg>0x10000000){load_error=10;return-4;}
  if(szhdr>sz){load_error=11;return-4;}
  image_base=IMAGE_BASE;image_size=szimg;entry=ep;
  for(uint32_t i=0;i<szhdr;i++)mem[image_base+i]=mem[f+i];
  uint32_t sh=oh+optsz;
  if((uint64_t)sh+(uint64_t)nsec*40u>f+sz){load_error=12;return-5;}
  for(uint16_t i=0;i<nsec;i++,sh+=40){
    uint32_t va=rd32(sh+12),raw=rd32(sh+20),rawsz=rd32(sh+16);
    if((uint64_t)image_base+va+rawsz>0x10000000ULL){load_error=13;return-5;}
    if(raw>sz||rawsz>sz-raw){load_error=14;return-5;}
    for(uint32_t j=0;j<rawsz;j++)mem[image_base+va+j]=mem[f+raw+j];
  }
  loaded=1;eip=image_base+entry;regs[4]=image_base+image_size-0x1000;
  loghex("X86 entry=",eip);return 0;
}
static void scan_imports(void){if(!loaded)return;uint32_t pe=rd32(image_base+0x3c),oh=image_base+pe+24,imp=rd32(oh+96+8);if(!imp)return;uint32_t d=image_base+imp;for(;rd32(d);d+=20){uint32_t nr=rd32(d+12),th=rd32(d+16);if(nr){uint32_t n=image_base+nr;dll_count++;xwasm_log(1,n,slen(n));}if(th){uint32_t t=image_base+th;for(uint32_t i=0;i<8192;i++){uint32_t v=rd32(t+i*4);if(!v)break;import_count++;}}}loghex("X86 DLL count=",dll_count);loghex("X86 import count=",import_count);}
static int step(void){uint8_t op=mem[eip++];switch(op){case 0x90:return 0;case 0xc3:eip=rd32(regs[4]);regs[4]+=4;return 1;case 0xcc:return 2;case 0xf4:return 3;case 0x31:{uint8_t m=mem[eip++];if(m==0xc0){regs[0]=0;return 0;}return-1;}case 0x40:regs[0]++;return 0;case 0x41:regs[1]++;return 0;case 0x42:regs[2]++;return 0;case 0x43:regs[3]++;return 0;case 0x48:regs[0]--;return 0;case 0x49:regs[1]--;return 0;case 0x4a:regs[2]--;return 0;case 0x4b:regs[3]--;return 0;default:return-1;}}
__attribute__((export_name("xwasm_init"))) int xwasm_init(void){heap=HEAP_BASE;loaded=0;dll_count=0;import_count=0;steps=0;load_error=0;loglit("XWASM X86 Runtime v0.1");loglit("PE32 loader + DLL resolver foundation ready");return 0;}
__attribute__((export_name("x86_load_pe"))) int x86_load_pe(int32_t p,int32_t n){int r=load_pe((uint32_t)p,(uint32_t)n);if(!r)scan_imports();return r;}
__attribute__((export_name("x86_step"))) int x86_step(void){if(!loaded)return-10;int r=step();steps++;return r;}
__attribute__((export_name("x86_run"))) int x86_run(int32_t n){if(!loaded)return-10;for(int32_t i=0;i<n;i++){int r=step();steps++;if(r)return r;}return 0;}
__attribute__((export_name("x86_get_eip"))) uint32_t x86_get_eip(void){return eip;}
__attribute__((export_name("x86_get_steps"))) uint32_t x86_get_steps(void){return steps;}
__attribute__((export_name("x86_get_dll_count"))) uint32_t x86_get_dll_count(void){return dll_count;}
__attribute__((export_name("x86_get_import_count"))) uint32_t x86_get_import_count(void){return import_count;}
__attribute__((export_name("x86_get_loaded"))) uint32_t x86_get_loaded(void){return loaded;}
__attribute__((export_name("x86_get_load_error"))) uint32_t x86_get_load_error(void){return load_error;}
