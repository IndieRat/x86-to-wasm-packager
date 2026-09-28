// XWASM X86 Runtime v0.8
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
#define AF 0x00000010u
#define ZF 0x00000040u
#define SF 0x00000080u
#define OF 0x00000800u
#define DF 0x00000400u
#define X86_PREFIX_REPNZ 0x02u
#define X86_PREFIX_REP 0x04u

static uint32_t heap=HEAP_BASE_FALLBACK,image_base=0,image_size=0,entry=0,eip=0,steps=0,loaded=0;
static uint32_t requested_image_base=0,reloc_rva=0,reloc_size=0,import_rva=0,import_size=0;
static uint32_t relocation_needed=0,dll_count=0,import_count=0,load_error=0,last_load_ptr=0,last_load_size=0;
static uint32_t regs[8],eflags=0x00000002u;
static uint32_t halted=0,cpu_error=0;
static uint8_t decoded_prefixes=0,decoded_operand16=0;
static uint32_t last_decoded_map=0,last_decoded_opcode=0,last_decoded_length=0;
static uint32_t last_dispatch_id=0,last_dispatch_count=0;
#define X86_TRACE_DEPTH 32u
static uint32_t trace_eip[X86_TRACE_DEPTH],trace_next_eip[X86_TRACE_DEPTH];
static uint32_t trace_opcode[X86_TRACE_DEPTH],trace_flags[X86_TRACE_DEPTH];
static uint32_t trace_eax[X86_TRACE_DEPTH],trace_ecx[X86_TRACE_DEPTH];
static uint32_t trace_ebx[X86_TRACE_DEPTH],trace_edx[X86_TRACE_DEPTH];
static uint32_t trace_dispatch[X86_TRACE_DEPTH];
static uint32_t trace_count=0,trace_head=0,trace_failure_index=0;
static int modrm_ea(uint8_t m,uint32_t *ip,uint32_t *ea);
static void x86_trace_reset(void){trace_count=0;trace_head=0;trace_failure_index=0;}
static void x86_trace_record(uint32_t before_eip,uint32_t before_flags,uint32_t before_eax,uint32_t before_ecx,uint32_t before_edx,uint32_t before_ebx,uint32_t before_opcode,uint32_t dispatch){
 uint32_t i=trace_head%X86_TRACE_DEPTH;
 trace_eip[i]=before_eip; trace_next_eip[i]=eip; trace_opcode[i]=before_opcode;
 trace_flags[i]=before_flags; trace_eax[i]=before_eax; trace_ecx[i]=before_ecx;
 trace_edx[i]=before_edx; trace_ebx[i]=before_ebx; trace_dispatch[i]=dispatch;
 trace_head=(trace_head+1u)%X86_TRACE_DEPTH; if(trace_count<X86_TRACE_DEPTH)trace_count++;
 if(regs[R_EAX]==0xDEADC0DEu && before_eax!=0xDEADC0DEu) trace_failure_index=i+1u;
}
enum { X86_DISPATCH_NONE=0, X86_DISPATCH_INC_R32=1, X86_DISPATCH_DEC_R32=2, X86_DISPATCH_RCR=3 };

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
extern int32_t xwasm_input_poll(int32_t msg_ptr,int32_t remove);
extern void xwasm_input_quit(void);
extern void xwasm_audio_beep(int32_t frequency,int32_t duration_ms);
extern void xwasm_gfx_create(int32_t width,int32_t height);
extern void xwasm_gfx_clear(int32_t color);
extern void xwasm_gfx_pixel(int32_t x,int32_t y,int32_t color);
extern void xwasm_gfx_rect(int32_t left,int32_t top,int32_t right,int32_t bottom,int32_t color);
extern void xwasm_gfx_present(void);

static uint32_t guest_heap=GUEST_HEAP_BASE;
static uint32_t guest_vm=0x02000000u;
static uint32_t guest_vm_limit=0x06000000u;
static uint32_t last_virtual_alloc=0,last_virtual_alloc_size=0,virtual_free_count=0;
static uint32_t import_resolved=0,import_failed=0;
static uint32_t message_count=0,message_last=0,message_quit=0,mouse_clicks=0,mouse_right_clicks=0,mouse_middle_clicks=0,mouse_moves=0;
static uint32_t surface_width=640,surface_height=360;
static uint32_t last_import_dll=0,last_import_func=0,last_import_thunk=0,last_import_target=0;
static uint32_t last_failed_import_dll=0,last_failed_import_func=0;

static uint32_t rd32(uint32_t p);
static void wr32(uint32_t p,uint32_t v);

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
 }
 if(streq_ascii(dll,"KERNEL32.dll")||streq_ascii(dll,"kernel32.dll")){
  if(streq_ascii(name,"Beep"))return API_KERNEL32_BEEP;
 }
 return 0;
}
static uint32_t call_builtin(uint32_t target){
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
  uint32_t a=al4(guest_vm),end=a+size;
  if(end<a||end>guest_vm_limit){regs[R_EAX]=0;regs[R_ESP]+=16u;return 1;}
  guest_vm=end;
  last_virtual_alloc=a;
  last_virtual_alloc_size=size;
  regs[R_EAX]=a;
  regs[R_ESP]+=16u;
  return 1;
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
 }
 if(target==API_USER32_GETMESSAGEA || target==API_USER32_PEEKMESSAGEA){
  /* 32-bit MSG: hwnd, message, wParam, lParam, time, pt.x, pt.y. */
  uint32_t sp=regs[R_ESP],msg=rd32(sp+4u);
  /* PeekMessageA(MSG*, hWnd, min, max, removeMsg): removeMsg is arg 5. */
  uint32_t remove=target==API_USER32_GETMESSAGEA?1u:rd32(sp+20u);
  int32_t got=xwasm_input_poll((int32_t)msg,(int32_t)remove);
  if(got>0){
   message_count++; message_last=rd32(msg+4u);
   if(message_last==0x0012u)message_quit=1;
   regs[R_EAX]=1u;
  }else{
   regs[R_EAX]=0u;
  }
  regs[R_ESP]+=20u;
  return 1;
 }
 if(target==API_USER32_TRANSLATEMESSAGE){
  regs[R_EAX]=1u; regs[R_ESP]+=4u; return 1;
 }
 if(target==API_USER32_DISPATCHMESSAGEA){
  uint32_t sp=regs[R_ESP],msg=rd32(sp+4u),type=msg?rd32(msg+4u):0;
  if(msg){
   uint32_t lp=rd32(msg+12u);
   if(type==0x0200u) mouse_moves++;
   else if(type==0x0204u) mouse_right_clicks++;
   else if(type==0x0207u) mouse_middle_clicks++;
   if(type==0x0201u){
    int32_t x=(int16_t)(lp&0xFFFFu),y=(int16_t)((lp>>16)&0xFFFFu);
    mouse_clicks++;
    xwasm_gfx_rect(x-4,y-4,x+5,y+5,0x0000FF00);
    xwasm_gfx_pixel(x,y,0x00FFFFFF);
    xwasm_gfx_present();
    xwasm_audio_beep(880,70);
   }
  }
  regs[R_EAX]=0u; regs[R_ESP]+=4u; return 1;
 }
 if(target==API_USER32_DEFWINDOWPROCA){
  regs[R_EAX]=0u; regs[R_ESP]+=16u; return 1;
 }
 if(target==API_USER32_POSTQUITMESSAGE){
  message_quit=1; xwasm_input_quit(); regs[R_ESP]+=4u; return 1;
 }
 if(target==API_USER32_GETCLIENTRECT){
  uint32_t sp=regs[R_ESP],rect=rd32(sp+8u);
  if(rect){wr32(rect,0);wr32(rect+4u,0);wr32(rect+8u,surface_width);wr32(rect+12u,surface_height);}
  regs[R_EAX]=rect?1u:0u; regs[R_ESP]+=8u; return 1;
 }
 if(target==API_USER32_INVALIDATERECT){
  regs[R_EAX]=1u; regs[R_ESP]+=12u; xwasm_gfx_present(); return 1;
 }
 if(target==API_USER32_UPDATEWINDOW){
  regs[R_EAX]=1u; regs[R_ESP]+=4u; xwasm_gfx_present(); return 1;
 }
 if(target==API_KERNEL32_BEEP){
  uint32_t sp=regs[R_ESP],freq=rd32(sp+4u),duration=rd32(sp+8u);
  xwasm_audio_beep((int32_t)freq,(int32_t)duration);
  regs[R_EAX]=1u; regs[R_ESP]+=8u; return 1;
 }
 if(target==API_VIRTUALFREE){
  /* Win32 stdcall: lpAddress, dwSize, dwFreeType. */
  uint32_t sp=regs[R_ESP];
  uint32_t address=rd32(sp+4u),size=rd32(sp+8u),free_type=rd32(sp+12u);
  (void)size;
  (void)free_type;
  regs[R_EAX]=(address!=0)?1u:0u;
  if(address!=0)virtual_free_count++;
  regs[R_ESP]+=12u;
  return 1;
 }
 return 0;
}

static uint16_t rd16(uint32_t p){return (uint16_t)MEM8(p)|((uint16_t)MEM8(p+1)<<8);}
static uint32_t rd32(uint32_t p){return (uint32_t)MEM8(p)|((uint32_t)MEM8(p+1)<<8)|((uint32_t)MEM8(p+2)<<16)|((uint32_t)MEM8(p+3)<<24);}
static void wr32(uint32_t p,uint32_t v){MEM8(p)=(uint8_t)v;MEM8(p+1)=(uint8_t)(v>>8);MEM8(p+2)=(uint8_t)(v>>16);MEM8(p+3)=(uint8_t)(v>>24);}
static void wr16(uint32_t p,uint16_t v){MEM8(p)=(uint8_t)v;MEM8(p+1)=(uint8_t)(v>>8);}
static void wr8(uint32_t p,uint8_t v){MEM8(p)=v;}
static void copy_bytes(uint32_t d,uint32_t s,uint32_t n){for(uint32_t i=0;i<n;i++)wr8(d+i,MEM8(s+i));}
static void loglit(const char*s){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}
static void loghex(const char*s,uint32_t v){uint32_t p=heap;while(*s)wr8(p++,(uint8_t)*s++);wr8(p++,'0');wr8(p++,'x');for(int i=7;i>=0;i--){uint8_t x=(v>>(i*4))&15u;wr8(p++,(uint8_t)(x<10?'0'+x:'A'+x-10));}xwasm_log(1,(int32_t)heap,(int32_t)(p-heap));heap=al4(p+1);}

static void set_logic_flags(uint32_t v){
 uint32_t p=v; p^=p>>4; p^=p>>2; p^=p>>1;
 eflags=(eflags&~(CF|PF|AF|ZF|SF|OF))|((p&1u)==0?PF:0)|(v==0?ZF:0)|((v&0x80000000u)?SF:0);
}
static uint32_t parity_even8(uint32_t v){v&=0xFFu;v^=v>>4;v^=v>>2;v^=v>>1;return (v&1u)==0u;}
static void set_logic_flags_width(uint32_t v,uint32_t bits){uint32_t mask=bits==8?0xFFu:(bits==16?0xFFFFu:0xFFFFFFFFu),sign=1u<<(bits-1u);v&=mask;uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);if(parity_even8(v))f|=PF;if(v==0)f|=ZF;if(v&sign)f|=SF;eflags=f;}
static void set_add_flags_width(uint32_t a,uint32_t b,uint32_t r,uint32_t bits){uint32_t mask=bits==8?0xFFu:(bits==16?0xFFFFu:0xFFFFFFFFu),sign=1u<<(bits-1u);a&=mask;b&=mask;r&=mask;uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);if((uint64_t)a+(uint64_t)b>mask)f|=CF;if(((a&0xFu)+(b&0xFu))>0xFu)f|=AF;if(parity_even8(r))f|=PF;if(!r)f|=ZF;if(r&sign)f|=SF;if(((~(a^b))&(a^r)&sign)!=0)f|=OF;eflags=f;}
static void set_adc_flags_width(uint32_t a,uint32_t b,uint32_t cin,uint32_t r,uint32_t bits){uint32_t mask=bits==8?0xFFu:(bits==16?0xFFFFu:0xFFFFFFFFu),sign=1u<<(bits-1u);a&=mask;b&=mask;r&=mask;uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);if((uint64_t)a+(uint64_t)b+cin>mask)f|=CF;if(((a&0xFu)+(b&0xFu)+cin)>0xFu)f|=AF;if(parity_even8(r))f|=PF;if(!r)f|=ZF;if(r&sign)f|=SF;uint32_t bb=(b+cin)&mask;if(((~(a^bb))&(a^r)&sign)!=0)f|=OF;eflags=f;}
static void set_sbb_flags_width(uint32_t a,uint32_t b,uint32_t bin,uint32_t r,uint32_t bits){uint32_t mask=bits==8?0xFFu:(bits==16?0xFFFFu:0xFFFFFFFFu),sign=1u<<(bits-1u);a&=mask;b&=mask;r&=mask;uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);uint32_t bb=b+bin;if((uint64_t)a<(uint64_t)bb)f|=CF;if((a&0xFu)<((b&0xFu)+bin))f|=AF;if(parity_even8(r))f|=PF;if(!r)f|=ZF;if(r&sign)f|=SF;bb&=mask;if(((a^bb)&(a^r)&sign)!=0)f|=OF;eflags=f;}
static void set_add_flags(uint32_t a,uint32_t b,uint32_t r){
 uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);
 if(r<a)f|=CF;
 if(((a&0xFu)+(b&0xFu))>0xFu)f|=AF;
 if(parity_even8(r))f|=PF;
 if(r==0)f|=ZF;
 if(r&0x80000000u)f|=SF;
 if(((~(a^b))&(a^r)&0x80000000u)!=0)f|=OF;
 eflags=f;
}
static void set_sub_flags(uint32_t a,uint32_t b,uint32_t r){
 uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);
 if(a<b)f|=CF;
 if((a&0xFu)<(b&0xFu))f|=AF;
 if(parity_even8(r))f|=PF;
 if(r==0)f|=ZF;
 if(r&0x80000000u)f|=SF;
 if(((a^b)&(a^r)&0x80000000u)!=0)f|=OF;
 eflags=f;
}
static void set_adc_flags(uint32_t a,uint32_t b,uint32_t cin,uint32_t r){
 uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF),bb=b+cin;
 if(r<a || (cin && r==a))f|=CF;
 if(((a&0xFu)+(b&0xFu)+cin)>0xFu)f|=AF;
 if(parity_even8(r))f|=PF;
 if(r==0)f|=ZF;
 if(r&0x80000000u)f|=SF;
 if(((~(a^bb))&(a^r)&0x80000000u)!=0)f|=OF;
 eflags=f;
}
static void set_sbb_flags(uint32_t a,uint32_t b,uint32_t bin,uint32_t r){
 uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF),bb=b+bin;
 if(a<bb || bb<b)f|=CF;
 if((a&0xFu)<((b&0xFu)+bin))f|=AF;
 if(parity_even8(r))f|=PF;
 if(r==0)f|=ZF;
 if(r&0x80000000u)f|=SF;
 if(((a^bb)&(a^r)&0x80000000u)!=0)f|=OF;
 eflags=f;
}
static void set_sub_flags_width(uint32_t a,uint32_t b,uint32_t r,uint32_t bits){
 uint32_t mask=bits==8?0xFFu:(bits==16?0xFFFFu:0xFFFFFFFFu),sign=1u<<(bits-1u);
 a&=mask;b&=mask;r&=mask;uint32_t f=eflags&~(CF|PF|AF|ZF|SF|OF);
 if(a<b)f|=CF;if((a&0xFu)<(b&0xFu))f|=AF;if(parity_even8(r))f|=PF;if(r==0)f|=ZF;if(r&sign)f|=SF;if(((a^b)&(a^r)&sign)!=0)f|=OF;eflags=f;
}
static uint8_t reg8_read(uint32_t r){uint32_t i=r&7u;return (uint8_t)(i<4u?regs[i]:(regs[i-4u]>>8));}
static void reg8_write(uint32_t r,uint8_t v){uint32_t i=r&7u;if(i<4u)regs[i]=(regs[i]&~0xFFu)|v;else{uint32_t q=i-4u;regs[q]=(regs[q]&~0xFF00u)|((uint32_t)v<<8);}}
static uint16_t reg16_read(uint32_t r){return (uint16_t)regs[r&7u];}
static void reg16_write(uint32_t r,uint16_t v){uint32_t i=r&7u;regs[i]=(regs[i]&~0xFFFFu)|v;}
static uint8_t modrm_read8(uint8_t m,uint32_t *ip){uint32_t ea=0;if(!modrm_ea(m,ip,&ea))return reg8_read(m&7);return MEM8(ea);}
static uint16_t modrm_read16(uint8_t m,uint32_t *ip){uint32_t ea=0;if(!modrm_ea(m,ip,&ea))return reg16_read(m&7);return rd16(ea);}
static void modrm_write16(uint8_t m,uint32_t *ip,uint16_t v){uint32_t ea=0;if(!modrm_ea(m,ip,&ea)){reg16_write(m&7,v);return;}wr32(ea,(rd32(ea)&0xFFFF0000u)|v);}
static void modrm_write8(uint8_t m,uint32_t *ip,uint8_t v){uint32_t ea=0;if(!modrm_ea(m,ip,&ea)){reg8_write(m&7,v);return;}wr8(ea,v);}
static void string_step(uint8_t op){
 uint32_t width=(op==0xA4||op==0xA6||op==0xAC||op==0xAE||op==0xAA)?1u:(decoded_operand16?2u:4u),si=regs[R_ESI],di=regs[R_EDI],step=(eflags&DF)?(uint32_t)(-(int32_t)width):width;
 if(op==0xA4||op==0xA5){for(uint32_t i=0;i<width;i++)wr8(di+i,MEM8(si+i));regs[R_ESI]+=step;regs[R_EDI]+=step;}
 else if(op==0xA6||op==0xA7){uint32_t a=width==1?MEM8(si):(width==2?rd16(si):rd32(si)),b=width==1?MEM8(di):(width==2?rd16(di):rd32(di));set_sub_flags_width(a,b,a-b,width*8u);regs[R_ESI]+=step;regs[R_EDI]+=step;}
 else if(op==0xAA||op==0xAB){uint32_t v=width==1?(regs[R_EAX]&0xFFu):(width==2?(regs[R_EAX]&0xFFFFu):regs[R_EAX]);for(uint32_t i=0;i<width;i++)wr8(di+i,(uint8_t)(v>>(8u*i)));regs[R_EDI]+=step;}
 else if(op==0xAC||op==0xAD){uint32_t v=width==1?MEM8(si):(width==2?rd16(si):rd32(si));if(width==1)reg8_write(0,(uint8_t)v);else if(width==2)reg16_write(0,(uint16_t)v);else regs[R_EAX]=v;regs[R_ESI]+=step;}
 else if(op==0xAE||op==0xAF){uint32_t a=width==1?(regs[R_EAX]&0xFFu):(width==2?(regs[R_EAX]&0xFFFFu):regs[R_EAX]),b=width==1?MEM8(di):(width==2?rd16(di):rd32(di));set_sub_flags_width(a,b,a-b,width*8u);regs[R_EDI]+=step;}
}
static void string_execute(uint8_t op){uint32_t repeat=(decoded_prefixes&(X86_PREFIX_REP|X86_PREFIX_REPNZ))?1u:0u;if(!repeat){string_step(op);return;}uint32_t count=regs[R_ECX];while(count){string_step(op);count--;regs[R_ECX]=count;if((op==0xA6||op==0xA7||op==0xAE||op==0xAF)){if((decoded_prefixes&X86_PREFIX_REP)&&!(eflags&ZF))break;if((decoded_prefixes&X86_PREFIX_REPNZ)&&(eflags&ZF))break;}}}
static void set_rotate_flags(uint32_t r,uint32_t cf,uint32_t of_valid,uint32_t of){
 eflags=(eflags&~(CF|OF))|(cf?CF:0u);
 if(of_valid)eflags=(eflags&~OF)|(of?OF:0u);
}
static void set_shift_flags(uint32_t v,uint32_t cf,int of_valid,uint32_t of){
 uint32_t keep=eflags&(CF|OF);
 eflags=(eflags&~(CF|PF|ZF|SF|OF))|((v==0)?ZF:0)|((v&0x80000000u)?SF:0);
 uint32_t p=v; p^=p>>4; p^=p>>2; p^=p>>1;
 if((p&1u)==0)eflags|=PF;
 if(cf)eflags|=CF;
 if(of_valid&&of)eflags|=OF;
 else if(of_valid)eflags&=~OF;
 else eflags=(eflags&~OF)|(keep&OF);
}
static int cond(uint8_t op){
 switch(op){
  case 0x70:return (eflags&OF)!=0; /* JO */
  case 0x71:return (eflags&OF)==0; /* JNO */
  case 0x72:return (eflags&CF)!=0; /* JB/JC */
  case 0x73:return (eflags&CF)==0; /* JAE/JNC */
  case 0x74:return (eflags&ZF)!=0; /* JE/JZ */
  case 0x75:return (eflags&ZF)==0; /* JNE/JNZ */
  case 0x76:return (eflags&CF)!=0||(eflags&ZF)!=0; /* JBE */
  case 0x77:return (eflags&CF)==0&&(eflags&ZF)==0; /* JA */
  case 0x78:return (eflags&SF)!=0; /* JS */
  case 0x79:return (eflags&SF)==0; /* JNS */
  case 0x7A:return (eflags&PF)!=0; /* JP/JPE */
  case 0x7B:return (eflags&PF)==0; /* JNP/JPO */
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

static int cpu_step_legacy(void){
 uint32_t ip=eip; uint8_t op=MEM8(ip++); steps++;
 switch(op){
  case 0xFC:eflags&=~DF;eip=ip;return 0;
  case 0xFD:eflags|=DF;eip=ip;return 0;
  case 0xA4:case 0xA5:case 0xA6:case 0xA7:case 0xAA:case 0xAB:case 0xAC:case 0xAD:case 0xAE:case 0xAF:string_execute(op);eip=ip;return 0;
  case 0x88:{uint8_t m=MEM8(ip++),v=reg8_read((m>>3)&7);modrm_write8(m,&ip,v);eip=ip;return 0;}
  case 0x8A:{uint8_t m=MEM8(ip++);reg8_write((m>>3)&7,modrm_read8(m,&ip));eip=ip;return 0;}
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
  case 0x8B: { /* MOV r32/r16,r/m */
   uint8_t m=MEM8(ip++); if(decoded_operand16){reg16_write((m>>3)&7,modrm_read16(m,&ip));}else{regs[(m>>3)&7]=modrm_read32(m,&ip);} eip=ip; return 0;
  }
  case 0x89: { /* MOV r/m32/r16,r32/r16 */
   uint8_t m=MEM8(ip++); if(decoded_operand16)modrm_write16(m,&ip,reg16_read((m>>3)&7));else modrm_write32(m,&ip,regs[(m>>3)&7]); eip=ip; return 0;
  }
  case 0x8D: { /* LEA r32,m */
   uint8_t m=MEM8(ip++); uint32_t ea=0; if(!modrm_ea(m,&ip,&ea)){cpu_error=0x8D;return -11;} regs[(m>>3)&7]=ea; eip=ip; return 0;
  }
  case 0x00:case 0x02:case 0x08:case 0x0A:case 0x10:case 0x12:case 0x18:case 0x1A:case 0x20:case 0x22:case 0x28:case 0x2A:case 0x30:case 0x32:case 0x38:case 0x3A:case 0x84:{
   uint8_t m=MEM8(ip++),d=(m>>3)&7;uint8_t a,b,r;uint32_t ea=0;
   if((m>>6)==3)a=reg8_read(m&7);else{modrm_ea(m,&ip,&ea);a=MEM8(ea);}
   b=reg8_read(d);
   switch(op&0xF8u){case 0x00:r=(uint8_t)(a+b);set_add_flags_width(a,b,r,8);break;case 0x08:r=(uint8_t)(a|b);set_logic_flags_width(r,8);break;case 0x10:{uint32_t c=(eflags&CF)?1u:0u;r=(uint8_t)(a+b+c);set_adc_flags_width(a,b,c,r,8);break;}case 0x18:{uint32_t c=(eflags&CF)?1u:0u;r=(uint8_t)(a-b-c);set_sbb_flags_width(a,b,c,r,8);break;}case 0x20:r=(uint8_t)(a&b);set_logic_flags_width(r,8);break;case 0x28:r=(uint8_t)(a-b);set_sub_flags_width(a,b,r,8);break;case 0x30:r=(uint8_t)(a^b);set_logic_flags_width(r,8);break;default:set_sub_flags_width(a,b,(uint8_t)(a-b),8);eip=ip;return 0;}
   if(op==0x02||op==0x0A||op==0x12||op==0x1A||op==0x22||op==0x2A||op==0x32||op==0x3A)reg8_write(d,r);else if(op==0x84){set_logic_flags_width((uint8_t)(a&b),8);eip=ip;return 0;}else if((m>>6)==3)reg8_write(m&7,r);else wr8(ea,r);
   eip=ip;return 0;
  }
  case 0x04:case 0x0C:case 0x14:case 0x1C:case 0x24:case 0x2C:case 0x34:case 0x3C:{
   uint8_t b=MEM8(ip++),a=reg8_read(0),r;switch(op){case 0x04:r=a+b;set_add_flags_width(a,b,r,8);break;case 0x0C:r=a|b;set_logic_flags_width(r,8);break;case 0x14:{uint32_t c=(eflags&CF)?1u:0u;r=a+b+c;set_adc_flags_width(a,b,c,r,8);break;}case 0x1C:{uint32_t c=(eflags&CF)?1u:0u;r=a-b-c;set_sbb_flags_width(a,b,c,r,8);break;}case 0x24:r=a&b;set_logic_flags_width(r,8);break;case 0x2C:r=a-b;set_sub_flags_width(a,b,r,8);break;case 0x34:r=a^b;set_logic_flags_width(r,8);break;default:set_sub_flags_width(a,b,(uint8_t)(a-b),8);eip=ip;return 0;}reg8_write(0,r);eip=ip;return 0;
  }
  case 0x80:{
   uint8_t m=MEM8(ip++),sub=(m>>3)&7;uint32_t ea=0;uint8_t a=(m>>6)==3?reg8_read(m&7):(modrm_ea(m,&ip,&ea),MEM8(ea)),b=MEM8(ip++),r;
   if(sub==0){r=a+b;set_add_flags_width(a,b,r,8);}else if(sub==2){uint32_t c=(eflags&CF)?1u:0u;r=a+b+c;set_adc_flags(a,b,c,r);}else if(sub==3){uint32_t c=(eflags&CF)?1u:0u;r=a-b-c;set_sbb_flags(a,b,c,r);}else if(sub==4){r=a&b;set_logic_flags_width(r,8);}else if(sub==5){r=a-b;set_sub_flags_width(a,b,r,8);}else if(sub==6){r=a^b;set_logic_flags_width(r,8);}else if(sub==7){set_sub_flags_width(a,b,(uint8_t)(a-b),8);eip=ip;return 0;}else{cpu_error=0x8000u|sub;return -40;}if(sub!=7){if((m>>6)==3)reg8_write(m&7,r);else wr8(ea,r);}eip=ip;return 0;
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
  case 0x09: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t ea=0,v=regs[d]; if((m>>6)==3){v|=regs[m&7];regs[m&7]=v;}else{modrm_ea(m,&ip,&ea);v=rd32(ea)|v;wr32(ea,v);} set_logic_flags(v);eip=ip;return 0; } /* OR r/m32,r32 */
  case 0x0B: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t v=regs[d]|modrm_read32(m,&ip);regs[d]=v;set_logic_flags(v);eip=ip;return 0; } /* OR r32,r/m32 */
  case 0x21: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t ea=0,v=regs[d]; if((m>>6)==3){v&=regs[m&7];regs[m&7]=v;}else{modrm_ea(m,&ip,&ea);v=rd32(ea)&v;wr32(ea,v);}set_logic_flags(v);eip=ip;return 0; } /* AND r/m32,r32 */
  case 0x23: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t v=regs[d]&modrm_read32(m,&ip);regs[d]=v;set_logic_flags(v);eip=ip;return 0; } /* AND r32,r/m32 */
  case 0x2B: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t a=regs[d],b=modrm_read32(m,&ip),v=a-b;set_sub_flags(a,b,v);regs[d]=v;eip=ip;return 0; } /* SUB r32,r/m32 */
  case 0x03: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t a=regs[d],b=modrm_read32(m,&ip),v=a+b;set_add_flags(a,b,v);regs[d]=v;eip=ip;return 0; } /* ADD r32,r/m32 */
  case 0x3B: { uint8_t m=MEM8(ip++),d=(m>>3)&7; uint32_t a=regs[d],b=modrm_read32(m,&ip);set_sub_flags(a,b,a-b);eip=ip;return 0; } /* CMP r32,r/m32 */
  case 0x81: { uint8_t m=MEM8(ip++),sub=(m>>3)&7; uint32_t ea=0,a; if((m>>6)==3)a=regs[m&7];else{modrm_ea(m,&ip,&ea);a=rd32(ea);} uint32_t b=rd32(ip);ip+=4; uint32_t v;
   if(sub==0){v=a+b;set_add_flags(a,b,v);}else if(sub==2){uint32_t c=(eflags&CF)?1u:0u;v=a+b+c;set_adc_flags(a,b,c,v);}else if(sub==3){uint32_t c=(eflags&CF)?1u:0u;v=a-b-c;set_sbb_flags(a,b,c,v);}else if(sub==5){v=a-b;set_sub_flags(a,b,v);}else if(sub==7){set_sub_flags(a,b,a-b);eip=ip;return 0;}else{cpu_error=0x8100u|sub;return -13;}
   if((m>>6)==3)regs[m&7]=v;else wr32(ea,v);eip=ip;return 0; } /* ADD/SUB/CMP r/m32,imm32 */
  case 0x83: { uint8_t m=MEM8(ip++),sub=(m>>3)&7; uint32_t ea=0,a; if((m>>6)==3)a=regs[m&7];else{modrm_ea(m,&ip,&ea);a=rd32(ea);} int32_t sb=(int8_t)MEM8(ip++);uint32_t b=(uint32_t)sb,v;
   if(sub==0){v=a+b;set_add_flags(a,b,v);}else if(sub==2){uint32_t c=(eflags&CF)?1u:0u;v=a+b+c;set_adc_flags(a,b,c,v);}else if(sub==3){uint32_t c=(eflags&CF)?1u:0u;v=a-b-c;set_sbb_flags(a,b,c,v);}else if(sub==5){v=a-b;set_sub_flags(a,b,v);}else if(sub==7){set_sub_flags(a,b,a-b);eip=ip;return 0;}else{cpu_error=0x8300u|sub;return -14;}
   if((m>>6)==3)regs[m&7]=v;else wr32(ea,v);eip=ip;return 0; } /* ADD/SUB/CMP r/m32,imm8 */
  case 0x39: { /* CMP r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t ea=0,b=regs[(m>>3)&7],a;
   if((m>>6)==3)a=regs[m&7]; else {modrm_ea(m,&ip,&ea);a=rd32(ea);}
   uint32_t r=a-b; set_sub_flags(a,b,r); eip=ip; return 0;
  }
  case 0x85: { /* TEST r/m32,r32 */
   uint8_t m=MEM8(ip++); uint32_t v=modrm_read32(m,&ip)&regs[(m>>3)&7]; set_logic_flags(v); eip=ip; return 0;
  }
  case 0x11: {uint8_t m=MEM8(ip++);uint32_t ea=0,a,b=regs[(m>>3)&7],cin=(eflags&CF)?1u:0u;if((m>>6)==3)a=regs[m&7];else{modrm_ea(m,&ip,&ea);a=rd32(ea);}uint32_t r=a+b+cin;set_adc_flags(a,b,cin,r);if((m>>6)==3)regs[m&7]=r;else wr32(ea,r);eip=ip;return 0;}
  case 0x13: {uint8_t m=MEM8(ip++),d=(m>>3)&7,cin=(eflags&CF)?1u:0u,a=regs[d],b=modrm_read32(m,&ip),r=a+b+cin;set_adc_flags(a,b,cin,r);regs[d]=r;eip=ip;return 0;}
  case 0x15: {uint32_t b=rd32(ip),cin=(eflags&CF)?1u:0u,a=regs[R_EAX],r=a+b+cin;set_adc_flags(a,b,cin,r);regs[R_EAX]=r;eip=ip+4;return 0;}
  case 0x19: {uint8_t m=MEM8(ip++);uint32_t ea=0,a,b=regs[(m>>3)&7],bin=(eflags&CF)?1u:0u;if((m>>6)==3)a=regs[m&7];else{modrm_ea(m,&ip,&ea);a=rd32(ea);}uint32_t r=a-b-bin;set_sbb_flags(a,b,bin,r);if((m>>6)==3)regs[m&7]=r;else wr32(ea,r);eip=ip;return 0;}
  case 0x1B: {uint8_t m=MEM8(ip++),d=(m>>3)&7,bin=(eflags&CF)?1u:0u,a=regs[d],b=modrm_read32(m,&ip),r=a-b-bin;set_sbb_flags(a,b,bin,r);regs[d]=r;eip=ip;return 0;}
  case 0x1D: {uint32_t b=rd32(ip),bin=(eflags&CF)?1u:0u,a=regs[R_EAX],r=a-b-bin;set_sbb_flags(a,b,bin,r);regs[R_EAX]=r;eip=ip+4;return 0;}
  case 0x05: {uint32_t b=rd32(ip);uint32_t r=regs[R_EAX]+b;set_add_flags(regs[R_EAX],b,r);regs[R_EAX]=r;eip=ip+4;return 0;}
  case 0x2D: {uint32_t b=rd32(ip);uint32_t r=regs[R_EAX]-b;set_sub_flags(regs[R_EAX],b,r);regs[R_EAX]=r;eip=ip+4;return 0;}
  case 0x3D: {uint32_t b=rd32(ip);uint32_t r=regs[R_EAX]-b;set_sub_flags(regs[R_EAX],b,r);eip=ip+4;return 0;} /* CMP EAX,imm32 */
  case 0xC0: case 0xC1: case 0xD0: case 0xD1: case 0xD2: case 0xD3: {
   /* Group 2: 8/16/32-bit shifts and rotates. */
   uint8_t m=MEM8(ip++),sub=(m>>3)&7;
   uint32_t bits=(op==0xC0||op==0xD0||op==0xD2)?8u:(decoded_operand16?16u:32u);
   uint32_t mask=bits==8?0xFFu:(bits==16?0xFFFFu:0xFFFFFFFFu);
   uint32_t sign=1u<<(bits-1u);
   uint32_t ea=0,v;
   if((m>>6)==3) v=bits==8?reg8_read(m&7):bits==16?reg16_read(m&7):regs[m&7];
   else {modrm_ea(m,&ip,&ea);v=bits==8?MEM8(ea):bits==16?rd16(ea):rd32(ea);}
   v&=mask;
   uint32_t count=(op==0xC0||op==0xC1)?MEM8(ip++):((op==0xD2||op==0xD3)?(regs[R_ECX]&31u):1u);
   uint32_t cf=(eflags&CF)?1u:0u,of=0,of_valid=0,r=v;
   if(sub>=4){
    count&=31u;if(!count){eip=ip;return 0;}
    if(sub==4){r=(v<<count)&mask;cf=(v>>(bits-count))&1u;of_valid=count==1;of=((r&sign)?1u:0u)^cf;}
    else if(sub==5){r=v>>count;cf=(v>>(count-1u))&1u;of_valid=count==1;of=(v&sign)?1u:0u;}
    else if(sub==7){r=(uint32_t)(((int32_t)(v|((v&sign)?~mask:0u)))>>count)&mask;cf=(v>>(count-1u))&1u;of_valid=0;}
    else {cpu_error=0xC000u|sub;return -35;}
    set_shift_flags(r,cf,of_valid,of);
   }else{
    uint32_t modulus=bits==8?9u:(bits==16?17u:33u);
    count&=31u;count%=modulus;if(!count){eip=ip;return 0;}
    uint64_t x=((uint64_t)cf<<bits)|v;
    uint64_t fullmask=(1ull<<(bits+1u))-1ull;
    if(sub==0){
     r=(uint32_t)(((uint64_t)v<<count)|(v>>(bits-count)))&mask;
     cf=r&1u;of_valid=count==1;of=((r&sign)?1u:0u)^cf;
    }else if(sub==1){
     r=(v>>count)|(v<<(bits-count));r&=mask;
     cf=(r&sign)?1u:0u;of_valid=count==1;of=((r&sign)?1u:0u)^((r>>(bits-2u))&1u);
    }else if(sub==2){
     x=((x<<count)|(x>>(bits+1u-count)))&fullmask;r=(uint32_t)x&mask;cf=(uint32_t)((x>>bits)&1u);
     of_valid=count==1;of=((r&sign)?1u:0u)^cf;
    }else{
     x=((x>>count)|(x<<(bits+1u-count)))&fullmask;r=(uint32_t)x&mask;cf=(uint32_t)((x>>bits)&1u);
     of_valid=count==1;of=((r&sign)?1u:0u)^((r>>(bits-2u))&1u);
    }
    set_rotate_flags(r,cf,of_valid,of);
   }
   if((m>>6)==3){
    if(bits==8)reg8_write(m&7,(uint8_t)r);
    else if(bits==16)reg16_write(m&7,(uint16_t)r);
    else regs[m&7]=r;
   }else{
    if(bits==8)wr8(ea,(uint8_t)r);
    else if(bits==16)modrm_write16(m,&(uint32_t){ip},(uint16_t)r);
    else wr32(ea,r);
   }
   eip=ip;return 0;
  }
  case 0x69: {uint8_t m=MEM8(ip++);uint32_t a=modrm_read32(m,&ip),imm=rd32(ip);ip+=4;int64_t p=(int64_t)(int32_t)a*(int64_t)(int32_t)imm;uint32_t r=(uint32_t)p;uint32_t sx=(uint32_t)(int32_t)r;eflags=(eflags&~(CF|OF))|((p!=(int64_t)(int32_t)r)?(CF|OF):0);regs[(m>>3)&7]=r;eip=ip;return 0;}
  case 0x6B: {uint8_t m=MEM8(ip++);uint32_t a=modrm_read32(m,&ip);int32_t imm=(int8_t)MEM8(ip++);int64_t p=(int64_t)(int32_t)a*(int64_t)imm;uint32_t r=(uint32_t)p;eflags=(eflags&~(CF|OF))|((p!=(int64_t)(int32_t)r)?(CF|OF):0);regs[(m>>3)&7]=r;eip=ip;return 0;}
  case 0xF7: { /* NOT/NEG/MUL/IMUL/DIV/IDIV r/m32 */
   uint8_t m=MEM8(ip++),sub=(m>>3)&7; uint32_t ea=0,v=(m>>6)==3?regs[m&7]:(modrm_ea(m,&ip,&ea),rd32(ea));
   if(sub==2){v=~v;if((m>>6)==3)regs[m&7]=v;else wr32(ea,v);eip=ip;return 0;}
   if(sub==3){uint32_t r=0u-v;set_sub_flags(0u,v,r);if(v)eflags|=CF;else eflags&=~CF;if(v==0x80000000u)eflags|=OF;else eflags&=~OF;if((m>>6)==3)regs[m&7]=r;else wr32(ea,r);eip=ip;return 0;}
   if(sub==4){uint64_t p=(uint64_t)regs[R_EAX]*(uint64_t)v;regs[R_EAX]=(uint32_t)p;regs[R_EDX]=(uint32_t)(p>>32);eflags=(eflags&~(CF|OF))|(((p>>32)!=0)?(CF|OF):0);eip=ip;return 0;}
   if(sub==5){int64_t p=(int64_t)(int32_t)regs[R_EAX]*(int64_t)(int32_t)v;uint32_t lo=(uint32_t)p,hi=(uint32_t)((uint64_t)p>>32);regs[R_EAX]=lo;regs[R_EDX]=hi;int64_t sx=(int64_t)(int32_t)lo;eflags=(eflags&~(CF|OF))|((p!=sx)?(CF|OF):0);eip=ip;return 0;}
   if(sub==6){if(v==0){cpu_error=0xF706u;return -30;}uint64_t dividend=((uint64_t)regs[R_EDX]<<32)|regs[R_EAX];uint64_t q=dividend/v,r=dividend%v;if(q>0xFFFFFFFFull){cpu_error=0xF707u;return -31;}regs[R_EAX]=(uint32_t)q;regs[R_EDX]=(uint32_t)r;eip=ip;return 0;}
   if(sub==7){if(v==0){cpu_error=0xF708u;return -32;}int32_t divisor=(int32_t)v;int64_t dividend=((int64_t)(int32_t)regs[R_EDX]<<32)|(uint32_t)regs[R_EAX];if(dividend==(-9223372036854775807ll-1ll)&&divisor==-1){cpu_error=0xF709u;return -33;}int64_t q=dividend/divisor,r=dividend%divisor;if(q>2147483647ll||q<(-2147483647ll-1ll)){cpu_error=0xF709u;return -33;}regs[R_EAX]=(uint32_t)q;regs[R_EDX]=(uint32_t)r;eip=ip;return 0;}
   cpu_error=0xF700u|sub;return -34;
  }
  case 0x40:case 0x41:case 0x42:case 0x43:case 0x44:case 0x45:case 0x46:case 0x47:
   {uint32_t r=regs[op-0x40]+1;regs[op-0x40]=r; /* INC does not modify CF */
    uint32_t old=eflags;set_add_flags(regs[op-0x40]-1,1,r);eflags=(eflags&~CF)|(old&CF);eip=ip;return 0;}
  case 0x48:case 0x49:case 0x4A:case 0x4B:case 0x4C:case 0x4D:case 0x4E:case 0x4F:
   {uint32_t r=regs[op-0x48]-1;uint32_t old=eflags;set_sub_flags(regs[op-0x48]+1,1,r);eflags=(eflags&~CF)|(old&CF);regs[op-0x48]=r;eip=ip;return 0;}
  case 0xE9:{int32_t d=(int32_t)rd32(ip);eip=ip+4+(uint32_t)d;return 0;} /* JMP rel32 */
  case 0xEB:{int8_t d=(int8_t)MEM8(ip);eip=ip+1+(int32_t)d;return 0;} /* JMP rel8 */
  case 0x70:case 0x71:case 0x72:case 0x73:case 0x74:case 0x75:case 0x76:case 0x77:case 0x78:case 0x79:case 0x7A:case 0x7B:case 0x7C:case 0x7D:case 0x7E:case 0x7F:{
   int8_t d=(int8_t)MEM8(ip++);eip=cond(op)?ip+(int32_t)d:ip;return 0;
  }
  case 0x68:{uint32_t v=rd32(ip);ip+=4;regs[R_ESP]-=4;wr32(regs[R_ESP],v);eip=ip;return 0;} /* PUSH imm32 */
  case 0x6A:{int8_t v=(int8_t)MEM8(ip++);regs[R_ESP]-=4;wr32(regs[R_ESP],(uint32_t)(int32_t)v);eip=ip;return 0;} /* PUSH imm8 */
  case 0x58:case 0x59:case 0x5A:case 0x5B:case 0x5C:case 0x5D:case 0x5E:case 0x5F:
   regs[op-0x58]=rd32(regs[R_ESP]);regs[R_ESP]+=4;eip=ip;return 0;
  case 0x50:case 0x51:case 0x52:case 0x53:case 0x54:case 0x55:case 0x56:case 0x57:
   regs[R_ESP]-=4;wr32(regs[R_ESP],regs[op-0x50]);eip=ip;return 0;
  case 0x0F: {
   uint8_t op2=MEM8(ip++);
   if(op2==0xAF){uint8_t m=MEM8(ip++);int64_t p=(int64_t)(int32_t)regs[(m>>3)&7]*(int64_t)(int32_t)modrm_read32(m,&ip);uint32_t r=(uint32_t)p;regs[(m>>3)&7]=r;eflags=(eflags&~(CF|OF))|((p!=(int64_t)(int32_t)r)?(CF|OF):0);eip=ip;return 0;}
   if(op2==0xB6||op2==0xBE){uint8_t m=MEM8(ip++);uint32_t v;if((m>>6)==3){v=regs[m&7]&0xFFu;}else{uint32_t ea=0;if(!modrm_ea(m,&ip,&ea)){cpu_error=0x0F00u|op2;return -17;}v=MEM8(ea);}if(op2==0xBE&&v&0x80u)v|=0xFFFFFF00u;regs[(m>>3)&7]=v;eip=ip;return 0;}
   if(op2==0xA3||op2==0xAB||op2==0xB3||op2==0xBB){uint8_t m=MEM8(ip++),d=(m>>3)&7;int32_t bit=(int32_t)regs[d];uint32_t ea=0,shift=(uint32_t)bit&31u,v;if((m>>6)==3)v=regs[m&7];else{modrm_ea(m,&ip,&ea);ea+=(uint32_t)(bit>>5)*4u;v=rd32(ea);}uint32_t old=(v>>shift)&1u;eflags=(eflags&~CF)|(old?CF:0);if(op2!=0xA3){if(op2==0xAB)v|=1u<<shift;else if(op2==0xB3)v&=~(1u<<shift);else v^=1u<<shift;if((m>>6)==3)regs[m&7]=v;else wr32(ea,v);}eip=ip;return 0;}
   if(op2==0xBA){uint8_t m=MEM8(ip++),sub=(m>>3)&7,bit=MEM8(ip++);if(sub<4||sub>7){cpu_error=0x0FBAu|sub;return -36;}uint32_t ea=0,v,shift=bit&31u;if((m>>6)==3)v=regs[m&7];else{modrm_ea(m,&ip,&ea);v=rd32(ea);}uint32_t old=(v>>shift)&1u;eflags=(eflags&~CF)|(old?CF:0);if(sub!=4){if(sub==5)v|=1u<<shift;else if(sub==6)v&=~(1u<<shift);else v^=1u<<shift;if((m>>6)==3)regs[m&7]=v;else wr32(ea,v);}eip=ip;return 0;}
   if(op2>=0x80&&op2<=0x8F){int32_t d=(int32_t)rd32(ip);ip+=4;uint8_t shortop=(uint8_t)(0x70u+(op2-0x80u));eip=cond(shortop)?ip+(uint32_t)d:ip;return 0;}
   cpu_error=0x0F00u|op2;return -18;
  }
  case 0xE3:{int8_t d=(int8_t)MEM8(ip++);eip=(regs[R_ECX]==0)?ip+(int32_t)d:ip;return 0;} /* JECXZ */
  case 0xE0:case 0xE1:case 0xE2:{int8_t d=(int8_t)MEM8(ip++);regs[R_ECX]--;uint32_t take=(regs[R_ECX]!=0);if(op==0xE1)take=take&&((eflags&ZF)!=0);if(op==0xE0)take=take&&((eflags&ZF)==0);eip=take?ip+(int32_t)d:ip;return 0;}
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

#include "cpu_decoder.c"

static int image_rva_valid(uint32_t rva,uint32_t size){
 return rva<=image_size && size<=image_size-rva;
}
static void scan_imports(void){
 dll_count=0; import_count=0; import_resolved=0; import_failed=0; last_import_dll=0; last_import_func=0; last_import_thunk=0; last_import_target=0; last_failed_import_dll=0; last_failed_import_func=0;
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
    last_import_target=target;
    resolved_this_dll++;
   }else{
    import_failed++;
    last_failed_import_dll=name_rva;
    last_failed_import_func=v;
    uint32_t dl=0,fn=0;
    while(dl<255u&&MEM8(image_base+name_rva+dl))dl++;
    while(fn<255u&&MEM8(image_base+v+2u+fn))fn++;
    xwasm_log(2,(int32_t)(image_base+name_rva),(int32_t)dl);
    xwasm_log(2,(int32_t)(image_base+v+2u),(int32_t)fn);
   }
  }
  (void)resolved_this_dll;
 }
}


static int load_pe(uint32_t f,uint32_t sz){
 load_error=0;loaded=0;last_load_ptr=f;last_load_size=sz;
 requested_image_base=0;reloc_rva=reloc_size=import_rva=import_size=0;relocation_needed=0;dll_count=import_count=0;import_resolved=import_failed=0;last_import_dll=last_import_func=last_import_thunk=last_import_target=0;last_failed_import_dll=last_failed_import_func=0;mouse_clicks=0;mouse_right_clicks=0;mouse_middle_clicks=0;mouse_moves=0;surface_width=640;surface_height=360;
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
 loaded=1;eip=image_base+entry;regs[R_ESP]=0x03F00000u;guest_heap=GUEST_HEAP_BASE;halted=0;cpu_error=0;steps=0;eflags=0x2;decoded_prefixes=0;decoded_operand16=0;last_decoded_map=0;last_decoded_opcode=0;last_decoded_length=0;last_dispatch_id=0;last_dispatch_count=0;x86_trace_reset();
 loghex("X86 requested image base=",requested_image_base);
 loghex("X86 mapped image base=",image_base);
 loghex("X86 entry=",eip);
 return 0;
}

__attribute__((export_name("xwasm_init"))) int xwasm_init(void){
 heap=al4((uint32_t)(uintptr_t)__heap_base);guest_heap=GUEST_HEAP_BASE;guest_vm=0x02000000u;last_virtual_alloc=0;last_virtual_alloc_size=0;virtual_free_count=0;loaded=0;requested_image_base=0;reloc_rva=reloc_size=import_rva=import_size=0;relocation_needed=0;dll_count=0;import_count=0;steps=0;load_error=0;halted=0;cpu_error=0;eflags=0x2;surface_width=640;surface_height=360;
 for(int i=0;i<8;i++)regs[i]=0; decoded_prefixes=0;decoded_operand16=0; last_decoded_map=0;last_decoded_opcode=0;last_decoded_length=0;last_dispatch_id=0;last_dispatch_count=0;x86_trace_reset(); message_count=0;message_last=0;message_quit=0;mouse_clicks=0;mouse_right_clicks=0;mouse_middle_clicks=0;mouse_moves=0;
loglit("XWASM X86 Runtime v0.8");
loglit("PE32 + imports + memory + USER32/GDI32 + browser window/message/input + audio bridge");return 0;
}
__attribute__((export_name("x86_get_runtime_version"))) uint32_t x86_get_runtime_version(void){return 0x00080000u;}
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
__attribute__((export_name("x86_get_last_decoded_map"))) uint32_t x86_get_last_decoded_map(void){return last_decoded_map;}
__attribute__((export_name("x86_get_last_decoded_opcode"))) uint32_t x86_get_last_decoded_opcode(void){return last_decoded_opcode;}
__attribute__((export_name("x86_get_last_decoded_length"))) uint32_t x86_get_last_decoded_length(void){return last_decoded_length;}
__attribute__((export_name("x86_get_last_dispatch_id"))) uint32_t x86_get_last_dispatch_id(void){return last_dispatch_id;}
__attribute__((export_name("x86_get_last_dispatch_count"))) uint32_t x86_get_last_dispatch_count(void){return last_dispatch_count;}

/* Independent architectural RCR oracle used by the test shell.  This is
 * deliberately separate from guest state so a failed game fixture cannot
 * mask a rotate-through-carry regression. */
__attribute__((export_name("x86_rcr32_self_test")))
uint32_t x86_rcr32_self_test(void){
 uint32_t failures=0;
 const uint32_t values[4]={0x80000000u,0x80000000u,0x00000001u,0xFFFFFFFFu};
 const uint32_t carries[4]={0u,1u,1u,0u};
 const uint32_t counts[4]={1u,1u,1u,31u};
 const uint32_t expected[4]={0x40000000u,0xC0000000u,0x80000000u,0xFFFFFFFDu};
 const uint32_t expected_cf[4]={0u,0u,1u,1u};
 for(uint32_t i=0;i<4u;i++){
  uint32_t count=counts[i]&31u;
  uint64_t x=((uint64_t)carries[i]<<32)|values[i];
  x=((x>>count)|(x<<(33u-count)))&0x1FFFFFFFFull;
  if((uint32_t)x!=expected[i] || (uint32_t)((x>>32)&1u)!=expected_cf[i]) failures|=(1u<<i);
 }
 return failures;
}
__attribute__((export_name("x86_get_trace_count"))) uint32_t x86_get_trace_count(void){return trace_count;}
__attribute__((export_name("x86_get_trace_index"))) uint32_t x86_get_trace_index(uint32_t n){if(n>=trace_count)return 0xFFFFFFFFu;return (trace_head+X86_TRACE_DEPTH-trace_count+n)%X86_TRACE_DEPTH;}
__attribute__((export_name("x86_get_trace_eip"))) uint32_t x86_get_trace_eip(uint32_t i){return i<X86_TRACE_DEPTH?trace_eip[i]:0;}
__attribute__((export_name("x86_get_trace_next_eip"))) uint32_t x86_get_trace_next_eip(uint32_t i){return i<X86_TRACE_DEPTH?trace_next_eip[i]:0;}
__attribute__((export_name("x86_get_trace_opcode"))) uint32_t x86_get_trace_opcode(uint32_t i){return i<X86_TRACE_DEPTH?trace_opcode[i]:0;}
__attribute__((export_name("x86_get_trace_flags"))) uint32_t x86_get_trace_flags(uint32_t i){return i<X86_TRACE_DEPTH?trace_flags[i]:0;}
__attribute__((export_name("x86_get_trace_eax"))) uint32_t x86_get_trace_eax(uint32_t i){return i<X86_TRACE_DEPTH?trace_eax[i]:0;}
__attribute__((export_name("x86_get_trace_ecx"))) uint32_t x86_get_trace_ecx(uint32_t i){return i<X86_TRACE_DEPTH?trace_ecx[i]:0;}
__attribute__((export_name("x86_get_trace_edx"))) uint32_t x86_get_trace_edx(uint32_t i){return i<X86_TRACE_DEPTH?trace_edx[i]:0;}
__attribute__((export_name("x86_get_trace_ebx"))) uint32_t x86_get_trace_ebx(uint32_t i){return i<X86_TRACE_DEPTH?trace_ebx[i]:0;}
__attribute__((export_name("x86_get_trace_dispatch"))) uint32_t x86_get_trace_dispatch(uint32_t i){return i<X86_TRACE_DEPTH?trace_dispatch[i]:0;}
__attribute__((export_name("x86_get_trace_failure_index"))) uint32_t x86_get_trace_failure_index(void){return trace_failure_index;}
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
__attribute__((export_name("x86_get_last_import_target"))) uint32_t x86_get_last_import_target(void){return last_import_target;}
__attribute__((export_name("x86_get_last_failed_import_dll_rva"))) uint32_t x86_get_last_failed_import_dll_rva(void){return last_failed_import_dll;}
__attribute__((export_name("x86_get_last_failed_import_func_rva"))) uint32_t x86_get_last_failed_import_func_rva(void){return last_failed_import_func;}
__attribute__((export_name("x86_alloc"))) uint32_t x86_alloc(uint32_t n){return guest_alloc_raw(n);}
__attribute__((export_name("x86_get_guest_heap"))) uint32_t x86_get_guest_heap(void){return guest_heap;}
__attribute__((export_name("x86_virtual_alloc"))) uint32_t x86_virtual_alloc(uint32_t size){uint32_t a=al4(guest_vm),end=a+al4(size);if(!size||end<a||end>guest_vm_limit)return 0;guest_vm=end;return a;}
__attribute__((export_name("x86_get_virtual_heap"))) uint32_t x86_get_virtual_heap(void){return guest_vm;}
__attribute__((export_name("x86_get_last_virtual_alloc"))) uint32_t x86_get_last_virtual_alloc(void){return last_virtual_alloc;}
__attribute__((export_name("x86_get_last_virtual_alloc_size"))) uint32_t x86_get_last_virtual_alloc_size(void){return last_virtual_alloc_size;}
__attribute__((export_name("x86_get_virtual_free_count"))) uint32_t x86_get_virtual_free_count(void){return virtual_free_count;}
__attribute__((export_name("x86_get_loaded"))) uint32_t x86_get_loaded(void){return loaded;}
__attribute__((export_name("x86_get_load_error"))) uint32_t x86_get_load_error(void){return load_error;}
__attribute__((export_name("x86_get_load_ptr"))) uint32_t x86_get_load_ptr(void){return last_load_ptr;}
__attribute__((export_name("x86_get_load_size"))) uint32_t x86_get_load_size(void){return last_load_size;}
__attribute__((export_name("x86_get_message_count"))) uint32_t x86_get_message_count(void){return message_count;}
__attribute__((export_name("x86_get_last_message"))) uint32_t x86_get_last_message(void){return message_last;}
__attribute__((export_name("x86_get_message_quit"))) uint32_t x86_get_message_quit(void){return message_quit;}
__attribute__((export_name("x86_get_mouse_clicks"))) uint32_t x86_get_mouse_clicks(void){return mouse_clicks;}
__attribute__((export_name("x86_get_mouse_right_clicks"))) uint32_t x86_get_mouse_right_clicks(void){return mouse_right_clicks;}
__attribute__((export_name("x86_get_mouse_middle_clicks"))) uint32_t x86_get_mouse_middle_clicks(void){return mouse_middle_clicks;}
__attribute__((export_name("x86_get_mouse_moves"))) uint32_t x86_get_mouse_moves(void){return mouse_moves;}
__attribute__((export_name("x86_get_surface_width"))) uint32_t x86_get_surface_width(void){return surface_width;}
__attribute__((export_name("x86_get_surface_height"))) uint32_t x86_get_surface_height(void){return surface_height;}
__attribute__((export_name("x86_get_rich_ops_pass"))) uint32_t x86_get_rich_ops_pass(void){return regs[R_EBP]==0x584F5053u?1u:0u;}
__attribute__((export_name("x86_get_running"))) uint32_t x86_get_running(void){return loaded&&!halted&&!cpu_error;}
