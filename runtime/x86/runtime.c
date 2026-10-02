// XWASM X86 Runtime v0.9
#include <stdint.h>

extern void xwasm_log(int32_t level,int32_t ptr,int32_t len);
#define HEAP_BASE_FALLBACK 0x100000u
extern unsigned char __heap_base[];
#define IMAGE_BASE 0x00400000u
#define X86_STRESS_REPORT_BASE 0x00401900u
#define MEM8(p) (*(volatile uint8_t *)(uintptr_t)(p))

/* 32-bit x86 register order: EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI. */
enum { R_EAX=0,R_ECX,R_EDX,R_EBX,R_ESP,R_EBP,R_ESI,R_EDI };
#define CF 0x00000001u
#define PF 0x00000004u
#define AF 0x00000010u
#define ZF 0x00000040u
#define SF 0x00000080u
#define OF 0x00000800u
#define DF 0x00000400u
#define X86_PREFIX_REPNZ 0x02u
#define X86_PREFIX_REP 0x04u

static uint32_t heap=HEAP_BASE_FALLBACK,image_base=0,image_size=0,entry=0,eip=0,steps=0,loaded=0;
#define X86_CRT_ATEXIT_MAX 32u
#define X86_CRT_EINVAL 22
#define X86_CRT_ENOMEM 12
#define X86_CRT_EFAULT 14
#define X86_CRT_CALLBACK_SENTINEL 0xF00DC0DEu
#define X86_CRT_CALLBACK_MARKER 0xC2C0FFEEu
#define X86_ENTRY_RETURN_SENTINEL 0xF00DCAFEu
static int32_t crt_errno=0;
static uint32_t crt_last_error=0,crt_started=0,crt_exited=0,crt_exit_code=0;
static uint32_t crt_atexit_count=0,crt_last_atexit_result=0,crt_last_atexit_ok=0,crt_atexit_running=0;
static uint32_t crt_atexit_callbacks[X86_CRT_ATEXIT_MAX];
static uint32_t requested_image_base=0,reloc_rva=0,reloc_size=0,import_rva=0,import_size=0;
static uint32_t relocation_needed=0,dll_count=0,import_count=0,load_error=0,last_load_ptr=0,last_load_size=0;
static uint32_t regs[8],eflags=0x00000002u;
/* Minimal x87 state. Values are kept as host doubles for the first compiler-coverage milestone; memory loads/stores still round through IEEE binary32/binary64 formats. */
static double x87_stack[8];
static uint32_t x87_count=0;
/* IA-32 SSE/SSE2 architectural XMM0-XMM7 state. The first SIMD milestone
 * implements scalar operations while retaining all 128 register bits. */
static uint8_t xmm[8][16];
static uint32_t halted=0,cpu_error=0;
static uint8_t decoded_prefixes=0,decoded_operand16=0;
static uint32_t last_decoded_map=0,last_decoded_opcode=0,last_decoded_length=0;
static uint32_t last_dispatch_id=0,last_dispatch_count=0,legacy_execution_count=0;
#define X86_SEMANTIC_ID_MAX 64u
static char last_decoded_semantic_id[X86_SEMANTIC_ID_MAX];
#define X86_TRACE_DEPTH 32u
static uint32_t trace_eip[X86_TRACE_DEPTH],trace_next_eip[X86_TRACE_DEPTH];
static uint32_t trace_opcode[X86_TRACE_DEPTH],trace_flags[X86_TRACE_DEPTH];
static uint32_t trace_eax[X86_TRACE_DEPTH],trace_ecx[X86_TRACE_DEPTH];
static uint32_t trace_ebx[X86_TRACE_DEPTH],trace_edx[X86_TRACE_DEPTH];
/* Each trace entry keeps both sides of the instruction boundary.  The legacy
 * trace_* register fields are the pre-state; trace_post_* are the state after
 * execution.  This makes dataflow faults attributable without guessing from
 * the next instruction's pre-state. */
static uint32_t trace_post_eax[X86_TRACE_DEPTH],trace_post_ecx[X86_TRACE_DEPTH];
static uint32_t trace_post_ebx[X86_TRACE_DEPTH],trace_post_edx[X86_TRACE_DEPTH];
static uint32_t trace_post_flags[X86_TRACE_DEPTH];
static uint32_t trace_dispatch[X86_TRACE_DEPTH];
static char trace_semantic_id[X86_TRACE_DEPTH][X86_SEMANTIC_ID_MAX];
static uint32_t trace_count=0,trace_head=0,trace_failure_index=0;
static int modrm_ea(uint8_t m,uint32_t *ip,uint32_t *ea);
static int cpu_step_x87(uint8_t op,uint32_t *ip);
static uint32_t xmm_get_u32(uint8_t r){return (uint32_t)xmm[r][0]|((uint32_t)xmm[r][1]<<8)|((uint32_t)xmm[r][2]<<16)|((uint32_t)xmm[r][3]<<24);}
static void xmm_set_u32(uint8_t r,uint32_t v){xmm[r][0]=(uint8_t)v;xmm[r][1]=(uint8_t)(v>>8);xmm[r][2]=(uint8_t)(v>>16);xmm[r][3]=(uint8_t)(v>>24);}
static uint64_t xmm_get_u64(uint8_t r){uint64_t lo=xmm_get_u32(r);uint32_t hi=(uint32_t)xmm[r][4]|((uint32_t)xmm[r][5]<<8)|((uint32_t)xmm[r][6]<<16)|((uint32_t)xmm[r][7]<<24);return lo|((uint64_t)hi<<32);}
static void xmm_set_u64(uint8_t r,uint64_t v){xmm_set_u32(r,(uint32_t)v);uint32_t hi=(uint32_t)(v>>32);xmm[r][4]=(uint8_t)hi;xmm[r][5]=(uint8_t)(hi>>8);xmm[r][6]=(uint8_t)(hi>>16);xmm[r][7]=(uint8_t)(hi>>24);}
static float xmm_get_f32(uint8_t r){union{uint32_t u;float f;}v;v.u=xmm_get_u32(r);return v.f;}
static void xmm_set_f32(uint8_t r,float v){union{uint32_t u;float f;}x;x.f=v;xmm_set_u32(r,x.u);}
static double xmm_get_f64(uint8_t r){union{uint64_t u;double f;}v;v.u=xmm_get_u64(r);return v.f;}
static void xmm_set_f64(uint8_t r,double v){union{uint64_t u;double f;}x;x.f=v;xmm_set_u64(r,x.u);}
static void xmm_reset(void){for(uint32_t r=0;r<8u;r++)for(uint32_t b=0;b<16u;b++)xmm[r][b]=0;}
static void x86_copy_semantic_id(char *dst,const char *src){uint32_t i=0;if(!src)src="NONE";for(;i+1u<X86_SEMANTIC_ID_MAX&&src[i];++i)dst[i]=src[i];dst[i]=0;}
static void x86_trace_reset(void){trace_count=0;trace_head=0;trace_failure_index=0;last_decoded_semantic_id[0]=0;}
static void x86_trace_record(uint32_t before_eip,uint32_t before_flags,uint32_t before_eax,uint32_t before_ecx,uint32_t before_edx,uint32_t before_ebx,uint32_t before_opcode,uint32_t dispatch){
 uint32_t i=trace_head%X86_TRACE_DEPTH;
 trace_eip[i]=before_eip; trace_next_eip[i]=eip; trace_opcode[i]=before_opcode;
 trace_flags[i]=before_flags; trace_eax[i]=before_eax; trace_ecx[i]=before_ecx;
 trace_edx[i]=before_edx; trace_ebx[i]=before_ebx; trace_dispatch[i]=dispatch;
 trace_post_eax[i]=regs[R_EAX]; trace_post_ecx[i]=regs[R_ECX];
 trace_post_edx[i]=regs[R_EDX]; trace_post_ebx[i]=regs[R_EBX];
 trace_post_flags[i]=eflags;
 x86_copy_semantic_id(trace_semantic_id[i],last_decoded_semantic_id);
 trace_head=(trace_head+1u)%X86_TRACE_DEPTH; if(trace_count<X86_TRACE_DEPTH)trace_count++;
 if(regs[R_EAX]==0xDEADC0DEu && before_eax!=0xDEADC0DEu) trace_failure_index=i+1u;
}
enum { X86_DISPATCH_NONE=0, X86_DISPATCH_INC_R32=1, X86_DISPATCH_DEC_R32=2, X86_DISPATCH_RCR=3, X86_DISPATCH_MOV_R8_IMM8=4, X86_DISPATCH_MOV_R16_IMM16=5, X86_DISPATCH_CMP_R16_IMM16=6, X86_DISPATCH_MOV_R32_IMM32=7, X86_DISPATCH_ADD_EAX_IMM=8, X86_DISPATCH_SUB_EAX_IMM=9, X86_DISPATCH_CMP_EAX_IMM=10, X86_DISPATCH_MOV_R32_RM32=11, X86_DISPATCH_MOV_RM32_R32=12, X86_DISPATCH_CMP_R32_RM32=13, X86_DISPATCH_CMP_RM32_R32=14, X86_DISPATCH_JCC=15, X86_DISPATCH_GROUP2=16, X86_DISPATCH_F7=17, X86_DISPATCH_HLT=18, X86_DISPATCH_BT=19, X86_DISPATCH_BTS=20, X86_DISPATCH_BTR=21, X86_DISPATCH_BTC=22, X86_DISPATCH_X87=23, X86_DISPATCH_XOR_RM32_IMM32=24, X86_DISPATCH_SSE_SCALAR=25 };

/* v0.4 guest memory/import foundation. The guest-visible address space is
 * intentionally separate from the WASM allocator used for diagnostics. */
#define GUEST_HEAP_BASE 0x00800000u
#define GUEST_HEAP_LIMIT 0x01F00000u
#define API_BASE 0x70000000u
#define API_GETTICKCOUNT (API_BASE+0x00001000u)
#define API_XWASM_LOG (API_BASE+0x00002000u)
#define API_VIRTUALALLOC (API_BASE+0x00003000u)
#define API_VIRTUALFREE (API_BASE+0x00003004u)
#define API_USER32_CREATEWINDOWEXA (API_BASE+0x00004000u)
#define API_USER32_SHOWWINDOW (API_BASE+0x00004004u)
#define API_USER32_GETDC (API_BASE+0x00004008u)
#define API_USER32_RELEASEDC (API_BASE+0x0000400Cu)
#define API_GDI32_SETPIXEL (API_BASE+0x00005000u)
#define API_GDI32_RECTANGLE (API_BASE+0x00005004u)
#define API_USER32_GETMESSAGEA (API_BASE+0x00006000u)
#define API_USER32_PEEKMESSAGEA (API_BASE+0x00006004u)
#define API_USER32_TRANSLATEMESSAGE (API_BASE+0x00006008u)
#define API_USER32_DISPATCHMESSAGEA (API_BASE+0x0000600Cu)
#define API_USER32_DEFWINDOWPROCA (API_BASE+0x00006010u)
#define API_USER32_POSTQUITMESSAGE (API_BASE+0x00006014u)
#define API_USER32_GETCLIENTRECT (API_BASE+0x00006018u)
#define API_USER32_INVALIDATERECT (API_BASE+0x0000601Cu)
#define API_USER32_UPDATEWINDOW (API_BASE+0x00006020u)
#define API_KERNEL32_BEEP (API_BASE+0x00007000u)
#define API_KERNEL32_CREATEFILEA (API_BASE+0x00008000u)
#define API_KERNEL32_READFILE (API_BASE+0x00008004u)
#define API_KERNEL32_WRITEFILE (API_BASE+0x00008008u)
#define API_KERNEL32_CLOSEHANDLE (API_BASE+0x0000800Cu)
#define API_KERNEL32_SETFILEPOINTER (API_BASE+0x00008010u)
#define API_KERNEL32_GETFILESIZE (API_BASE+0x00008014u)
#define API_KERNEL32_REGOPENKEYEXA (API_BASE+0x00008018u)
#define API_KERNEL32_REGCREATEKEYEXA (API_BASE+0x0000801Cu)
#define API_KERNEL32_REGQUERYVALUEEXA (API_BASE+0x00008020u)
#define API_KERNEL32_REGSETVALUEEXA (API_BASE+0x00008024u)
#define API_KERNEL32_REGCLOSEKEY (API_BASE+0x00008028u)
#define API_KERNEL32_REGDELETEVALUEA (API_BASE+0x0000802Cu)
#define API_KERNEL32_GETLASTERROR (API_BASE+0x00008030u)
#define API_KERNEL32_SETLASTERROR (API_BASE+0x00008034u)
#define API_KERNEL32_SLEEP (API_BASE+0x00008038u)
#define API_KERNEL32_GETMODULEHANDLEA (API_BASE+0x0000803Cu)
#define API_KERNEL32_GETPROCADDRESS (API_BASE+0x00008040u)
#define API_KERNEL32_GETCURRENTPROCESS (API_BASE+0x00008044u)
#define API_KERNEL32_GETCURRENTTHREADID (API_BASE+0x00008048u)
#define API_KERNEL32_HEAPALLOC (API_BASE+0x0000804Cu)
#define API_KERNEL32_HEAPFREE (API_BASE+0x00008050u)
#define API_KERNEL32_HEAPREALLOC (API_BASE+0x00008054u)
#define API_KERNEL32_VIRTUALPROTECT (API_BASE+0x00008058u)
#define API_USER32_REGISTERCLASSEXA (API_BASE+0x00009000u)
#define API_USER32_DESTROYWINDOW (API_BASE+0x00009004u)
#define API_USER32_SETWINDOWPOS (API_BASE+0x00009008u)
#define API_USER32_GETWINDOWRECT (API_BASE+0x0000900Cu)
#define API_USER32_POSTMESSAGEA (API_BASE+0x00009010u)
#define API_USER32_SETFOCUS (API_BASE+0x00009014u)
#define API_USER32_GETCURSORPOS (API_BASE+0x00009018u)
#define API_USER32_SHOWCURSOR (API_BASE+0x0000901Cu)
#define API_USER32_SETCAPTURE (API_BASE+0x00009020u)
#define API_USER32_RELEASECAPTURE (API_BASE+0x00009024u)
#define API_KERNEL32_GETACP (API_BASE+0x0000805Cu)
#define API_KERNEL32_GETOEMCP (API_BASE+0x00008060u)
#define API_KERNEL32_MULTIBYTETOWIDECHAR (API_BASE+0x00008064u)
#define API_KERNEL32_WIDECHARTOMULTIBYTE (API_BASE+0x00008068u)
#define API_GDI32_CREATESOLIDBRUSH (API_BASE+0x0000A000u)
#define API_GDI32_DELETEOBJECT (API_BASE+0x0000A004u)
#define API_GDI32_SELECTOBJECT (API_BASE+0x0000A008u)
#define API_GDI32_FILLRECT (API_BASE+0x0000A00Cu)
#define API_GDI32_BITBLT (API_BASE+0x0000A010u)
#define API_C5_MALLOC (API_BASE+0x00010000u)
#define API_C5_FREE (API_BASE+0x00010004u)
#define API_C5_STRLEN (API_BASE+0x00010008u)
#define API_C5_FS_MOUNT (API_BASE+0x0001000Cu)
#define API_C5_FS_OPEN (API_BASE+0x00010010u)
#define API_C5_FS_READ (API_BASE+0x00010014u)
#define API_C5_FS_CLOSE (API_BASE+0x00010018u)
#define API_C5_REG_CREATE (API_BASE+0x0001001Cu)
#define API_C5_REG_SET (API_BASE+0x00010020u)
#define API_C5_REG_CLOSE (API_BASE+0x00010024u)
#define API_C5_REG_HKEY_CURRENT_USER 0x80000001u
extern int32_t xwasm_input_poll(int32_t msg_ptr,int32_t remove);
extern void xwasm_input_quit(void);
extern void xwasm_audio_beep(int32_t frequency,int32_t duration_ms);
extern void xwasm_gfx_create(int32_t width,int32_t height);
extern void xwasm_gfx_clear(int32_t color);
extern void xwasm_gfx_pixel(int32_t x,int32_t y,int32_t color);
extern void xwasm_gfx_rect(int32_t left,int32_t top,int32_t right,int32_t bottom,int32_t color);
extern void xwasm_gfx_present(void);

/* v0.9 memory allocator state must precede the region helpers that use it. */
static uint32_t guest_vm=0x02000000u;
static uint32_t guest_vm_limit=0x06000000u;
static uint32_t last_virtual_alloc=0,last_virtual_alloc_size=0,virtual_free_count=0;
static uint32_t al4(uint32_t x);
static uint32_t rd32(uint32_t p);
static void wr32(uint32_t p,uint32_t v);
static void wr8(uint32_t p,uint8_t v);
static int x87_push(double v){
 if(x87_count>=8u){cpu_error=0xD801u;return 0;}
 for(uint32_t i=x87_count;i>0u;i--)x87_stack[i]=x87_stack[i-1u];
 x87_stack[0]=v;x87_count++;return 1;
}
static int x87_pop(void){
 if(!x87_count){cpu_error=0xD802u;return 0;}
 for(uint32_t i=1;i<x87_count;i++)x87_stack[i-1u]=x87_stack[i];
 x87_count--;return 1;
}
static int x87_need_top(void){if(!x87_count){cpu_error=0xD802u;return 0;}return 1;}
static float x87_load_f32(uint32_t p){union{uint32_t u;float f;}x;x.u=rd32(p);return x.f;}
static double x87_load_f64(uint32_t p){union{uint64_t u;double d;}x;x.u=(uint64_t)rd32(p)|((uint64_t)rd32(p+4u)<<32);return x.d;}
static void x87_store_f32(uint32_t p,double v){union{uint32_t u;float f;}x;x.f=(float)v;wr32(p,x.u);}
static void x87_store_f64(uint32_t p,double v){union{uint64_t u;double d;}x;x.d=v;wr32(p,(uint32_t)x.u);wr32(p+4u,(uint32_t)(x.u>>32));}
static int x87_modrm_ea(uint8_t m,uint32_t *ip,uint32_t *ea){if((m>>6)==3)return 0;return modrm_ea(m,ip,ea);}



/* v0.9 memory subsystem: explicit guest regions plus checked bulk-memory helpers.
 * The current instruction core still uses its established little-endian accessors;
 * these APIs establish the common memory contract that future CPU/CRT code can use
 * without exposing raw WASM addresses to guest-facing allocation code. */
#define X86_MEM_REGION_MAX 64u
#define X86_MEM_READ  0x01u
#define X86_MEM_WRITE 0x02u
#define X86_MEM_EXEC  0x04u

typedef struct {
 uint32_t base;
 uint32_t size;
 uint32_t flags;
 uint32_t kind;
 uint32_t active;
} x86_mem_region_t;

static x86_mem_region_t x86_mem_regions[X86_MEM_REGION_MAX];
static uint32_t x86_mem_region_count=0;
static uint32_t x86_mem_faults=0;

static void x86_mem_reset(void){
 for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)x86_mem_regions[i].active=0;
 x86_mem_region_count=0; x86_mem_faults=0;
}
static int x86_mem_region_add(uint32_t base,uint32_t size,uint32_t flags,uint32_t kind){
 if(!size||base+size<base)return 0;
 for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(!x86_mem_regions[i].active){
  x86_mem_regions[i].base=base; x86_mem_regions[i].size=size;
  x86_mem_regions[i].flags=flags; x86_mem_regions[i].kind=kind; x86_mem_regions[i].active=1;
  x86_mem_region_count++; return 1;
 }
 return 0;
}
static int x86_mem_region_find(uint32_t p,uint32_t n,uint32_t need){
 if(n==0)return 1;
 uint32_t end=p+n; if(end<p)return 0;
 for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active){
  uint32_t r_end=x86_mem_regions[i].base+x86_mem_regions[i].size;
  if(p>=x86_mem_regions[i].base&&end<=r_end&&(x86_mem_regions[i].flags&need))return 1;
 }
 return 0;
}
static int x86_mem_ensure_wasm(uint32_t end){
 uint32_t pages=__builtin_wasm_memory_size(0u);
 uint32_t have=pages*65536u;
 if(end<=have)return 1;
 uint32_t want=(end+65535u)/65536u;
 if(want>4096u)return 0;
 uint32_t grow=want-pages;
 if(grow==0)return 1;
 return __builtin_wasm_memory_grow(0u,grow)>=0;
}
static uint32_t x86_mem_alloc_region(uint32_t size,uint32_t flags,uint32_t kind){
 uint32_t a=al4(guest_vm),n=al4(size),end;
 if(!size)return 0;
 if(!n)return 0;
 for(uint32_t pass=0;pass<X86_MEM_REGION_MAX;pass++){
  end=a+n;
  if(end<a||end>guest_vm_limit)return 0;
  int overlap=0;
  for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active){
   uint32_t r_end=x86_mem_regions[i].base+x86_mem_regions[i].size;
   if(a<r_end&&end>x86_mem_regions[i].base){
    a=al4(r_end);
    overlap=1;
    break;
   }
  }
  if(!overlap)break;
 }
 end=a+n;
 if(end<a||end>guest_vm_limit||!x86_mem_ensure_wasm(end))return 0;
 if(!x86_mem_region_add(a,n,flags,kind))return 0;
 guest_vm=end; last_virtual_alloc=a; last_virtual_alloc_size=n; return a;
}
static int x86_crt_find_alloc(uint32_t address,uint32_t *size){
 for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active&&x86_mem_regions[i].base==address&&x86_mem_regions[i].kind==5u){
  if(size)*size=x86_mem_regions[i].size; return 1;
 }
 return 0;
}
static uint32_t x86_crt_malloc_impl(uint32_t size){
 return x86_mem_alloc_region(size,X86_MEM_READ|X86_MEM_WRITE,5u);
}
static uint32_t x86_crt_calloc_impl(uint32_t count,uint32_t size){
 if(count&&size>0xFFFFFFFFu/count)return 0;
 uint32_t total=count*size;
 if(!total)return 0;
 uint32_t p=x86_crt_malloc_impl(total);
 if(!p)return 0;
 for(uint32_t i=0;i<total;i++)wr8(p+i,0);
 return p;
}
static uint32_t x86_crt_free_impl(uint32_t address){
 if(!address)return 1;
 for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active&&x86_mem_regions[i].base==address&&x86_mem_regions[i].kind==5u){
  x86_mem_regions[i].active=0; x86_mem_region_count--; return 1;
 }
 x86_mem_faults++; return 0;
}
static uint32_t x86_crt_realloc_impl(uint32_t address,uint32_t size){
 if(!address)return x86_crt_malloc_impl(size);
 if(!size){x86_crt_free_impl(address);return 0;}
 uint32_t old_size=0;
 if(!x86_crt_find_alloc(address,&old_size)){x86_mem_faults++;return 0;}
 if(size<=old_size){
  for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active&&x86_mem_regions[i].base==address&&x86_mem_regions[i].kind==5u){
   x86_mem_regions[i].size=al4(size); return address;
  }
 }
 uint32_t p=x86_crt_malloc_impl(size);
 if(!p)return 0;
 uint32_t n=old_size<size?old_size:size;
 for(uint32_t i=0;i<n;i++)wr8(p+i,MEM8(address+i));
 x86_crt_free_impl(address);
 return p;
}

static uint32_t x86_mem_free_region(uint32_t address){
 for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active&&x86_mem_regions[i].base==address&&x86_mem_regions[i].kind==2u){
  x86_mem_regions[i].active=0; x86_mem_region_count--; virtual_free_count++; return 1;
 }
 return 0;
}
static void x86_mem_register_image(void){
 x86_mem_region_add(image_base,image_size,X86_MEM_READ|X86_MEM_EXEC|X86_MEM_WRITE,1u);
 x86_mem_region_add(GUEST_HEAP_BASE,GUEST_HEAP_LIMIT-GUEST_HEAP_BASE,X86_MEM_READ|X86_MEM_WRITE,3u);
 x86_mem_region_add(0x03E00000u,0x00100000u,X86_MEM_READ|X86_MEM_WRITE,4u);
}

#define X86_FS_MAX_FILES 32u
#define X86_FS_MAX_HANDLES 32u
#define X86_FS_MAX_PATH 256u
#define X86_FS_HANDLE_BASE 0x1000u
#define X86_FS_ACCESS_READ  0x01u
#define X86_FS_ACCESS_WRITE 0x02u
#define X86_FS_OPEN_CREATE  0x04u
#define X86_FS_OPEN_TRUNCATE 0x08u

typedef struct {
 uint32_t used;
 uint32_t data;
 uint32_t size;
 uint32_t capacity;
 char path[X86_FS_MAX_PATH];
} x86_fs_file_t;
typedef struct {
 uint32_t used;
 uint32_t file;
 uint32_t pos;
 uint32_t access;
} x86_fs_handle_t;
static x86_fs_file_t x86_fs_files[X86_FS_MAX_FILES];
static x86_fs_handle_t x86_fs_handles[X86_FS_MAX_HANDLES];
static uint32_t x86_fs_last_error=0;

static void x86_fs_reset(void){
 for(uint32_t i=0;i<X86_FS_MAX_FILES;i++){x86_fs_files[i].used=0;x86_fs_files[i].data=0;x86_fs_files[i].size=0;x86_fs_files[i].capacity=0;x86_fs_files[i].path[0]=0;}
 for(uint32_t i=0;i<X86_FS_MAX_HANDLES;i++)x86_fs_handles[i].used=0;
 x86_fs_last_error=0;
}
static int x86_fs_guest_string(uint32_t ptr,char *out,uint32_t cap){
 if(!ptr||cap<2u)return 0;
 for(uint32_t i=0;i+1u<cap;i++){
  if(!x86_mem_region_find(ptr+i,1u,X86_MEM_READ))return 0;
  uint8_t ch=MEM8(ptr+i);
  if(ch==0){out[i]=0;return 1;}
  out[i]=(char)ch;
 }
 out[cap-1u]=0; return 0;
}
static int x86_fs_normalize(const char *src,char *dst,uint32_t cap){
 uint32_t di=0,seg_start=0;
 if(!src||!dst||cap<2u)return 0;
 dst[0]='/';
 di=1;
 for(uint32_t i=0;src[i];){
  while(src[i]=='/'||src[i]=='\\')i++;
  uint32_t start=i;
  while(src[i]&&src[i]!='/'&&src[i]!='\\')i++;
  uint32_t n=i-start;
  if(!n)continue;
  if(n==1u&&src[start]=='.')continue;
  if(n==2u&&src[start]=='.')return 0;
  if(di>1u){if(di+1u>=cap)return 0;dst[di++]='/';}
  if(di+n>=cap)return 0;
  for(uint32_t j=0;j<n;j++)dst[di++]=src[start+j];
  seg_start=di;
  (void)seg_start;
 }
 if(di==1u){if(cap<2u)return 0;dst[1]=0;}else dst[di]=0;
 return 1;
}
static int x86_fs_find_file(const char *path){
 for(uint32_t i=0;i<X86_FS_MAX_FILES;i++)if(x86_fs_files[i].used){
  uint32_t j=0;while(j<X86_FS_MAX_PATH&&x86_fs_files[i].path[j]&&path[j]&&x86_fs_files[i].path[j]==path[j])j++;
  if(j<X86_FS_MAX_PATH&&x86_fs_files[i].path[j]==0&&path[j]==0)return (int)i;
 }
 return -1;
}
static int x86_fs_find_free_file(void){for(uint32_t i=0;i<X86_FS_MAX_FILES;i++)if(!x86_fs_files[i].used)return (int)i;return -1;}
static int x86_fs_find_free_handle(void){for(uint32_t i=0;i<X86_FS_MAX_HANDLES;i++)if(!x86_fs_handles[i].used)return (int)i;return -1;}
static uint32_t x86_fs_handle_value(uint32_t index){return X86_FS_HANDLE_BASE+index;}
static int x86_fs_handle_index(uint32_t handle){if(handle<X86_FS_HANDLE_BASE||handle>=X86_FS_HANDLE_BASE+X86_FS_MAX_HANDLES)return -1;return (int)(handle-X86_FS_HANDLE_BASE);}
static int x86_fs_resize_file(uint32_t fi,uint32_t size){
 x86_fs_file_t *f=&x86_fs_files[fi];
 if(size<=f->capacity){f->size=size;return 1;}
 uint32_t cap=al4(size);
 if(cap<size)cap=size;
 uint32_t p=x86_mem_alloc_region(cap,X86_MEM_READ|X86_MEM_WRITE,6u);
 if(!p)return 0;
 for(uint32_t i=0;i<f->size;i++)wr8(p+i,MEM8(f->data+i));
 if(f->data){
  for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active&&x86_mem_regions[i].base==f->data&&x86_mem_regions[i].kind==6u){x86_mem_regions[i].active=0;x86_mem_region_count--;break;}
 }
 f->data=p;f->capacity=cap;f->size=size;return 1;
}
static uint32_t x86_fs_mount_impl(const char *raw_path,uint32_t data,uint32_t size){
 char path[X86_FS_MAX_PATH];
 if(!x86_fs_normalize(raw_path,path,sizeof(path))){x86_fs_last_error=3;return 0;}
 if(size&&!x86_mem_region_find(data,size,X86_MEM_READ)){x86_fs_last_error=14;return 0;}
 int fi=x86_fs_find_file(path);
 if(fi<0)fi=x86_fs_find_free_file();
 if(fi<0){x86_fs_last_error=24;return 0;}
 x86_fs_file_t *f=&x86_fs_files[fi];
 if(!f->used){f->used=1;for(uint32_t i=0;i<X86_FS_MAX_PATH;i++){f->path[i]=path[i];if(!path[i])break;}}
 if(size==0){if(f->data){for(uint32_t i=0;i<X86_MEM_REGION_MAX;i++)if(x86_mem_regions[i].active&&x86_mem_regions[i].base==f->data&&x86_mem_regions[i].kind==6u){x86_mem_regions[i].active=0;x86_mem_region_count--;break;}}f->data=0;f->size=0;f->capacity=0;return 1;}
 if(!x86_fs_resize_file((uint32_t)fi,size)){x86_fs_last_error=12;return 0;}
 for(uint32_t i=0;i<size;i++)wr8(f->data+i,MEM8(data+i));
 return 1;
}
static uint32_t x86_fs_open_impl(const char *raw_path,uint32_t access,uint32_t flags){
 char path[X86_FS_MAX_PATH];
 if(!x86_fs_normalize(raw_path,path,sizeof(path))){x86_fs_last_error=3;return 0;}
 int fi=x86_fs_find_file(path);
 if(fi<0){
  if(!(flags&X86_FS_OPEN_CREATE)){x86_fs_last_error=2;return 0;}
  fi=x86_fs_find_free_file();
  if(fi<0){x86_fs_last_error=24;return 0;}
  x86_fs_files[fi].used=1;x86_fs_files[fi].data=0;x86_fs_files[fi].size=0;x86_fs_files[fi].capacity=0;
  for(uint32_t i=0;i<X86_FS_MAX_PATH;i++){x86_fs_files[fi].path[i]=path[i];if(!path[i])break;}
 }else if(flags&X86_FS_OPEN_TRUNCATE){x86_fs_resize_file((uint32_t)fi,0);}
 int hi=x86_fs_find_free_handle();
 if(hi<0){x86_fs_last_error=24;return 0;}
 x86_fs_handles[hi].used=1;x86_fs_handles[hi].file=(uint32_t)fi;x86_fs_handles[hi].pos=0;x86_fs_handles[hi].access=access;
 return x86_fs_handle_value((uint32_t)hi);
}
static uint32_t x86_fs_close_impl(uint32_t handle){
 int hi=x86_fs_handle_index(handle);
 if(hi<0||!x86_fs_handles[hi].used){x86_fs_last_error=6;return 0;}
 x86_fs_handles[hi].used=0;return 1;
}
static uint32_t x86_fs_read_impl(uint32_t handle,uint32_t dst,uint32_t size,uint32_t *read_out){
 if(read_out)*read_out=0;
 int hi=x86_fs_handle_index(handle);
 if(hi<0||!x86_fs_handles[hi].used){x86_fs_last_error=6;return 0;}
 x86_fs_handle_t *h=&x86_fs_handles[hi];x86_fs_file_t *f=&x86_fs_files[h->file];
 if(!(h->access&X86_FS_ACCESS_READ)){x86_fs_last_error=5;return 0;}
 if(size&&!x86_mem_region_find(dst,size,X86_MEM_WRITE)){x86_fs_last_error=14;return 0;}
 uint32_t n=f->size>h->pos?f->size-h->pos:0;if(n>size)n=size;
 for(uint32_t i=0;i<n;i++)wr8(dst+i,MEM8(f->data+h->pos+i));
 h->pos+=n;if(read_out)*read_out=n;return 1;
}
static uint32_t x86_fs_write_impl(uint32_t handle,uint32_t src,uint32_t size,uint32_t *written_out){
 if(written_out)*written_out=0;
 int hi=x86_fs_handle_index(handle);
 if(hi<0||!x86_fs_handles[hi].used){x86_fs_last_error=6;return 0;}
 x86_fs_handle_t *h=&x86_fs_handles[hi];x86_fs_file_t *f=&x86_fs_files[h->file];
 if(!(h->access&X86_FS_ACCESS_WRITE)){x86_fs_last_error=5;return 0;}
 if(size&&!x86_mem_region_find(src,size,X86_MEM_READ)){x86_fs_last_error=14;return 0;}
 uint32_t end=h->pos+size;if(end<h->pos){x86_fs_last_error=8;return 0;}
 if(end>f->size&&!x86_fs_resize_file(h->file,end)){x86_fs_last_error=12;return 0;}
 for(uint32_t i=0;i<size;i++)wr8(f->data+h->pos+i,MEM8(src+i));
 h->pos=end;if(written_out)*written_out=size;return 1;
}
static uint32_t x86_fs_seek_impl(uint32_t handle,int32_t distance,uint32_t origin){
 int hi=x86_fs_handle_index(handle);
 if(hi<0||!x86_fs_handles[hi].used){x86_fs_last_error=6;return 0xFFFFFFFFu;}
 x86_fs_handle_t *h=&x86_fs_handles[hi];x86_fs_file_t *f=&x86_fs_files[h->file];
 int64_t base=origin==0?0:(origin==1?(int64_t)h->pos:(int64_t)f->size),next=base+(int64_t)distance;
 if(next<0||next>0xFFFFFFFFll){x86_fs_last_error=22;return 0xFFFFFFFFu;}
 h->pos=(uint32_t)next;return h->pos;
}
static uint32_t x86_fs_size_impl(uint32_t handle){
 int hi=x86_fs_handle_index(handle);
 if(hi<0||!x86_fs_handles[hi].used){x86_fs_last_error=6;return 0xFFFFFFFFu;}
 return x86_fs_files[x86_fs_handles[hi].file].size;
}
static uint32_t x86_fs_mount_impl_from_guest(uint32_t path_ptr,uint32_t data_ptr,uint32_t size){
 char raw[X86_FS_MAX_PATH];if(!x86_fs_guest_string(path_ptr,raw,sizeof(raw)))return 0;return x86_fs_mount_impl(raw,data_ptr,size);
}
static uint32_t x86_fs_open_impl_from_guest(uint32_t path_ptr,uint32_t access,uint32_t flags){
 char raw[X86_FS_MAX_PATH];if(!x86_fs_guest_string(path_ptr,raw,sizeof(raw)))return 0;return x86_fs_open_impl(raw,access,flags);
}
static uint32_t x86_fs_c5_read_count=0;
static uint32_t x86_fs_read_c5(uint32_t handle,uint32_t dst,uint32_t size){
 uint32_t n=0,ok=x86_fs_read_impl(handle,dst,size,&n);x86_fs_c5_read_count=n;return ok;
}
static uint32_t x86_fs_exists_impl(const char *raw_path){
 char path[X86_FS_MAX_PATH];if(!x86_fs_normalize(raw_path,path,sizeof(path)))return 0;
 return x86_fs_find_file(path)>=0?1u:0u;
}

/* C4 game registry: a deterministic, in-memory Win32-compatible subset.
 * It intentionally avoids the host OS registry. Keys and values are small and
 * fixed-capacity because this is a game compatibility facility, not OS emulation. */
#define X86_REG_MAX_KEYS 64u
#define X86_REG_MAX_VALUES 128u
#define X86_REG_MAX_PATH 256u
#define X86_REG_MAX_VALUE_NAME 128u
#define X86_REG_MAX_VALUE_DATA 4096u
#define X86_REG_HANDLE_BASE 0x2000u
#define X86_REG_HKEY_CURRENT_USER  0x80000001u
#define X86_REG_HKEY_LOCAL_MACHINE 0x80000002u
#define X86_REG_REG_SZ 1u
#define X86_REG_REG_EXPAND_SZ 2u
#define X86_REG_REG_BINARY 3u
#define X86_REG_REG_DWORD 4u
#define X86_REG_ERROR_SUCCESS 0u
#define X86_REG_ERROR_FILE_NOT_FOUND 2u
#define X86_REG_ERROR_ACCESS_DENIED 5u
#define X86_REG_ERROR_INVALID_HANDLE 6u
#define X86_REG_ERROR_INVALID_PARAMETER 87u
#define X86_REG_ERROR_MORE_DATA 234u
#define X86_REG_ERROR_ALREADY_EXISTS 183u
#define X86_REG_ERROR_OUTOFMEMORY 14u

typedef struct {
 uint32_t used;
 uint32_t hive;
 char path[X86_REG_MAX_PATH];
} x86_reg_key_t;
typedef struct {
 uint32_t used;
 uint32_t key;
 uint32_t type;
 uint32_t size;
 char name[X86_REG_MAX_VALUE_NAME];
 uint8_t data[X86_REG_MAX_VALUE_DATA];
} x86_reg_value_t;
static x86_reg_key_t x86_reg_keys[X86_REG_MAX_KEYS];
static x86_reg_value_t x86_reg_values[X86_REG_MAX_VALUES];
static uint32_t x86_reg_last_error=0;

static void x86_reg_set_error(uint32_t error){x86_reg_last_error=error;crt_last_error=error;}
static void x86_reg_reset(void){
 for(uint32_t i=0;i<X86_REG_MAX_KEYS;i++){x86_reg_keys[i].used=0;x86_reg_keys[i].hive=0;x86_reg_keys[i].path[0]=0;}
 for(uint32_t i=0;i<X86_REG_MAX_VALUES;i++){x86_reg_values[i].used=0;x86_reg_values[i].key=0;x86_reg_values[i].type=0;x86_reg_values[i].size=0;x86_reg_values[i].name[0]=0;}
 x86_reg_last_error=0;
}
static int x86_reg_hive(uint32_t handle){
 if(handle==X86_REG_HKEY_CURRENT_USER)return 1;
 if(handle==X86_REG_HKEY_LOCAL_MACHINE)return 2;
 if(handle>=X86_REG_HANDLE_BASE&&handle<X86_REG_HANDLE_BASE+X86_REG_MAX_KEYS){
  uint32_t i=handle-X86_REG_HANDLE_BASE;
  if(x86_reg_keys[i].used)return (int)x86_reg_keys[i].hive;
 }
 return 0;
}
static int x86_reg_key_index(uint32_t handle){
 if(handle<X86_REG_HANDLE_BASE||handle>=X86_REG_HANDLE_BASE+X86_REG_MAX_KEYS)return -1;
 uint32_t i=handle-X86_REG_HANDLE_BASE;
 return x86_reg_keys[i].used?(int)i:-1;
}
static int x86_reg_path_equal(const char *a,const char *b){
 uint32_t i=0;while(i<X86_REG_MAX_PATH&&a[i]&&b[i]){
  char ca=a[i],cb=b[i];
  if(ca>='a'&&ca<='z')ca=(char)(ca-'a'+'A');
  if(cb>='a'&&cb<='z')cb=(char)(cb-'a'+'A');
  if(ca!=cb)return 0;i++;
 }
 return i<X86_REG_MAX_PATH&&a[i]==0&&b[i]==0;
}
static int x86_reg_normalize_subkey(const char *src,char *dst,uint32_t cap){
 uint32_t di=0;
 if(!dst||cap<2u)return 0;
 for(uint32_t i=0;src&&src[i];){
  while(src[i]=='\\'||src[i]=='/')i++;
  uint32_t start=i;
  while(src[i]&&src[i]!='\\'&&src[i]!='/')i++;
  uint32_t n=i-start;
  if(!n)continue;
  if(n==1u&&src[start]=='.')continue;
  if(n==2u&&src[start]=='.')return 0;
  if(di&&di+1u>=cap)return 0;
  if(di)dst[di++]='\\';
  if(di+n>=cap)return 0;
  for(uint32_t j=0;j<n;j++)dst[di++]=src[start+j];
 }
 dst[di]=0;return 1;
}
static int x86_reg_find_key_path(uint32_t hive,const char *path){
 for(uint32_t i=0;i<X86_REG_MAX_KEYS;i++)if(x86_reg_keys[i].used&&x86_reg_keys[i].hive==hive&&x86_reg_path_equal(x86_reg_keys[i].path,path))return (int)i;
 return -1;
}
static int x86_reg_find_free_key(void){for(uint32_t i=0;i<X86_REG_MAX_KEYS;i++)if(!x86_reg_keys[i].used)return (int)i;return -1;}
static int x86_reg_find_value(uint32_t key,const char *name){
 for(uint32_t i=0;i<X86_REG_MAX_VALUES;i++)if(x86_reg_values[i].used&&x86_reg_values[i].key==key&&x86_reg_path_equal(x86_reg_values[i].name,name))return (int)i;
 return -1;
}
static int x86_reg_find_free_value(void){for(uint32_t i=0;i<X86_REG_MAX_VALUES;i++)if(!x86_reg_values[i].used)return (int)i;return -1;}
static uint32_t x86_reg_key_handle(uint32_t index){return X86_REG_HANDLE_BASE+index;}
static uint32_t x86_reg_build_path(uint32_t parent,const char *sub,char *out,uint32_t cap,uint32_t *hive_out){
 uint32_t hive=0;int pi=x86_reg_key_index(parent);
 if(parent==X86_REG_HKEY_CURRENT_USER)hive=1;else if(parent==X86_REG_HKEY_LOCAL_MACHINE)hive=2;else if(pi>=0)hive=x86_reg_keys[pi].hive;else return 0;
 char norm[X86_REG_MAX_PATH];
 if(!x86_reg_normalize_subkey(sub?sub:"",norm,sizeof(norm)))return 0;
 uint32_t di=0;
 if(pi>=0){while(di+1u<cap&&x86_reg_keys[pi].path[di]){out[di]=x86_reg_keys[pi].path[di];di++;}if(norm[0]){if(di+1u>=cap)return 0;out[di++]='\\';}}
 else if(norm[0]){ /* root handles have an empty relative path */ }
 for(uint32_t i=0;norm[i];i++){if(di+1u>=cap)return 0;out[di++]=norm[i];}
 out[di]=0;if(hive_out)*hive_out=hive;return 1;
}
static uint32_t x86_reg_open_impl(uint32_t parent,const char *sub,uint32_t *out_handle){
 if(out_handle)*out_handle=0;
 char path[X86_REG_MAX_PATH];uint32_t hive=0;
 if(!x86_reg_build_path(parent,sub,path,sizeof(path),&hive)){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 if(!path[0]){if(out_handle)*out_handle=parent; x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;}
 int ki=x86_reg_find_key_path(hive,path);
 if(ki<0){x86_reg_set_error(X86_REG_ERROR_FILE_NOT_FOUND);return X86_REG_ERROR_FILE_NOT_FOUND;}
 if(out_handle)*out_handle=x86_reg_key_handle((uint32_t)ki);x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;
}
static uint32_t x86_reg_create_impl(uint32_t parent,const char *sub,uint32_t *out_handle,uint32_t *disposition){
 if(out_handle)*out_handle=0;if(disposition)*disposition=1u;
 char norm[X86_REG_MAX_PATH],full[X86_REG_MAX_PATH];uint32_t hive=0;int pi=x86_reg_key_index(parent);
 if(parent!=X86_REG_HKEY_CURRENT_USER&&parent!=X86_REG_HKEY_LOCAL_MACHINE&&pi<0){x86_reg_set_error(X86_REG_ERROR_INVALID_HANDLE);return X86_REG_ERROR_INVALID_HANDLE;}
 if(!x86_reg_normalize_subkey(sub?sub:"",norm,sizeof(norm))){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 if(!x86_reg_build_path(parent,norm,full,sizeof(full),&hive)){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 if(!full[0]){if(out_handle)*out_handle=parent;if(disposition)*disposition=2u;x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;}
 uint32_t final_existed=x86_reg_find_key_path(hive,full)>=0?1u:0u;
 /* RegCreateKeyExA creates missing intermediate keys as part of the requested path. */
 uint32_t start=0,last=0;
 while(1){
  while(full[start]=='\\')start++;
  uint32_t i=start;while(full[i]&&full[i]!='\\')i++;
  if(i>start){
   char prefix[X86_REG_MAX_PATH];uint32_t n=i;
   if(n>=sizeof(prefix)){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
   for(uint32_t j=0;j<n;j++)prefix[j]=full[j];prefix[n]=0;
   int existing=x86_reg_find_key_path(hive,prefix);
   if(existing<0){
    int created=x86_reg_find_free_key();
    if(created<0){x86_reg_set_error(X86_REG_ERROR_OUTOFMEMORY);return X86_REG_ERROR_OUTOFMEMORY;}
    x86_reg_keys[created].used=1;x86_reg_keys[created].hive=hive;
    for(uint32_t j=0;j<=n;j++)x86_reg_keys[created].path[j]=prefix[j];
    last=(uint32_t)created;
   }else last=(uint32_t)existing;
  }
  if(!full[i])break;
  start=i+1u;
 }
 if(out_handle)*out_handle=x86_reg_key_handle(last);
 if(disposition)*disposition=final_existed?2u:1u;
 x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;
}
static uint32_t x86_reg_close_impl(uint32_t handle){
 if(handle==X86_REG_HKEY_CURRENT_USER||handle==X86_REG_HKEY_LOCAL_MACHINE){x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;}
 int ki=x86_reg_key_index(handle);if(ki<0){x86_reg_set_error(X86_REG_ERROR_INVALID_HANDLE);return X86_REG_ERROR_INVALID_HANDLE;}
 x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;
}
static uint32_t x86_reg_set_value_impl(uint32_t handle,const char *name,uint32_t type,const uint8_t *data,uint32_t size){
 int ki=x86_reg_key_index(handle);if(ki<0){x86_reg_set_error(X86_REG_ERROR_INVALID_HANDLE);return X86_REG_ERROR_INVALID_HANDLE;}
 if(type!=X86_REG_REG_SZ&&type!=X86_REG_REG_EXPAND_SZ&&type!=X86_REG_REG_BINARY&&type!=X86_REG_REG_DWORD){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 if(size>X86_REG_MAX_VALUE_DATA||(type==X86_REG_REG_DWORD&&size!=4u)){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 if(size&&!data){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 int vi=x86_reg_find_value((uint32_t)ki,name?name:"");
 if(vi<0){vi=x86_reg_find_free_value();if(vi<0){x86_reg_set_error(X86_REG_ERROR_OUTOFMEMORY);return X86_REG_ERROR_OUTOFMEMORY;}x86_reg_values[vi].used=1;x86_reg_values[vi].key=(uint32_t)ki;}
 x86_reg_value_t *v=&x86_reg_values[vi];v->type=type;v->size=size;
 for(uint32_t i=0;i<X86_REG_MAX_VALUE_NAME;i++){v->name[i]=(name&&name[i])?name[i]:0;if(!name||!name[i])break;}
 for(uint32_t i=0;i<size;i++)v->data[i]=data[i];
 x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;
}
static uint32_t x86_reg_query_value_impl(uint32_t handle,const char *name,uint32_t *type,uint8_t *data,uint32_t *size){
 int ki=x86_reg_key_index(handle);if(ki<0){x86_reg_set_error(X86_REG_ERROR_INVALID_HANDLE);return X86_REG_ERROR_INVALID_HANDLE;}
 int vi=x86_reg_find_value((uint32_t)ki,name?name:"");if(vi<0){x86_reg_set_error(X86_REG_ERROR_FILE_NOT_FOUND);return X86_REG_ERROR_FILE_NOT_FOUND;}
 x86_reg_value_t *v=&x86_reg_values[vi];
 if(type)*type=v->type;
 if(!size){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 uint32_t capacity=*size;*size=v->size;
 if(v->size&&!data){x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;}
 if(capacity<v->size){x86_reg_set_error(X86_REG_ERROR_MORE_DATA);return X86_REG_ERROR_MORE_DATA;}
 if(v->size&&data&&!x86_mem_region_find((uint32_t)(uintptr_t)data,v->size,X86_MEM_WRITE)){x86_reg_set_error(X86_REG_ERROR_INVALID_PARAMETER);return X86_REG_ERROR_INVALID_PARAMETER;}
 if(v->size&&data)for(uint32_t i=0;i<v->size;i++)data[i]=v->data[i];
 x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;
}
static uint32_t x86_reg_create_guest_impl(uint32_t parent,uint32_t sub_ptr,uint32_t out_ptr,uint32_t *handle,uint32_t *disp){
 char raw[X86_REG_MAX_PATH];if(sub_ptr&&!x86_fs_guest_string(sub_ptr,raw,sizeof(raw)))return X86_REG_ERROR_INVALID_PARAMETER;
 uint32_t result=x86_reg_create_impl(parent,sub_ptr?raw:"",handle,disp);
 if(result==X86_REG_ERROR_SUCCESS&&(!out_ptr||!x86_mem_region_find(out_ptr,4u,X86_MEM_WRITE)))return X86_REG_ERROR_INVALID_PARAMETER;
 if(result==X86_REG_ERROR_SUCCESS)wr32(out_ptr,*handle);
 return result;
}
static uint32_t x86_reg_set_guest_impl(uint32_t handle,uint32_t name_ptr,uint32_t type,uint32_t data_ptr,uint32_t size){
 char raw[X86_REG_MAX_VALUE_NAME];if(name_ptr&&!x86_fs_guest_string(name_ptr,raw,sizeof(raw)))return X86_REG_ERROR_INVALID_PARAMETER;
 if(size&&!x86_mem_region_find(data_ptr,size,X86_MEM_READ))return X86_REG_ERROR_INVALID_PARAMETER;
 uint8_t tmp[X86_REG_MAX_VALUE_DATA];if(size>sizeof(tmp))return X86_REG_ERROR_INVALID_PARAMETER;
 for(uint32_t i=0;i<size;i++)tmp[i]=MEM8(data_ptr+i);
 return x86_reg_set_value_impl(handle,name_ptr?raw:"",type,tmp,size);
}
static uint32_t x86_reg_delete_value_impl(uint32_t handle,const char *name){
 int ki=x86_reg_key_index(handle);if(ki<0){x86_reg_set_error(X86_REG_ERROR_INVALID_HANDLE);return X86_REG_ERROR_INVALID_HANDLE;}
 int vi=x86_reg_find_value((uint32_t)ki,name?name:"");if(vi<0){x86_reg_set_error(X86_REG_ERROR_FILE_NOT_FOUND);return X86_REG_ERROR_FILE_NOT_FOUND;}
 x86_reg_values[vi].used=0;x86_reg_set_error(X86_REG_ERROR_SUCCESS);return X86_REG_ERROR_SUCCESS;
}
static uint32_t x86_reg_key_exists_impl(uint32_t parent,const char *sub){
 char path[X86_REG_MAX_PATH];uint32_t hive=0;
 if(!x86_reg_build_path(parent,sub,path,sizeof(path),&hive))return 0;
 return x86_reg_find_key_path(hive,path)>=0?1u:0u;
}
static uint32_t x86_reg_value_exists_impl(uint32_t handle,const char *name){
 int ki=x86_reg_key_index(handle);if(ki<0)return 0;
 return x86_reg_find_value((uint32_t)ki,name?name:"")>=0?1u:0u;
}

static uint32_t guest_heap=GUEST_HEAP_BASE;
static uint32_t import_resolved=0,import_failed=0;
static uint32_t message_count=0,message_last=0,message_quit=0,mouse_clicks=0,mouse_right_clicks=0,mouse_middle_clicks=0,mouse_moves=0;
static uint32_t surface_width=640,surface_height=360;
static uint32_t gdi_brush_color=0x00FFFFFFu;
static uint32_t last_import_dll=0,last_import_func=0,last_import_thunk=0,last_import_target=0;
static uint32_t last_failed_import_dll=0,last_failed_import_func=0;

static uint32_t al4(uint32_t x){return(x+3u)&~3u;}
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
 if(streq_ascii(dll,"XWASMHOST.dll")||streq_ascii(dll,"xwasmhost.dll")){
  if(streq_ascii(name,"xwasm_log"))return API_XWASM_LOG;
 }
 if(streq_ascii(dll,"KERNEL32.dll")||streq_ascii(dll,"kernel32.dll")){
  if(streq_ascii(name,"VirtualAlloc"))return API_VIRTUALALLOC;
  if(streq_ascii(name,"VirtualFree"))return API_VIRTUALFREE;
 }
 if(streq_ascii(dll,"USER32.dll")||streq_ascii(dll,"user32.dll")){
  if(streq_ascii(name,"CreateWindowExA"))return API_USER32_CREATEWINDOWEXA;
  if(streq_ascii(name,"ShowWindow"))return API_USER32_SHOWWINDOW;
  if(streq_ascii(name,"GetDC"))return API_USER32_GETDC;
  if(streq_ascii(name,"ReleaseDC"))return API_USER32_RELEASEDC;
 }
 if(streq_ascii(dll,"GDI32.dll")||streq_ascii(dll,"gdi32.dll")){
  if(streq_ascii(name,"SetPixel"))return API_GDI32_SETPIXEL;
  if(streq_ascii(name,"Rectangle"))return API_GDI32_RECTANGLE;
  if(streq_ascii(name,"CreateSolidBrush"))return API_GDI32_CREATESOLIDBRUSH;
  if(streq_ascii(name,"DeleteObject"))return API_GDI32_DELETEOBJECT;
  if(streq_ascii(name,"SelectObject"))return API_GDI32_SELECTOBJECT;
  if(streq_ascii(name,"FillRect"))return API_GDI32_FILLRECT;
  if(streq_ascii(name,"BitBlt"))return API_GDI32_BITBLT;
 }
 if(streq_ascii(dll,"USER32.dll")||streq_ascii(dll,"user32.dll")){
  if(streq_ascii(name,"GetMessageA"))return API_USER32_GETMESSAGEA;
  if(streq_ascii(name,"PeekMessageA"))return API_USER32_PEEKMESSAGEA;
  if(streq_ascii(name,"TranslateMessage"))return API_USER32_TRANSLATEMESSAGE;
  if(streq_ascii(name,"DispatchMessageA"))return API_USER32_DISPATCHMESSAGEA;
  if(streq_ascii(name,"DefWindowProcA"))return API_USER32_DEFWINDOWPROCA;
  if(streq_ascii(name,"PostQuitMessage"))return API_USER32_POSTQUITMESSAGE;
  if(streq_ascii(name,"GetClientRect"))return API_USER32_GETCLIENTRECT;
  if(streq_ascii(name,"InvalidateRect"))return API_USER32_INVALIDATERECT;
  if(streq_ascii(name,"UpdateWindow"))return API_USER32_UPDATEWINDOW;
  if(streq_ascii(name,"RegisterClassExA"))return API_USER32_REGISTERCLASSEXA;
  if(streq_ascii(name,"DestroyWindow"))return API_USER32_DESTROYWINDOW;
  if(streq_ascii(name,"SetWindowPos"))return API_USER32_SETWINDOWPOS;
  if(streq_ascii(name,"GetWindowRect"))return API_USER32_GETWINDOWRECT;
  if(streq_ascii(name,"PostMessageA"))return API_USER32_POSTMESSAGEA;
  if(streq_ascii(name,"SetFocus"))return API_USER32_SETFOCUS;
  if(streq_ascii(name,"GetCursorPos"))return API_USER32_GETCURSORPOS;
  if(streq_ascii(name,"ShowCursor"))return API_USER32_SHOWCURSOR;
  if(streq_ascii(name,"SetCapture"))return API_USER32_SETCAPTURE;
  if(streq_ascii(name,"ReleaseCapture"))return API_USER32_RELEASECAPTURE;
 }
 if(streq_ascii(dll,"KERNEL32.dll")||streq_ascii(dll,"kernel32.dll")){
  if(streq_ascii(name,"Beep"))return API_KERNEL32_BEEP;
 }
 if(streq_ascii(dll,"KERNEL32.dll")||streq_ascii(dll,"kernel32.dll")){
  if(streq_ascii(name,"CreateFileA"))return API_KERNEL32_CREATEFILEA;
  if(streq_ascii(name,"ReadFile"))return API_KERNEL32_READFILE;
  if(streq_ascii(name,"WriteFile"))return API_KERNEL32_WRITEFILE;
  if(streq_ascii(name,"CloseHandle"))return API_KERNEL32_CLOSEHANDLE;
  if(streq_ascii(name,"SetFilePointer"))return API_KERNEL32_SETFILEPOINTER;
  if(streq_ascii(name,"GetFileSize"))return API_KERNEL32_GETFILESIZE;
  if(streq_ascii(name,"RegOpenKeyExA"))return API_KERNEL32_REGOPENKEYEXA;
  if(streq_ascii(name,"RegCreateKeyExA"))return API_KERNEL32_REGCREATEKEYEXA;
  if(streq_ascii(name,"RegQueryValueExA"))return API_KERNEL32_REGQUERYVALUEEXA;
  if(streq_ascii(name,"RegSetValueExA"))return API_KERNEL32_REGSETVALUEEXA;
  if(streq_ascii(name,"RegCloseKey"))return API_KERNEL32_REGCLOSEKEY;
  if(streq_ascii(name,"RegDeleteValueA"))return API_KERNEL32_REGDELETEVALUEA;
  if(streq_ascii(name,"GetLastError"))return API_KERNEL32_GETLASTERROR;
  if(streq_ascii(name,"SetLastError"))return API_KERNEL32_SETLASTERROR;
  if(streq_ascii(name,"Sleep"))return API_KERNEL32_SLEEP;
  if(streq_ascii(name,"GetModuleHandleA"))return API_KERNEL32_GETMODULEHANDLEA;
  if(streq_ascii(name,"GetProcAddress"))return API_KERNEL32_GETPROCADDRESS;
  if(streq_ascii(name,"GetCurrentProcess"))return API_KERNEL32_GETCURRENTPROCESS;
  if(streq_ascii(name,"GetCurrentThreadId"))return API_KERNEL32_GETCURRENTTHREADID;
  if(streq_ascii(name,"HeapAlloc"))return API_KERNEL32_HEAPALLOC;
  if(streq_ascii(name,"HeapFree"))return API_KERNEL32_HEAPFREE;
  if(streq_ascii(name,"HeapReAlloc"))return API_KERNEL32_HEAPREALLOC;
  if(streq_ascii(name,"VirtualProtect"))return API_KERNEL32_VIRTUALPROTECT;
  if(streq_ascii(name,"GetACP"))return API_KERNEL32_GETACP;
  if(streq_ascii(name,"GetOEMCP"))return API_KERNEL32_GETOEMCP;
  if(streq_ascii(name,"MultiByteToWideChar"))return API_KERNEL32_MULTIBYTETOWIDECHAR;
  if(streq_ascii(name,"WideCharToMultiByte"))return API_KERNEL32_WIDECHARTOMULTIBYTE;
 }
 if(streq_ascii(dll,"XWASMCRT.dll")||streq_ascii(dll,"xwasmcrt.dll"))return 0; /* C5 uses direct cdecl API addresses. */
 if(streq_ascii(dll,"ADVAPI32.dll")||streq_ascii(dll,"advapi32.dll")){
  if(streq_ascii(name,"RegOpenKeyExA"))return API_KERNEL32_REGOPENKEYEXA;
  if(streq_ascii(name,"RegCreateKeyExA"))return API_KERNEL32_REGCREATEKEYEXA;
  if(streq_ascii(name,"RegQueryValueExA"))return API_KERNEL32_REGQUERYVALUEEXA;
  if(streq_ascii(name,"RegSetValueExA"))return API_KERNEL32_REGSETVALUEEXA;
  if(streq_ascii(name,"RegCloseKey"))return API_KERNEL32_REGCLOSEKEY;
  if(streq_ascii(name,"RegDeleteValueA"))return API_KERNEL32_REGDELETEVALUEA;
 }
 return 0;
}
static uint32_t x86_crt_strlen(uint32_t s);
static uint32_t call_builtin(uint32_t target){
 if(target==API_C5_MALLOC){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_crt_malloc_impl(rd32(sp+4u));return 1;}
 if(target==API_C5_FREE){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_crt_free_impl(rd32(sp+4u));return 1;}
 if(target==API_C5_STRLEN){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_crt_strlen(rd32(sp+4u));return 1;}
 if(target==API_C5_FS_MOUNT){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_fs_mount_impl_from_guest(rd32(sp+4u),rd32(sp+8u),rd32(sp+12u));return 1;}
 if(target==API_C5_FS_OPEN){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_fs_open_impl_from_guest(rd32(sp+4u),rd32(sp+8u),rd32(sp+12u));return 1;}
 if(target==API_C5_FS_READ){uint32_t sp=regs[R_ESP];uint32_t n=0,ok=x86_fs_read_impl(rd32(sp+4u),rd32(sp+8u),rd32(sp+12u),&n);regs[R_EAX]=ok?n:0xFFFFFFFFu;return 1;}
 if(target==API_C5_FS_CLOSE){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_fs_close_impl(rd32(sp+4u));return 1;}
 if(target==API_C5_REG_CREATE){uint32_t sp=regs[R_ESP],handle=0,disp=0;regs[R_EAX]=x86_reg_create_guest_impl(rd32(sp+4u),rd32(sp+8u),rd32(sp+12u),&handle,&disp);return 1;}
 if(target==API_C5_REG_SET){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_reg_set_guest_impl(rd32(sp+4u),rd32(sp+8u),rd32(sp+12u),rd32(sp+16u),rd32(sp+20u));return 1;}
 if(target==API_C5_REG_CLOSE){uint32_t sp=regs[R_ESP];regs[R_EAX]=x86_reg_close_impl(rd32(sp+4u));return 1;}
 if(target==API_GETTICKCOUNT){regs[R_EAX]=1234u;return 1;}
 if(target==API_XWASM_LOG){
  xwasm_log(1,(int32_t)regs[R_ECX],(int32_t)regs[R_EDX]);
  return 1;
 }
 if(target==API_VIRTUALALLOC){
  /* Win32 stdcall: lpAddress, dwSize, flAllocationType, flProtect. */
  uint32_t sp=regs[R_ESP];
  uint32_t size=al4(rd32(sp+8u));
  if(!size){regs[R_EAX]=0;regs[R_ESP]+=16u;return 1;}
  uint32_t a=x86_mem_alloc_region(size,X86_MEM_READ|X86_MEM_WRITE,2u);
  if(!a){regs[R_EAX]=0;regs[R_ESP]+=16u;return 1;}
  regs[R_EAX]=a;
  regs[R_ESP]+=16u;
  return 1;
 }
 if(target==API_KERNEL32_SLEEP){
  uint32_t sp=regs[R_ESP]; (void)rd32(sp+4u); regs[R_EAX]=0u; regs[R_ESP]+=4u; return 1;
 }
 if(target==API_KERNEL32_GETMODULEHANDLEA){
  uint32_t sp=regs[R_ESP],name=rd32(sp+4u);
  if(name&&!streq_ascii(name,"xwasm.exe")&&!streq_ascii(name,"XWASM.exe")&&
     !streq_ascii(name,"kernel32.dll")&&!streq_ascii(name,"KERNEL32.dll")){
   regs[R_EAX]=0u;
  } else regs[R_EAX]=image_base?image_base:IMAGE_BASE;
  regs[R_ESP]+=4u; return 1;
 }
 if(target==API_KERNEL32_GETPROCADDRESS){
  uint32_t sp=regs[R_ESP],name=rd32(sp+8u),target_api=0;
  if(name){
   if(streq_ascii(name,"GetTickCount"))target_api=API_GETTICKCOUNT;
   else if(streq_ascii(name,"VirtualAlloc"))target_api=API_VIRTUALALLOC;
   else if(streq_ascii(name,"VirtualFree"))target_api=API_VIRTUALFREE;
   else if(streq_ascii(name,"Sleep"))target_api=API_KERNEL32_SLEEP;
   else if(streq_ascii(name,"HeapAlloc"))target_api=API_KERNEL32_HEAPALLOC;
   else if(streq_ascii(name,"HeapFree"))target_api=API_KERNEL32_HEAPFREE;
   else if(streq_ascii(name,"HeapReAlloc"))target_api=API_KERNEL32_HEAPREALLOC;
   else if(streq_ascii(name,"VirtualProtect"))target_api=API_KERNEL32_VIRTUALPROTECT;
   else if(streq_ascii(name,"GetLastError"))target_api=API_KERNEL32_GETLASTERROR;
   else if(streq_ascii(name,"SetLastError"))target_api=API_KERNEL32_SETLASTERROR;
  }
  regs[R_EAX]=target_api; regs[R_ESP]+=8u; return 1;
 }
 if(target==API_KERNEL32_GETCURRENTPROCESS){regs[R_EAX]=0xFFFFFFFFu;return 1;}
 if(target==API_KERNEL32_GETCURRENTTHREADID){regs[R_EAX]=1u;return 1;}
 if(target==API_KERNEL32_HEAPALLOC){
  uint32_t sp=regs[R_ESP],size=rd32(sp+12u);
  regs[R_EAX]=size?x86_crt_malloc_impl(size):0u; regs[R_ESP]+=12u; return 1;
 }
 if(target==API_KERNEL32_HEAPFREE){
  uint32_t sp=regs[R_ESP],p=rd32(sp+12u);
  regs[R_EAX]=x86_crt_free_impl(p); regs[R_ESP]+=12u; return 1;
 }
 if(target==API_KERNEL32_HEAPREALLOC){
  uint32_t sp=regs[R_ESP],p=rd32(sp+12u),size=rd32(sp+16u);
  regs[R_EAX]=x86_crt_realloc_impl(p,size); regs[R_ESP]+=16u; return 1;
 }
 if(target==API_KERNEL32_VIRTUALPROTECT){
  uint32_t sp=regs[R_ESP],addr=rd32(sp+4u),size=rd32(sp+8u),old=rd32(sp+16u);
  uint32_t ok=(size&&x86_mem_region_find(addr,size,X86_MEM_READ))?1u:0u;
  if(old&&x86_mem_region_find(old,4u,X86_MEM_WRITE))wr32(old,X86_MEM_READ|X86_MEM_WRITE);
  regs[R_EAX]=ok; regs[R_ESP]+=16u; return 1;
 }
 if(target==API_USER32_REGISTERCLASSEXA){
  uint32_t sp=regs[R_ESP],cls=rd32(sp+4u);
  regs[R_EAX]=cls?1u:0u; regs[R_ESP]+=4u; return 1;
 }
 if(target==API_USER32_DESTROYWINDOW){
  uint32_t sp=regs[R_ESP]; (void)rd32(sp+4u); xwasm_gfx_present(); regs[R_EAX]=1u; regs[R_ESP]+=4u; return 1;
 }
 if(target==API_USER32_SETWINDOWPOS){
  uint32_t sp=regs[R_ESP],x=rd32(sp+12u),y=rd32(sp+16u),w=rd32(sp+20u),h=rd32(sp+24u);
  if(w>=64u&&w<=1920u)surface_width=w; if(h>=64u&&h<=1080u)surface_height=h;
  (void)x; (void)y; xwasm_gfx_create((int32_t)surface_width,(int32_t)surface_height); xwasm_gfx_present();
  regs[R_EAX]=1u; regs[R_ESP]+=28u; return 1;
 }
 if(target==API_USER32_GETWINDOWRECT){
  uint32_t sp=regs[R_ESP],rect=rd32(sp+8u);
  if(rect&&x86_mem_region_find(rect,16u,X86_MEM_WRITE)){wr32(rect,0);wr32(rect+4u,0);wr32(rect+8u,surface_width);wr32(rect+12u,surface_height);regs[R_EAX]=1u;}
  else regs[R_EAX]=0u;
  regs[R_ESP]+=8u; return 1;
 }
 if(target==API_USER32_POSTMESSAGEA){
  uint32_t sp=regs[R_ESP],msg=rd32(sp+8u); message_last=msg; message_count++;
  regs[R_EAX]=1u; regs[R_ESP]+=20u; return 1;
 }
 if(target==API_USER32_SETFOCUS){uint32_t sp=regs[R_ESP];regs[R_EAX]=rd32(sp+4u);regs[R_ESP]+=4u;return 1;}
 if(target==API_USER32_GETCURSORPOS){
  uint32_t sp=regs[R_ESP],pt=rd32(sp+4u);
  if(pt&&x86_mem_region_find(pt,8u,X86_MEM_WRITE)){wr32(pt,0);wr32(pt+4u,0);regs[R_EAX]=1u;}else regs[R_EAX]=0u;
  regs[R_ESP]+=4u; return 1;
 }
 if(target==API_USER32_SHOWCURSOR){uint32_t sp=regs[R_ESP];regs[R_EAX]=1u;regs[R_ESP]+=4u;return 1;}
 if(target==API_USER32_SETCAPTURE){uint32_t sp=regs[R_ESP];regs[R_EAX]=rd32(sp+4u);regs[R_ESP]+=4u;return 1;}
 if(target==API_USER32_RELEASECAPTURE){regs[R_EAX]=1u;return 1;}
 if(target==API_KERNEL32_GETACP){regs[R_EAX]=1252u;return 1;}
 if(target==API_KERNEL32_GETOEMCP){regs[R_EAX]=437u;return 1;}
 if(target==API_KERNEL32_MULTIBYTETOWIDECHAR){
  uint32_t sp=regs[R_ESP],src=rd32(sp+16u),src_n=rd32(sp+20u),dst=rd32(sp+24u),dst_n=rd32(sp+28u);
  uint32_t count=0;
  if(!src){regs[R_EAX]=0;regs[R_ESP]+=24u;return 1;}
  uint32_t limit=src_n==0xFFFFFFFFu?0x10000u:src_n;
  for(uint32_t i=0;i<limit&&count<dst_n;i++){
   uint8_t ch=MEM8(src+i);
   if(!dst||!x86_mem_region_find(dst+count*2u,2u,X86_MEM_WRITE))break;
   wr8(dst+count*2u,ch);wr8(dst+count*2u+1u,0);
   count++; if(src_n==0xFFFFFFFFu&&ch==0)break;
  }
  regs[R_EAX]=count; regs[R_ESP]+=24u; return 1;
 }
 if(target==API_KERNEL32_WIDECHARTOMULTIBYTE){
  uint32_t sp=regs[R_ESP],src=rd32(sp+12u),src_n=rd32(sp+16u),dst=rd32(sp+20u),dst_n=rd32(sp+24u),used=rd32(sp+28u);
  uint32_t count=0;
  if(src&&dst){
   for(uint32_t i=0;i<src_n&&count<dst_n;i++){
    uint32_t p=src+i*2u;
    if(!x86_mem_region_find(p,2u,X86_MEM_READ)||!x86_mem_region_find(dst+count,1u,X86_MEM_WRITE))break;
    uint32_t wc=(uint32_t)MEM8(p)|((uint32_t)MEM8(p+1u)<<8);
    wr8(dst+count++,(uint8_t)(wc<=0xFFu?wc:'?'));
   }
  }
  if(used&&x86_mem_region_find(used,4u,X86_MEM_WRITE))wr32(used,count);
  regs[R_EAX]=count; regs[R_ESP]+=32u; return 1;
 }
 if(target==API_GDI32_CREATESOLIDBRUSH){
  uint32_t sp=regs[R_ESP];gdi_brush_color=rd32(sp+4u)&0x00FFFFFFu;regs[R_EAX]=0x2001u;regs[R_ESP]+=4u;return 1;
 }
 if(target==API_GDI32_DELETEOBJECT){uint32_t sp=regs[R_ESP];regs[R_EAX]=rd32(sp+4u)==0x2001u?1u:0u;regs[R_ESP]+=4u;return 1;}
 if(target==API_GDI32_SELECTOBJECT){uint32_t sp=regs[R_ESP];regs[R_EAX]=0u;regs[R_ESP]+=8u;return 1;}
 if(target==API_GDI32_FILLRECT){
  uint32_t sp=regs[R_ESP],rect=rd32(sp+8u),brush=rd32(sp+12u);
  if(rect&&x86_mem_region_find(rect,16u,X86_MEM_READ)){
   int32_t l=(int32_t)rd32(rect),t=(int32_t)rd32(rect+4u),r=(int32_t)rd32(rect+8u),b=(int32_t)rd32(rect+12u);
   uint32_t color=brush==0x2001u?gdi_brush_color:0x00FFFFFFu;
   xwasm_gfx_rect(l,t,r,b,(int32_t)color);xwasm_gfx_present();regs[R_EAX]=1u;
  } else regs[R_EAX]=0u;
  regs[R_ESP]+=12u;return 1;
 }
 if(target==API_GDI32_BITBLT){uint32_t sp=regs[R_ESP];(void)sp;xwasm_gfx_present();regs[R_EAX]=1u;regs[R_ESP]+=36u;return 1;
 }
 if(target==API_USER32_CREATEWINDOWEXA){
  /* Win32 stdcall: 12 arguments, width/height are args 6/7. */
  uint32_t sp=regs[R_ESP];
  uint32_t width=rd32(sp+28u),height=rd32(sp+32u);
  if(width<64u||width>1920u)width=640u;
  if(height<64u||height>1080u)height=360u;
  surface_width=width; surface_height=height;
  xwasm_gfx_create((int32_t)width,(int32_t)height);
  xwasm_gfx_clear(0x00101820);
  xwasm_gfx_present();
  regs[R_EAX]=1u; regs[R_ESP]+=48u; return 1;
 }
 if(target==API_USER32_SHOWWINDOW){ regs[R_EAX]=1u; regs[R_ESP]+=8u; return 1; }
 if(target==API_USER32_GETDC){ regs[R_EAX]=1u; regs[R_ESP]+=4u; return 1; }
 if(target==API_USER32_RELEASEDC){ regs[R_EAX]=1u; regs[R_ESP]+=8u; return 1; }
 if(target==API_GDI32_SETPIXEL){
  uint32_t sp=regs[R_ESP]; uint32_t hdc=rd32(sp+4u),x=rd32(sp+8u),y=rd32(sp+12u),color=rd32(sp+16u);
  if(hdc) xwasm_gfx_pixel((int32_t)x,(int32_t)y,(int32_t)color); xwasm_gfx_present(); regs[R_EAX]=color; regs[R_ESP]+=16u; return 1;
 }
 if(target==API_GDI32_RECTANGLE){
  uint32_t sp=regs[R_ESP]; uint32_t hdc=rd32(sp+4u),left=rd32(sp+8u),top=rd32(sp+12u),right=rd32(sp+16u),bottom=rd32(sp+20u);
  if(hdc) xwasm_gfx_rect((int32_t)left,(int32_t)top,(int32_t)right,(int32_t)bottom,0x00FFFFFF); xwasm_gfx_present(); regs[R_EAX]=1u; regs[R_ESP]+=20u; return 1;