/*
 * XWASM IA-32 decoder front-end.
 *
 * This file is included by runtime.c after the guest CPU state/helpers are
 * defined.  The decoder owns instruction-boundary parsing and lookup; the
 * legacy executor remains behind it until each semantic family is migrated.
 */
#include "generated_decode_table.h"

typedef struct {
    uint32_t start;
    uint32_t cursor;
    uint8_t prefixes;
    uint8_t operand16;
    uint8_t address16;
    uint8_t map;
    uint8_t opcode;
    uint8_t modrm;
    uint8_t has_modrm;
    uint8_t sib;
    uint8_t has_sib;
    uint8_t disp_size;
    uint8_t imm_size;
    uint8_t rel_size;
    int8_t modrm_ext;
    const x86_decode_entry_t *entry;
} x86_decoded_t;

#define X86_PREFIX_LOCK 0x01u
#define X86_PREFIX_REPNZ 0x02u
#define X86_PREFIX_REP 0x04u
#define X86_PREFIX_SEG 0x08u
#define X86_PREFIX_OP16 0x10u
#define X86_PREFIX_ADDR16 0x20u

static int x86_is_prefix(uint8_t b) {
    switch (b) {
        case 0xF0: case 0xF2: case 0xF3:
        case 0x2E: case 0x36: case 0x3E: case 0x26: case 0x64: case 0x65:
        case 0x66: case 0x67:
            return 1;
        default:
            return 0;
    }
}

static void x86_record_prefix(x86_decoded_t *d, uint8_t b) {
    if (b == 0xF0) d->prefixes |= X86_PREFIX_LOCK;
    else if (b == 0xF2) d->prefixes |= X86_PREFIX_REPNZ;
    else if (b == 0xF3) d->prefixes |= X86_PREFIX_REP;
    else if (b == 0x66) { d->prefixes |= X86_PREFIX_OP16; d->operand16 ^= 1u; }
    else if (b == 0x67) { d->prefixes |= X86_PREFIX_ADDR16; d->address16 ^= 1u; }
    else d->prefixes |= X86_PREFIX_SEG;
}

static const x86_decode_entry_t *x86_find_entry(uint8_t map, uint8_t opcode,
                                                 int has_modrm, uint8_t modrm) {
    const x86_decode_entry_t *best = 0;
    for (uint32_t i = 0; i < X86_DECODE_TABLE_COUNT; ++i) {
        const x86_decode_entry_t *e = &x86_decode_table[i];
        if (e->map != map || e->opcode != opcode) continue;
        if (e->needs_modrm != (uint8_t)has_modrm) continue;
        if (e->modrm_ext >= 0) {
            if (!has_modrm || ((modrm >> 3) & 7u) != (uint8_t)e->modrm_ext) continue;
        }
        best = e;
        break;
    }
    return best;
}

static int x86_decode_modrm_tail(x86_decoded_t *d) {
    uint8_t m = d->modrm;
    uint8_t mod = m >> 6;
    uint8_t rm = m & 7u;

    if (mod == 3) return 0;

    if (d->address16) {
        d->disp_size = (mod == 0 && rm == 6) ? 2 : (mod == 1 ? 1 : (mod == 2 ? 2 : 0));
        d->cursor += d->disp_size;
        return 0;
    }

    if (rm == 4) {
        d->has_sib = 1;
        d->sib = MEM8(d->cursor++);
        uint8_t base = d->sib & 7u;
        if (mod == 0 && base == 5) d->disp_size = 4;
    } else if (mod == 0 && rm == 5) {
        d->disp_size = 4;
    }
    if (mod == 1) d->disp_size = 1;
    else if (mod == 2) d->disp_size = 4;
    d->cursor += d->disp_size;
    return 0;
}

static int x86_id_is(const char *a,const char *b){while(*a&&*b){if(*a++!=*b++)return 0;}return *a==0&&*b==0;}

static void x86_decode_payload_size(x86_decoded_t *d) {
    const char *id = d->entry ? d->entry->id : 0;
    if (!id) return;
    if (x86_id_is(id, "MOV_R32_IMM32") ||
        x86_id_is(id, "ADD_RM32_IMM32") ||
        x86_id_is(id, "SUB_RM32_IMM32") ||
        x86_id_is(id, "CMP_RM32_IMM32") ||
        x86_id_is(id, "ADC_RM32_IMM32") ||
        x86_id_is(id, "SBB_RM32_IMM32") ||
        x86_id_is(id, "IMUL_R32_RM32_IMM32") ||
        x86_id_is(id, "ADD_EAX_IMM32") ||
        x86_id_is(id, "SUB_EAX_IMM32") ||
        x86_id_is(id, "CMP_EAX_IMM32") ||
        x86_id_is(id, "PUSH_IMM32")) d->imm_size = 4;
    else if (x86_id_is(id, "ADD_RM32_IMM8") ||
             x86_id_is(id, "SUB_RM32_IMM8") ||
             x86_id_is(id, "CMP_RM32_IMM8") ||
             x86_id_is(id, "ADC_RM32_IMM8") ||
             x86_id_is(id, "SBB_RM32_IMM8") ||
             x86_id_is(id, "SHL_RM32_IMM8") ||
             x86_id_is(id, "SHR_RM32_IMM8") ||
             x86_id_is(id, "SAR_RM32_IMM8") ||
             x86_id_is(id, "ROL_RM32_IMM8") ||
             x86_id_is(id, "ROR_RM32_IMM8") ||
             x86_id_is(id, "RCL_RM32_IMM8") ||
             x86_id_is(id, "RCR_RM32_IMM8") ||
             x86_id_is(id, "IMUL_R32_RM32_IMM8") ||
             x86_id_is(id, "BT_RM32_IMM8") ||
             x86_id_is(id, "BTS_RM32_IMM8") ||
             x86_id_is(id, "BTR_RM32_IMM8") ||
             x86_id_is(id, "BTC_RM32_IMM8") ||
             x86_id_is(id, "PUSH_IMM8")) d->imm_size = 1;
    else if (x86_id_is(id, "CALL_REL32") ||
             x86_id_is(id, "JMP_REL32") ||
             x86_id_is(id, "JE_REL32") ||
             x86_id_is(id, "JNE_REL32")) d->rel_size = 4;
    else if (x86_id_is(id, "JMP_REL8") ||
             x86_id_is(id, "JE_REL8") ||
             x86_id_is(id, "JNE_REL8") ||
             x86_id_is(id, "JB_REL8") ||
             x86_id_is(id, "JAE_REL8") ||
             x86_id_is(id, "JA_REL8") ||
             x86_id_is(id, "JBE_REL8") ||
             x86_id_is(id, "JL_REL8") ||
             x86_id_is(id, "JGE_REL8") ||
             x86_id_is(id, "JLE_REL8") ||
             x86_id_is(id, "JG_REL8") ||
             x86_id_is(id, "JO_REL8") ||
             x86_id_is(id, "JNO_REL8") ||
             x86_id_is(id, "JS_REL8") ||
             x86_id_is(id, "JNS_REL8") ||
             x86_id_is(id, "JP_REL8") ||
             x86_id_is(id, "JNP_REL8") ||
             x86_id_is(id, "JCXZ_REL8") ||
             x86_id_is(id, "LOOP_REL8") ||
             x86_id_is(id, "LOOPE_REL8") ||
             x86_id_is(id, "LOOPNE_REL8")) d->rel_size = 1;
}
static int x86_decode_instruction(x86_decoded_t *d) {
    d->start = eip;
    d->cursor = eip;
    d->prefixes = 0;
    d->operand16 = 0;
    d->address16 = 0;
    d->map = 0;
    d->opcode = 0;
    d->modrm = 0;
    d->has_modrm = 0;
    d->sib = 0;
    d->has_sib = 0;
    d->disp_size = 0;
    d->imm_size = 0;
    d->rel_size = 0;
    d->modrm_ext = -1;
    d->entry = 0;

    for (uint32_t n = 0; n < 15u && x86_is_prefix(MEM8(d->cursor)); ++n) {
        x86_record_prefix(d, MEM8(d->cursor++));
    }

    if (d->cursor - d->start >= 15u) {
        cpu_error = 0xD001u;
        return -1;
    }

    d->opcode = MEM8(d->cursor++);
    if (d->opcode == 0x0F) {
        d->map = 1;
        if (MEM8(d->cursor) == 0x38 || MEM8(d->cursor) == 0x3A) {
            /* Three-byte maps are decoded structurally now; execution is
             * intentionally rejected until their semantic families land. */
            d->map = MEM8(d->cursor++) == 0x38 ? 2 : 3;
        }
        d->opcode = MEM8(d->cursor++);
    }

    /* First locate an opcode candidate without consuming ModR/M. */
    d->entry = x86_find_entry(d->map, d->opcode, 0, 0);

    /* If there is no fixed-form entry, try the ModR/M forms. */
    if (!d->entry) {
        d->entry = x86_find_entry(d->map, d->opcode, 1, MEM8(d->cursor));
        if (d->entry) {
            d->has_modrm = 1;
            d->modrm = MEM8(d->cursor++);
            d->modrm_ext = (int8_t)((d->modrm >> 3) & 7u);
            x86_decode_modrm_tail(d);
        }
    } else if (d->entry->needs_modrm) {
        d->has_modrm = 1;
        d->modrm = MEM8(d->cursor++);
        d->modrm_ext = (int8_t)((d->modrm >> 3) & 7u);
        x86_decode_modrm_tail(d);
    }

    if (!d->entry) {
        /* Opcode forms that use an opcode-embedded register are represented
         * by one entry for several opcode bytes in the JSON database. */
        if (d->map == 0) {
            if ((d->opcode >= 0xB8 && d->opcode <= 0xBF) ||
                (d->opcode >= 0x40 && d->opcode <= 0x4F) ||
                (d->opcode >= 0x50 && d->opcode <= 0x5F)) {
                d->entry = x86_find_entry(0, d->opcode, 0, 0);
            }
        }
    }

    if (!d->entry) {
        cpu_error = 0xD000u | d->opcode;
        return -2;
    }

    x86_decode_payload_size(d);
    if(d->imm_size){if(d->cursor-d->start+d->imm_size>15u){cpu_error=0xD003u;return -5;}d->cursor+=d->imm_size;}
    if(d->rel_size){if(d->cursor-d->start+d->rel_size>15u){cpu_error=0xD004u;return -6;}d->cursor+=d->rel_size;}

    /* Operand-size/address-size overrides are decoded correctly, but the
     * current semantic executor only consumes 32-bit forms. */
    if (d->address16) {
        cpu_error = 0xD100u | d->opcode;
        return -3;
    }
    if (d->operand16) {
        int string16 = x86_id_is(d->entry->id, "MOVSW") ||
                       x86_id_is(d->entry->id, "CMPSW") ||
                       x86_id_is(d->entry->id, "SCASW") ||
                       x86_id_is(d->entry->id, "LODSW") ||
                       x86_id_is(d->entry->id, "STOSW");
        int group2_16 = x86_id_is(d->entry->id, "SHL_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "SHR_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "SAR_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "ROL_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "ROR_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "RCL_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "RCR_RM32_IMM8") ||
                        x86_id_is(d->entry->id, "SHL_RM32_1") ||
                        x86_id_is(d->entry->id, "SHR_RM32_1") ||
                        x86_id_is(d->entry->id, "SAR_RM32_1");
        if (!string16 && !group2_16) {
            cpu_error = 0xD100u | d->opcode;
            return -3;
        }
    }

    if (d->cursor - d->start > 15u) {
        cpu_error = 0xD002u;
        return -4;
    }

    return 0;
}

static int cpu_step(void) {
    x86_decoded_t d;
    uint32_t saved_eip = eip;
    uint32_t before_flags = eflags;
    uint32_t before_eax = regs[R_EAX];
    uint32_t before_ecx = regs[R_ECX];
    uint32_t before_edx = regs[R_EDX];
    uint32_t before_ebx = regs[R_EBX];
    uint32_t before_opcode = (uint32_t)MEM8(saved_eip);
    int decoded = x86_decode_instruction(&d);
    if (decoded < 0) return decoded;

    /*
     * Semantic migration point.
     *
     * The old executor already implements the working v0.8 foundation
     * semantics. Keeping it behind a verified decoder lets us migrate each
     * instruction family independently without maintaining two decoders.
     */
    eip = saved_eip;
    decoded_prefixes = d.prefixes;
    decoded_operand16 = d.operand16;
    last_decoded_map = d.map;
    last_decoded_opcode = d.opcode;
    last_decoded_length = d.cursor - d.start;

    /*
     * Refined semantic dispatch:
     * the decoder's instruction ID is authoritative for migrated families.
     * INC is dispatched from the decoded semantic ID rather than re-decoding
     * the raw opcode in the legacy switch.
     */
    if (d.entry && d.entry->id) {
        if (x86_id_is(d.entry->id,"RCR_RM32_1") ||
            x86_id_is(d.entry->id,"RCR_RM32_IMM8") ||
            x86_id_is(d.entry->id,"RCR_RM32_CL")) {
            uint32_t op_ip=d.cursor-d.disp_size;
            uint32_t v=decoded_operand16 ? (uint32_t)modrm_read16(d.modrm,&op_ip) : modrm_read32(d.modrm,&op_ip);
            uint32_t bits=decoded_operand16?16u:32u;
            uint32_t mask=bits==16?0xFFFFu:0xFFFFFFFFu;
            uint32_t sign=1u<<(bits-1u);
            uint32_t count=x86_id_is(d.entry->id,"RCR_RM32_1")?1u:
                          x86_id_is(d.entry->id,"RCR_RM32_CL")?(regs[R_ECX]&31u):MEM8(d.cursor);
            uint32_t modulus=bits==16?17u:33u;
            count&=31u; count%=modulus;
            if(count){
                uint32_t cf=(eflags&CF)?1u:0u;
                uint64_t x=((uint64_t)cf<<bits)|(v&mask);
                uint64_t fullmask=(1ull<<(bits+1u))-1ull;
                x=((x>>count)|(x<<(bits+1u-count)))&fullmask;
                uint32_t r=(uint32_t)x&mask;
                cf=(uint32_t)((x>>bits)&1u);
                uint32_t of=((r&sign)?1u:0u)^((r>>(bits-2u))&1u);
                set_rotate_flags(r,cf,count==1u,of);
                uint32_t write_ip=d.cursor-d.disp_size;
                if(decoded_operand16)modrm_write16(d.modrm,&write_ip,(uint16_t)r);
                else modrm_write32(d.modrm,&write_ip,r);
            }
            eip=d.cursor+(x86_id_is(d.entry->id,"RCR_RM32_IMM8")?1u:0u);
            last_dispatch_id=X86_DISPATCH_RCR;
            last_dispatch_count++;
            x86_trace_record(saved_eip,before_flags,before_eax,before_ecx,before_edx,before_ebx,
                             before_opcode,last_dispatch_id);
            return 0;
        }
        if (d.entry->id[0]=='I' && d.entry->id[1]=='N' &&
            d.entry->id[2]=='C' && d.entry->id[3]=='_' &&
            d.entry->id[4]=='R' && d.entry->id[5]=='3' &&
            d.entry->id[6]=='2' && d.entry->id[7]==0) {
            uint32_t reg=(uint32_t)(d.opcode-0x40u);
            uint32_t old_flags=eflags;
            uint32_t a=regs[reg], r=a+1u;
            regs[reg]=r;
            set_add_flags(a,1u,r);
            eflags=(eflags&~CF)|(old_flags&CF);
            eip=saved_eip+1u;
            last_dispatch_id=X86_DISPATCH_INC_R32;
            last_dispatch_count++;
            x86_trace_record(saved_eip,before_flags,before_eax,before_ecx,before_edx,before_ebx,
                             before_opcode,last_dispatch_id);
            return 0;
        }
    }

    last_dispatch_id=X86_DISPATCH_NONE;
    int result=cpu_step_legacy();
    x86_trace_record(saved_eip,before_flags,before_eax,before_ecx,before_edx,before_ebx,
                     before_opcode,last_dispatch_id);
    return result;
}
