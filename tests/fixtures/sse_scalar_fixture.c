int _fltused = 0;

#include <stdint.h>
static volatile float lhs32=1.5f,rhs32=2.25f;
static volatile double lhs64=1.5,rhs64=2.25;
typedef union{float f;uint32_t u;}f32_bits;
typedef union{double f;uint64_t u;}f64_bits;
int main(void){float a=lhs32,b=rhs32,sf=(a*b)+b;double x=lhs64,y=rhs64,sd=(x*y)+y;f32_bits fb;f64_bits db;fb.f=sf;db.f=sd;if(fb.u!=0x40B40000u)return 0;if(db.u!=0x4016800000000000ULL)return 0;return 1;}
