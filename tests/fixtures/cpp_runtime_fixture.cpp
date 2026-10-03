struct Pair {
    int a;
    int b;
};

static int pair_sum(const Pair *p) {
    return p->a + p->b;
}

static int accumulate_pairs(int count) {
    int total = 0;
    for (int i = 0; i < count; ++i) {
        Pair p{i, i + 1};
        total += pair_sum(&p);
    }
    return total;
}

extern "C" int main() {
    // Deliberately exercise compiler-generated C++ control flow, stack
    // locals, address calculation, a helper call, and integer comparisons.
    const int result = accumulate_pairs(7);
    return result == 56 ? 42 : 0;
}
