// Compare the former heap-based dot path with current CPU type traits.
// Build against a Release TurboQuant build; see docs/turboquant-validation.md.
#include "ggml.h"
#include "ggml-cpu.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

int main() {
    ggml_init_params params{1024*1024, nullptr, true};
    auto * ctx = ggml_init(params);
    volatile float sink = 0;
    std::puts("type,n,repeat,path,ns_per_dot");
    for (auto type : {GGML_TYPE_TURBO2_0, GGML_TYPE_TURBO3_0, GGML_TYPE_TURBO4_0}) {
        const auto * traits = ggml_get_type_traits(type);
        const auto * cpu = ggml_get_type_traits_cpu(type);
        for (int n : {128, 256, 512, 4096}) {
            std::vector<float> x(n), y(n);
            std::vector<unsigned char> packed(ggml_row_size(type, n));
            for (int i = 0; i < n; ++i) { x[i] = sinf(i*0.17f); y[i] = cosf(i*0.13f); }
            traits->from_float_ref(x.data(), packed.data(), n);
            for (int repeat = -1; repeat < 5; ++repeat) {
                // Alternate order; discard the first pair as warmup.
                for (int pass = 0; pass < 2; ++pass) {
                    const int current = (pass + (repeat & 1)) % 2;
                    const int count = 20000;
                    const auto start = std::chrono::steady_clock::now();
                    for (int k = 0; k < count; ++k) {
                        float dot = 0;
                        if (current) {
                            cpu->vec_dot(n, &dot, 0, packed.data(), 0, y.data(), 0, 1);
                        } else {
                            float * tmp = static_cast<float *>(malloc(n*sizeof(float)));
                            if (!tmp) return 1;
                            traits->to_float(packed.data(), tmp, n);
                            for (int i = 0; i < n; ++i) dot += tmp[i]*y[i];
                            free(tmp);
                        }
                        sink = dot;
                    }
                    const double ns = std::chrono::duration<double, std::nano>(
                        std::chrono::steady_clock::now()-start).count()/count;
                    if (repeat >= 0) {
                        std::printf("%s,%d,%d,%s,%.2f\n", ggml_type_name(type), n, repeat,
                                    current ? "bounded" : "malloc", ns);
                    }
                }
            }
        }
    }
    ggml_free(ctx);
    return sink == 123456;
}
