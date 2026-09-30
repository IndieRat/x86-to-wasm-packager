#ifdef __cplusplus
extern "C"
#endif
/* Clang's MSVC x87 code references the MSVC floating-point marker. */
int _fltused = 0;

typedef unsigned int u32;
typedef float f32;

typedef union { f32 f; u32 u; } bits_u;

static volatile f32 lhs = 1.5f;
static volatile f32 rhs = 2.25f;
static volatile f32 out;

int main(void) {
    f32 a = lhs;
    f32 b = rhs;
    f32 c = (a * b) + b;
    out = c;
    bits_u bits;
    bits.f = out;
    return bits.u == 0x40B40000u ? 1 : 0;
}
