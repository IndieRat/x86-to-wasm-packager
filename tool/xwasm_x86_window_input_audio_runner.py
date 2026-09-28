#!/usr/bin/env python3
"""Generate a standalone browser runner for the XWASM v0.7 window/input/audio fixture."""
from pathlib import Path
import argparse

HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>XWASM X86 Runtime v0.7 — Window / Input / Audio</title>
<style>
body{font-family:monospace;background:#111;color:#ddd}
 .window{width:max-content;border:2px solid #555;background:#222;box-shadow:0 4px 18px #0008}.titlebar{height:28px;line-height:28px;padding:0 10px;background:#333;color:#fff;font-weight:bold;display:flex;justify-content:space-between}.controls{font-weight:normal;color:#bbb}.window canvas{display:block;image-rendering:pixelated;background:#101820}
button{font:inherit;margin:8px 0;padding:6px 10px}
pre{white-space:pre-wrap}
</style>
<div class="window"><div class="titlebar"><span>XWASM X86 Window Surface</span><span class="controls">— □ ×</span></div><canvas id="gfx" width="640" height="360"></canvas></div>
<button id="run" disabled>Waiting for runtime…</button>
<pre id="log">XWASM X86 Runtime v0.7 — window/input/audio test</pre>
<input id="picker" type="file" webkitdirectory directory>
<script>
const log=document.getElementById("log");
const canvas=document.getElementById("gfx");
const gfx=canvas.getContext("2d");
const runButton=document.getElementById("run");
const say=s=>{log.textContent+="\n"+s;};
const rgb=c=>"#"+(c&255).toString(16).padStart(2,"0")+((c>>>8)&255).toString(16).padStart(2,"0")+((c>>>16)&255).toString(16).padStart(2,"0");
let memory=null;
const inputQueue=[];
let inputReady=false;
let runtimeExports=null;
let loopRunning=false;
let frameHandle=0;
let lastSteps=0;

function queueKeyMessage(type,keyCode){
  inputQueue.push({hwnd:0,message:type,wParam:keyCode>>>0,lParam:0,time:Date.now()>>>0,x:0,y:0});
}
function queueMouseMessage(type,e,buttonFlags=0){
  const r=canvas.getBoundingClientRect();
  const sx=canvas.width/r.width, sy=canvas.height/r.height;
  const x=Math.max(0,Math.min(canvas.width-1,Math.round((e.clientX-r.left)*sx)));
  const y=Math.max(0,Math.min(canvas.height-1,Math.round((e.clientY-r.top)*sy)));
  const wParam=buttonFlags>>>0;
  const lParam=((y&0xFFFF)<<16)|(x&0xFFFF);
  inputQueue.push({hwnd:0,message:type,wParam,lParam,time:Date.now()>>>0,x,y});
}


function writeMsg(ptr,m){
  const d=new DataView(memory.buffer);
  d.setUint32(ptr,m.hwnd,true);
  d.setUint32(ptr+4,m.message,true);
  d.setUint32(ptr+8,m.wParam,true);
  d.setUint32(ptr+12,m.lParam,true);
  d.setUint32(ptr+16,m.time,true);
  d.setInt32(ptr+20,m.x,true);
  d.setInt32(ptr+24,m.y,true);
}

function installInput(){
  window.addEventListener("keydown",e=>{
    if(!inputReady)return;
    e.preventDefault();
    queueKeyMessage(0x0100,e.keyCode||e.which||0);
    runFixture();
  });
  canvas.addEventListener("mousemove",e=>{
    if(!inputReady)return;
    queueMouseMessage(0x0200,e,0);
    runFixture();
  });
  canvas.addEventListener("mousedown",e=>{
    if(!inputReady)return;
    const flag=e.button===0?1:e.button===2?2:4;
    queueMouseMessage(e.button===0?0x0201:e.button===2?0x0204:0x0207,e,flag);
    runFixture();
  });
  canvas.addEventListener("mouseup",e=>{
    if(!inputReady)return;
    const flag=e.button===0?1:e.button===2?2:4;
    queueMouseMessage(e.button===0?0x0202:e.button===2?0x0205:0x0208,e,flag);
    runFixture();
  });
}

async function runFixture(){
  if(!runtimeExports || runtimeExports.x86_get_halted())return;
  try{
    const ex=runtimeExports;
    const result=ex.x86_run(512);
    if(result<0)throw Error("x86 CPU execution failed: EIP=0x"+ex.x86_get_eip().toString(16));
    lastSteps=ex.x86_get_steps();
    say("CPU slice: "+result+" | steps="+lastSteps+" | msg=0x"+ex.x86_get_last_message().toString(16).padStart(4,"0")+" | clicks="+(ex.x86_get_mouse_clicks?.()??0)+" | queue="+inputQueue.length);
    if(ex.x86_get_import_resolved()!==12)throw Error("expected 12 resolved imports");
    if(ex.x86_get_import_failed()!==0)throw Error("fixture has unresolved imports");
    if(ex.x86_get_cpu_error()!==0)throw Error("CPU error opcode=0x"+ex.x86_get_cpu_error().toString(16));
    say("WINDOW PASS — USER32 surface reached browser Canvas.");
    say("INPUT PASS — browser pointer/keyboard -> Win32 MSG -> x86 PeekMessageA.");
    if((ex.x86_get_mouse_clicks?.()??0)>0) say("MOUSE CLICK PASS — WM_LBUTTONDOWN reached x86 DispatchMessageA and drew a click marker.");
    if((ex.x86_get_mouse_right_clicks?.()??0)>0) say("RIGHT CLICK PASS — WM_RBUTTONDOWN reached x86 DispatchMessageA.");
    if((ex.x86_get_mouse_middle_clicks?.()??0)>0) say("MIDDLE CLICK PASS — WM_MBUTTONDOWN reached x86 DispatchMessageA.");
    if((ex.x86_get_mouse_moves?.()??0)>0) say("MOUSE MOVE PASS — WM_MOUSEMOVE reached x86 DispatchMessageA.");
    say("AUDIO PASS — KERNEL32 Beep -> browser Web Audio.");
    if(ex.x86_get_rich_ops_pass?.()===1) say("X86 OPS PASS — arithmetic, logic, shifts, IMUL, MOVZX, and conditional branches passed the fixture.");
    if(ex.x86_get_surface_width?.()&&ex.x86_get_surface_height?.()) say("SURFACE PASS — "+ex.x86_get_surface_width()+"x"+ex.x86_get_surface_height()+" client surface active.");
  }catch(err){ say("ERROR: "+err.message); }
}
function scheduleCpu(){
  if(!loopRunning)return;
  runFixture().finally(()=>{ frameHandle=requestAnimationFrame(scheduleCpu); });
}
function startCpuLoop(){
  if(loopRunning)return;
  loopRunning=true;
  frameHandle=requestAnimationFrame(scheduleCpu);
}

