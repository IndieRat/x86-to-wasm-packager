// XWASM X86 Runtime v0.1
#include <stdint.h>
extern void xwasm_log(int32_t level,int32_t ptr,int32_t len);
#define HEAP_BASE 0x10000u
#define IMAGE_BASE 0x00400000u
#define MEM8(p) (*(volatile uint8_t *)(uintptr_t)(p))
static uint32_t heap=HEAP_BASE,image_base=0,image_size=0,entry=0,eip=0,steps=0,loaded=0,dll_count=0,import_count=0,load_error=0;
static uint32_t last_load_ptr=0,last_load_size=0;
static uint32_t regs[8];
static uint16_t rd16(uint32_t p){return (uint16_t)MEM8(p)|((uint16_t)MEM8(p+1)<<8);}
static uint32_t rd32(uint32_t p){return (uint32_t)MEM8(p)|((uint32_t)MEM8(p+1)<<8)|((uint32_t)MEM8(p+2)<<16)|((uint32_t)MEM8(p+3)<<24);}
static uint32_t al4(uint32_t x){return(x+3u)&~3u;}
static void wr8(uint32_t p,uint8_t v){MEM8(p)=v;}
static void copy_bytes(uint32_t d,uint32_t s,uint32_t n){for(uint32_t i=0;i<n;i++)wr8(d+i,MEM8(s+i));}
static void loglit(const char*s){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}
static void loghex(const char*s,uint32_t v){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);wr8(p++,'0');wr8(p++,'x');for(int i=7;i>=0;i--){uint8_t x=(v>>(i*4))&15u;wr8(p++,(uint8_t)(x<10?'0'+x:'A'+x-10));}xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}
static int load_pe(uint32_t f,uint32_t sz){
 load_error=0;loaded=0;last_load_ptr=f;last_load_size=sz;
 if(sz<0x40u){load_error=1;return-1;}
 if(rd16(f)!=0x5a4du){load_error=2;return-1;}
 uint32_t pe=rd32(f+0x3cu);
 if(pe>sz-4u){load_error=3;return-2;}
 if(pe+24u>sz){load_error=4;return-2;}
 if(rd32(f+pe)!=0x4550u){load_error=5;return-2;}
 uint16_t mach=rd16(f+pe+4),nsec=rd16(f+pe+6),optsz=rd16(f+pe+20);
 if(mach!=0x14cu){load_error=6;return-3;}
 if(optsz<224u){load_error=7;return-3;}
 uint32_t oh=f+pe+24u;
 if(oh+optsz>sz){load_error=8;return-3;}
 if(rd16(oh)!=0x10bu){load_error=9;return-3;}
 uint32_t szimg=rd32(oh+56u),szhdr=rd32(oh+60u),ep=rd32(oh+16u);
 if(szimg<0x1000u||szimg>0x10000000u){load_error=10;return-4;}
 if(szhdr>sz){load_error=11;return-4;}
 image_base=IMAGE_BASE;image_size=szimg;entry=ep;
 copy_bytes(image_base,f,szhdr);
 uint32_t sh=oh+optsz;
 if(sh<f||sh>f+sz||(uint64_t)nsec*40u>(uint64_t)(f+sz-sh)){load_error=12;return-5;}
 for(uint16_t i=0;i<nsec;i++,sh+=40u){
  uint32_t va=rd32(sh+12u),raw=rd32(sh+20u),rawsz=rd32(sh+16u);
  if((uint64_t)image_base+va+rawsz>0x10000000ULL){load_error=13;return-5;}
  if(raw>sz||rawsz>sz-raw){load_error=14;return-5;}
  copy_bytes(image_base+va,f+raw,rawsz);
 }
 loaded=1;eip=image_base+entry;regs[4]=image_base+image_size-0x1000u;loghex("X86 entry=",eip);return 0;
}
__attribute__((export_name("xwasm_init"))) int xwasm_init(void){heap=HEAP_BASE;loaded=0;dll_count=0;import_count=0;steps=0;load_error=0;loglit("XWASM X86 Runtime v0.1");loglit("PE32 loader + imported-memory test runtime");return 0;}
__attribute__((export_name("x86_get_runtime_version"))) uint32_t x86_get_runtime_version(void){return 0x00010002u;}
__attribute__((export_name("x86_debug_probe"))) uint32_t x86_debug_probe(int32_t p){return rd16((uint32_t)p);}
__attribute__((export_name("x86_load_pe"))) int x86_load_pe(int32_t p,int32_t n){return load_pe((uint32_t)p,(uint32_t)n);}
__attribute__((export_name("x86_get_eip"))) uint32_t x86_get_eip(void){return eip;}
__attribute__((export_name("x86_get_steps"))) uint32_t x86_get_steps(void){return steps;}
__attribute__((export_name("x86_get_dll_count"))) uint32_t x86_get_dll_count(void){return dll_count;}
__attribute__((export_name("x86_get_import_count"))) uint32_t x86_get_import_count(void){return import_count;}
__attribute__((export_name("x86_get_loaded"))) uint32_t x86_get_loaded(void){return loaded;}
__attribute__((export_name("x86_get_load_error"))) uint32_t x86_get_load_error(void){return load_error;}
__attribute__((export_name("x86_get_load_ptr"))) uint32_t x86_get_load_ptr(void){return last_load_ptr;}
__attribute__((export_name("x86_get_load_size"))) uint32_t x86_get_load_size(void){return last_load_size;}
