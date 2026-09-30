typedef unsigned int u32;
typedef signed int s32;

static volatile u32 divisor = 3u;
static volatile s32 signed_divisor = -3;

static u32 integer_mix(u32 a, u32 b) {
    a += b;
    a ^= b;
    a = (a << 5) | (a >> 27);
    a *= 33u;
    a /= divisor;
    a %= 7u;
    a -= 0x1234u;
    if (a & 0x40u) a |= 0x8000u;
    else a &= ~0x8000u;
    return a;
}

int main(void) {
    u32 value = integer_mix(0x12345678u, 0x0FEDCBA9u);
    s32 signed_value = -123456789;
    s32 quotient = signed_value / signed_divisor;
    s32 remainder = signed_value % signed_divisor;
    return value == 0xFFFFEDCEu && quotient == 41152263 && remainder == 0 ? 1 : 0;
}
