extern "C" int main() {
    struct Pair { int a; int b; };
    Pair p{21, 21};
    return p.a + p.b;
}
