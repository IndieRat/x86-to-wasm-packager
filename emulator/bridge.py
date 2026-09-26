"""
x86 Emulator Bridge Module

Provides a lightweight interface for a WASM-based or JavaScript-based x86 emulator
to consume packaged PE binaries and execute them in a browser environment.

This module:
- Defines the emulator contract (API surface)
- Provides memory initialization from PE sections
- Exposes hooks for syscall/API shims
- Implements a basic register and instruction fetch model
"""

import json
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class X86Register:
    """Represents an x86 32-bit register state."""
    eax: int = 0
    ebx: int = 0
    ecx: int = 0
    edx: int = 0
    esi: int = 0
    edi: int = 0
    ebp: int = 0
    esp: int = 0
    eip: int = 0


@dataclass
class MemoryRegion:
    """Represents a mapped memory region."""
    address: int
    size: int
    permissions: str  # "r", "w", "rw", "rwx"
    data: Optional[bytes] = None


class X86EmulatorBridge:
    """
    Interface and utility class for x86 emulation in browser environments.
    
    This bridge prepares PE payloads for consumption by a WASM or JS emulator.
    It does NOT implement the emulator itself — instead, it provides:
    
    1. Memory layout information
    2. Section mappings
    3. Entry point and symbol information
    4. API hooks for common Windows syscalls
    
    A real emulator (written in Rust/WASM or pure JS) will consume these
    and actually execute the x86 instructions.
    """
    
    def __init__(self, manifest: Dict, binary_data: bytes):
        """
        Initialize the bridge with a packaged PE binary.
        
        Args:
            manifest: The manifest.json from the package (contains metadata)
            binary_data: The raw PE binary payload
        """
        self.manifest = manifest
        self.binary_data = binary_data
        self.registers = X86Register()
        self.memory_map: Dict[int, MemoryRegion] = {}
        self._initialized = False
    
    def initialize_memory(self) -> Dict:
        """
        Prepare memory layout from PE sections.
        
        Returns a memory layout description that a WASM emulator can use to
        set up its initial memory state.
        """
        if self._initialized:
            return {"status": "already_initialized"}
        
        layout = {
            "entry_point": self.manifest.get("entry_point", 0),
            "image_base": 0x400000,  # Standard Windows user-mode base
            "sections": [],
            "total_size": 0,
        }
        
        for section in self.manifest.get("sections", []):
            region = MemoryRegion(
                address=section["virtual_address"],
                size=section["virtual_size"],
                permissions="rwx",  # Simplified; real PE parsing would check flags
                data=None,  # Emulator fetches from payload.bin
            )
            self.memory_map[region.address] = region
            
            layout["sections"].append({
                "name": section["name"],
                "address": region.address,
                "size": region.size,
                "permissions": region.permissions,
                "offset_in_binary": section.get("pointer_to_raw_data", 0),
            })
            layout["total_size"] += region.size
        
        self._initialized = True
        return layout
    
    def get_entry_point(self) -> int:
        """Get the program's entry point address."""
        return self.manifest.get("entry_point", 0x401000)
    
    def get_initial_registers(self) -> Dict:
        """
        Get initial register state for program startup.
        
        In a real Windows environment, these would be set up by the OS loader.
        Here, we provide sensible defaults.
        """
        return {
            "eax": 0,
            "ebx": 0,
            "ecx": 0,
            "edx": 0,
            "esi": 0,
            "edi": 0,
            "ebp": 0,
            "esp": 0x7fffffff,  # High memory (stack grows downward)
            "eip": self.get_entry_point(),
        }
    
    def get_syscall_hooks(self) -> Dict:
        """
        Expose common Windows syscall mappings.
        
        Returns a dictionary mapping syscall numbers to handler names.
        An actual emulator would call these when the emulated code
        executes an INT 0x2E or similar.
        """
        return {
            "exit_process": {
                "description": "ExitProcess — terminate the program",
                "handler": "exit_process",
            },
            "allocate_memory": {
                "description": "VirtualAlloc — allocate memory",
                "handler": "virtual_alloc",
            },
            "free_memory": {
                "description": "VirtualFree — free memory",
                "handler": "virtual_free",
            },
            "write_file": {
                "description": "WriteFile — write to stdout/file",
                "handler": "write_file",
            },
            "read_file": {
                "description": "ReadFile — read from stdin/file",
                "handler": "read_file",
            },
            "create_file": {
                "description": "CreateFileA — open/create a file",
                "handler": "create_file",
            },
            "get_last_error": {
                "description": "GetLastError — retrieve last error code",
                "handler": "get_last_error",
            },
        }
    
    def export_emulator_config(self) -> Dict:
        """
        Export a complete configuration bundle for the emulator.
        
        This is what a WASM emulator would consume at startup.
        """
        return {
            "version": "1.0",
            "emulator_contract": "x86-wasm-bridge",
            "binary_info": {
                "name": self.manifest.get("name"),
                "architecture": self.manifest.get("architecture"),
                "machine": self.manifest.get("machine"),
                "file_size": self.manifest.get("file_size"),
                "sha256": self.manifest.get("sha256"),
            },
            "memory_layout": self.initialize_memory(),
            "initial_registers": self.get_initial_registers(),
            "syscall_hooks": self.get_syscall_hooks(),
            "entry_point": self.get_entry_point(),
        }
    
    def to_json(self) -> str:
        """Serialize the emulator config to JSON."""
        return json.dumps(self.export_emulator_config(), indent=2)


def generate_emulator_js_stub() -> str:
    """
    Generate a minimal JavaScript stub that a WASM emulator can extend.
    
    This provides the basic structure for an emulator runner that
    loads the config and bridges to WASM execution.
    """
    return '''\
/**
 * x86 Emulator Bridge - JavaScript Stub
 * 
 * This stub provides the contract between the packaged PE binary
 * and a real x86 emulator (WASM or pure JS).
 */

class X86EmulatorBridge {
  constructor(config) {
    this.config = config;
    this.memory = new Uint8Array(0x10000000); // 256 MB virtual address space
    this.registers = { ...config.initial_registers };
    this.running = false;
    this.syscallHandlers = {};
  }

  /**
   * Initialize memory with the PE payload.
   * Assumes the emulator has fetched the binary and passed the data.
   */
  async loadPayload(binaryData) {
    const layout = this.config.memory_layout;
    
    for (const section of layout.sections) {
      const offset = section.offset_in_binary;
      const size = section.size;
      const vaddr = section.address;
      
      // Copy section from binary into virtual memory
      const sectionData = binaryData.slice(offset, offset + size);
      this.memory.set(new Uint8Array(sectionData), vaddr);
    }
    
    console.log('Payload loaded into virtual memory');
  }

  /**
   * Register a syscall handler.
   * The emulator calls these when the emulated code triggers a syscall.
   */
  registerSyscallHandler(name, handler) {
    this.syscallHandlers[name] = handler;
  }

  /**
   * Execute a syscall by name.
   * Real implementation would decode the syscall number and route to the handler.
   */
  async invokeSyscall(name, args) {
    const handler = this.syscallHandlers[name];
    if (!handler) {
      console.warn(`No handler for syscall: ${name}`);
      return { status: 'unhandled', name };
    }
    return handler(args, this);
  }

  /**
   * Fetch the next instruction from the instruction pointer.
   * The emulator's decoder would use this to get bytes to disassemble.
   */
  readInstruction(bytes = 15) {
    const eip = this.registers.eip;
    return this.memory.slice(eip, eip + bytes);
  }

  /**
   * Start execution.
   * A real emulator would implement the instruction decode loop here.
   */
  async execute() {
    this.running = true;
    console.log('Emulator started at EIP:', this.registers.eip.toString(16));
    
    // Placeholder: real implementation would decode and execute instructions
    // For now, emit a stub message
    return { status: 'ready_for_emulator', entry_point: this.registers.eip };
  }

  /**
   * Stop execution.
   */
  halt() {
    this.running = false;
    console.log('Emulator halted');
  }
}

/**
 * Initialize the emulator from a manifest and binary payload.
 * This is called by the boot shell.
 */
async function initializeX86Emulator(config, binaryData) {
  const bridge = new X86EmulatorBridge(config);
  await bridge.loadPayload(binaryData);
  
  // Register default syscall handlers
  bridge.registerSyscallHandler('exit_process', async (args, emu) => {
    console.log('Process exited with code:', args.exit_code);
    emu.halt();
    return { status: 'exited', exit_code: args.exit_code };
  });
  
  bridge.registerSyscallHandler('write_file', async (args, emu) => {
    console.log('Write output:', new TextDecoder().decode(args.data));
    return { status: 'success', bytes_written: args.data.length };
  });
  
  return bridge;
}

window.X86EmulatorBridge = X86EmulatorBridge;
window.initializeX86Emulator = initializeX86Emulator;
'''
