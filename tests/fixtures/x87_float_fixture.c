#ifdef __cplusplus
extern "C"
#endif
int _fltused = 0;

typedef unsigned int u32;
typedef unsigned long long u64;
typedef double f64;

typedef union { f64 d; u64 u; } bits_u;

static volatile f64 lhs = 1.5;
static volatile f64 rhs = 2.25;
static volatile f64 out;

int main(void) {
    f64 a = lhs;
    f64 b = rhs;

    /* Deliberately keep this x87-heavy: FLD/FSTP m64 plus
       register-stack FMULP/FADDP and arithmetic variants. */
    f64 mul = a * b;
    f64 add = mul + b;
    f64 sub = add - a;
    f64 rev = a - b;
    f64 div = sub / a;
    f64 revdiv = a / b;
    f64 result = div + revdiv + rev;

    out = result;

    bits_u bits;
    bits.d = out;

    /* Expected: 2.75 + 2/3 - 0.75 = 2.666... */
    return bits.u == 0x4012AAAAAAAAAAAAULL ? 1 : 0;
}
