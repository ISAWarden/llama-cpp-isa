# TurboQuant KV engineering validation

Current pinned upstream: `0f8a414b7587bc412e44611d4c9e2fea876449a6`.
Feature implementations remain selectable patches.

## Current revision verification

All six maintained patches apply individually with their dependencies and together.
Selector all/none round trips restore pristine tracked upstream files. Release CPU
builds (GCC 14.2, two jobs, RPC enabled) pass `test-turbo-quant`,
`test-quantize-fns`, `test-arg-parser`, and `test-emerald-mtp`; `llama-server`
builds and reports revision `0f8a414`.

On Radeon 890M with Mesa 25.0.7, the Release Vulkan dependency-only build passes
16 WHT/cache-chain, 6 SET_ROWS, and 11 turbo4 FLASH_ATTN_EXT cases. Vulkan cache
writer thresholds now exactly match the CPU reference at ±0.145560 and ±0.013963.
Two deterministic threshold-boundary cases (I32/I64 indices) fail with the former
shader constants and pass with the correction, without changing tolerances.
Metal C++ host syntax checks pass; current-pin Mac shader compilation and runtime
verification remain pending. The release workflow is regenerated from this pin.

The measurements and remote build results below are from upstream
`5202104b59ada9005db079eea43882a2b7bf5802`; they do not establish performance,
model quality, or cross-platform compilation on the current pin.

## Environment and limits

Local hardware: Ryzen AI 9 HX 370, Radeon 890M (`gfx1150`, RADV GFX1150),
32 GiB shared RAM; Linux 6.18.52; Mesa RADV 25.0.7. GCC 14.2, shaderc 2025.2, Vulkan SDK
headers/loader 1.4.309. Release CMake builds use native CPU instructions,
`-DGGML_VULKAN=ON`, and two build jobs. Builds and benchmarks run sequentially.
A user-owned inference server remains running from the managed checkout.
Results are therefore not measurements on an otherwise idle machine.

The installed ROCm/HIP is 5.7. The pinned HIP CMake configuration requires
6.1 or newer and rejects it. A minimal gfx1150 HIP kernel compiled but its
runtime aborted with `free(): invalid pointer`. No native HIP implementation,
HIP throughput claim, or CUDA/MUSA validation follows from these probes.

A laptop crash interrupted the first model benchmark and removed temporary
builds/logs. Its results are discarded. Subsequent work and logs are stored
under the ignored, disk-backed `.patch-state/turbo-engineering/`. The running
server leaves little reported device memory available (about 1.4 GiB at an
operator-test snapshot); local weight files start at 2.5 GiB. Model benchmarks,
perplexity, long-context quality, TTFT, concurrency, and peak-memory comparisons
remain unvalidated. Operator agreement does not establish model quality or
end-to-end speedup.

## Changes

- CPU turbo2/3/4 dot products use a bounded 128-float block buffer instead of
  allocating and freeing a full row for every dot. Decoding, packed layout,
  centroids, accumulation order and rotated-domain semantics are preserved.
- SYCL explicitly rejects the new types in generic capability checks and uses
  a destination whitelist matching its SET_ROWS dispatcher. RPC conservatively
  rejects TurboQuant operations because its protocol does not negotiate remote
  operator capability. CPU cache placement remains the safe path there.
- WHT validates optional scale tensor type, contiguity and length. Vulkan honors
  scales and group sizes 32, 64 and 128, with matching dispatch dimensions.
- Vulkan cache writes combine two independent per-lane steps before their
  barrier and use an exact four-comparison threshold search (including ties).
- Vulkan turbo4 uses modern scalar attention and a dedicated CM1 variant that
  stages decoded K/V values into cooperative-matrix tiles. Existing shape,
  shared-memory and precision checks still select scalar fallback. CM2 remains
  disabled for TurboQuant. GQA may turn a single token into multiple effective
  attention rows and use CM1; an effective row count of one stays scalar.
- Vulkan WHT uses subgroup shuffles for within-subgroup butterfly stages and
  shared memory only for cross-subgroup stages. Devices lacking the required
  fixed/full subgroup capabilities retain the shared-memory kernel.
- Metal adds standalone WHT using the existing signed rotation tables, optional
  scales and cooperative workgroup butterflies. C++ host syntax checks and remote
  macOS host/shader builds pass; runtime correctness and performance testing still require a Mac.
- `llama-bench` accepts canonical `turbo2_0`, `turbo3_0`, `turbo4_0` cache names.

## Reproduction

Develop and verify in isolated checkouts using the patch-maker workflow. Do not
switch patches in a checkout with a running build or server. Select `turboquant`
for CPU tests, and `turboquant turboquant_vulkan` for Vulkan tests.

```sh
cmake -S "$source" -B "$build" -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_BUILD_TESTS=ON -DGGML_VULKAN=ON
cmake --build "$build" -j 2 --target test-backend-ops test-turbo-quant \
  test-quantize-fns test-arg-parser llama-bench
ctest --test-dir "$build" \
  -R 'test-turbo-quant|test-quantize-fns|test-arg-parser' --output-on-failure
"$build/bin/test-backend-ops" test -b Vulkan0 -o TURBO_WHT
"$build/bin/test-backend-ops" test -b Vulkan0 -o SET_ROWS -p 'type_dst=turbo4_0'
"$build/bin/test-backend-ops" test -b Vulkan0 -o FLASH_ATTN_EXT -p 'type_K=turbo4_0'
"$build/bin/test-backend-ops" perf -b Vulkan0 \
  -o TURBO_WHT,SET_ROWS,FLASH_ATTN_EXT -p 'turbo4|group_size=128'
```

The bounded CPU dot microbenchmark includes the former allocation-based path
in the same executable. It warms both paths, alternates order, and records five
repetitions of 20,000 calls for 128/256/512/4096 elements. It measures hot-cache
operator cost, not inference latency:

```sh
c++ -O3 -march=native -I "$source/ggml/include" scripts/bench-turbo-dot.cpp \
  -L "$build/bin" -Wl,-rpath,"$build/bin" -lggml-cpu -lggml-base -o bench-turbo-dot
./bench-turbo-dot > dot-bench.csv
```

## Backend scope

| Backend | Validation status and remaining work |
| --- | --- |
| CPU | Allocation removal and numerical regression tests; measurement below |
| AMD Vulkan | WHT, writes and turbo4 attention compiled and operator-tested; measurement below |
| HIP/ROCm | Linux and Windows ROCm release builds pass; local runtime blocked; native cache chain still missing |
| CUDA / MUSA | Windows CUDA 12.4/13.3 x64 and 13.4 ARM64 builds pass; MUSA source reviewed only; no native TurboQuant chain or hardware validation |
| Metal | Native standalone WHT added; remote macOS ARM64 host and Metal shader compilation/linking pass; runtime correctness and performance pending |
| SYCL | Capability reporting corrected; Linux FP16/FP32 and Windows oneAPI builds pass; runtime fallback testing pending |
| RPC | Conservative rejection added; remote runtime not tested |
| OpenCL / WebGPU / CANN / Hexagon / ET | Source-level writer restrictions exclude TurboQuant; no native implementation or local runtime validation |
| OpenVINO | Source-level supported-type restrictions exclude TurboQuant; no native lowering validated |
| VirtGPU | Forwards support queries to its backing backend; transport/runtime validation pending |
| BLAS / ZenDNN / zDNN | Auxiliary backend roles; no claim of a native TurboQuant KV pipeline |

Remote build-only verification was authorized and dispatched on the separate
`turboquant-amd-verification` branch; see the remote verification results below.

## Local correctness results

- CPU `test-turbo-quant`, `test-quantize-fns`, and `test-arg-parser` pass.
  WHT round trips cover groups 32/64/128, multiple heads/sequences, and non-unit
  scales. Dot tests compare the implementation with decoded-domain reference
  accumulation at lengths 128/256/384/512/4096 and four amplitudes.
- AMD Vulkan: 12 standalone WHT cases plus 4 complete cache-chain cases pass;
  4 SET_ROWS and 11 FLASH_ATTN_EXT cases pass. The chains include head sizes
  64 (padded to 128) and 128, GQA, two sequences, partial KV tiles, masks and
  both one-query and seven-query calls. Direct backend graph execution runs the
  tested chain on Vulkan; this is not a trace of a complete model scheduler.
- The original Vulkan WHT passed only 2/12 standalone contract tests before the
  fixes. Both scaled transforms and smaller groups now pass without loosening
  tolerances. Attention tests retain the existing 5e-4 NMSE threshold.
- Metal C++ host files pass `c++ -std=c++17 -fsyntax-only` with the ggml include
  directories. Both 128-element sign tables match the CPU reference exactly.
  These checks do not constitute a Metal build or GPU correctness result.

## CPU operator measurements

Medians of five warmed repetitions; ns per dot. Full samples are in
[turboquant-dot-results.csv](turboquant-dot-results.csv). The same executable
compares the former malloc/dequantize/dot/free sequence with current type traits.

| turbo4 row length | Former allocation path | Bounded block scratch |
| ---: | ---: | ---: |
| 128 | 137.72 | 137.77 |
| 256 | 288.27 | 272.30 |
| 512 | 601.38 | 541.75 |
| 4096 | 4822.02 | 4322.38 |

Allocation removal does not materially improve the 128-element turbo4 dot on
this CPU; longer rows improve modestly. Turbo3 medians range from essentially
unchanged to about 4% faster. No inference throughput claim follows from this
microbenchmark.

## Vulkan operator measurements

[turboquant-operator-results.csv](turboquant-operator-results.csv) contains all
initial and interleaved runs. `scalar` is the modern scalar shader with corrected
shared-memory WHT; `optimized` adds CM1 attention and subgroup WHT. Both include
the four-comparison cache writer and CPU allocation fix. This comparison does
not isolate the cache-writer change, nor is it a pristine-upstream comparison.
The initial runs are labeled `*-perf`; the three subsequent A/B pairs are
`*-paired`. Each test harness measurement batches repeated warmed dispatches.

Interleaved-run medians [min, max], microseconds per operator call:

| Operator | Scalar/shared WHT | CM1/subgroup WHT |
| --- | ---: | ---: |
| WHT, group 128, 180 groups | 15.07 [9.72, 15.10] | 8.65 [8.41, 12.60] |
| Attention, KV 512, query batch 1 | 329.94 [325.38, 339.13] | 287.08 [287.03, 289.06] |
| Attention, KV 512, query batch 128 | 15098.49 [3007.56, 16610.44] | 1607.44 [1604.73, 2572.30] |
| Attention, KV 4096, query batch 1 | 2068.20 [487.82, 2076.09] | 352.26 [325.29, 927.41] |
| Attention, KV 4096, query batch 128 | 45364.26 [42721.47, 47549.64] | 9934.17 [9735.40, 12876.18] |
| Attention, KV 16384, query batch 1 | 6030.43 [5855.15, 6092.14] | 2575.60 [2545.37, 2660.55] |
| Attention, KV 16384, query batch 128 | 141387.25 [90472.00, 163465.08] | 26327.75 [25629.52, 40022.00] |

Attention uses head dimension 128, two KV heads, GQA ratio four, one sequence,
a mask, F32 accumulation, and populated synthetic K/V tensors. WHT uses shape
[384,5,2,2], i.e. 180 rotation groups. Timings vary substantially with the
user's concurrent server workload: even the unchanged SET_ROWS control varies
between runs. The results support a prefill optimization opportunity and show
lower measured operator times, but do not establish a stable speedup factor,
model tokens/sec, or break-even context versus FP16.

## Matched cache-format operator comparison

The final patched build ran matching attention shapes with FP16, Q8_0, Q4_0
and turbo4 K/V. Three warmed repetitions, median microseconds per call:

| KV entries | Queries | FP16 | Q8_0 | Q4_0 | Turbo4 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 1 | 16.84 | 15.56 | 15.31 | 29.53 |
| 512 | 128 | 96.91 | 173.47 | 174.92 | 359.48 |
| 4096 | 1 | 67.21 | 53.05 | 47.97 | 91.78 |
| 4096 | 128 | 697.02 | 1236.12 | 1273.32 | 2284.67 |
| 16384 | 1 | 223.91 | 161.16 | 146.71 | 299.14 |
| 16384 | 128 | 2895.12 | 5748.07 | 5485.27 | 9160.23 |

Full samples/ranges: [turboquant-format-results.csv](turboquant-format-results.csv).
These operator tests exclude cache writes and query/output WHT. Turbo4 remains
slower than FP16 in every tested shape, despite improving on the scalar
TurboQuant path. No break-even context was established. Packed centroid loading,
lookup cost and further attention tiling remain optimization opportunities;
there is no evidence here that the format should replace FP16 for latency.

Reproduce the matching format cases with:

```sh
"$build/bin/test-backend-ops" perf -b Vulkan0 -o FLASH_ATTN_EXT \
  -p 'hsk=128,hsv=128,nh=2,nr23=\[4,1\]'
```

## Remaining validation and implementation

Native HIP/CUDA/MUSA writers, signed/scaled WHT and attention are still missing;
no new accelerator patch advertises partial support. The installed HIP stack
must first be upgraded to a version supported by the pinned tree and pass a
minimal runtime smoke test. SYCL capability fallback testing, RPC remote
testing, and Mac runtime testing are pending. Remote compilation does not
establish backend execution correctness, quality, or performance.

Pristine-upstream model comparisons, FP16 patch-overhead comparisons, perplexity,
long-context retrieval, concurrent serving, MoE cache behavior, profiler traces,
and peak host/device memory remain outstanding. The AMD results above validate
specific operator graphs and their implementation agreement, not this entire
cross-backend project or deployment readiness.

## Integration checks and working checkout

Final exported patches were reconstructed by the temporary-index exporter.
The `turboquant` dependency-only selection and the complete maintained selection
both built in a separate CPU/RPC build and passed `test-turbo-quant`,
`test-quantize-fns`, and `test-arg-parser`. The final Vulkan dependency closure
built and passed the 16 WHT/chain, 4 SET_ROWS and 11 attention cases above.
The benchmark parser accepts canonical turbo4 arguments and reaches the expected
missing-model error in a no-model sentinel check.

Selector checks covered turboquant alone, its Vulkan and Metal dependency
closures, all maintained features, and none. The selector sandbox ended with
no selected patches and a clean upstream worktree. `git diff --check` passes;
the catalog base and parent gitlink remain pinned to the original revision.
Patch and measured-library hashes are recorded in the
[validation manifest](turboquant-validation-manifest.json).

The real managed checkout was not switched or edited. Its running server and
original selection remain intact: `turboquant`, `turboquant_vulkan`,
`turboquant_metal`, `moe_expert_cache`, `hauhaucs_fastmtp`, `emerald_mtp`.
It still contains the previously applied patch versions. After its workload
has stopped, reapply with `./configure.py --all` and rebuild to use these exports.
Do not switch it while that server is running.

## Remote compile verification

The build-only [verification run](https://github.com/ISAWarden/llama-cpp-isa/actions/runs/35713214957)
passed at `a579a8c486125758258fc666837110e2a9765d95` on branch
`turboquant-amd-verification`. All 23 platform/UI build jobs, source preparation,
and final packaging succeeded. Publication was skipped (`create_release=false`).
Commits were made without GPG signing; neither the upstream pin nor gitlink changed.

The matrix covers macOS ARM64/Intel, iOS, Android ARM64, Linux x64/ARM64 CPU and
Vulkan, Linux ROCm/OpenVINO/SYCL FP16 and FP32, Windows x64/ARM64 CPU, Windows
Vulkan/OpenCL/ROCm/OpenVINO/SYCL, and Windows CUDA 12.4/13.3 x64 and 13.4 ARM64.
The macOS ARM64 job explicitly compiled and linked the TurboQuant Metal shaders.

The [first run](https://github.com/ISAWarden/llama-cpp-isa/actions/runs/35712572099)
found an Android SDK setup error: the setup action requested the retired `tools`
package before compilation. The workflow generator now explicitly requests
`platform-tools`; its generated workflow passes the drift check. The retry passed
Android. The first Windows ROCm job exceeded its three-hour execution limit;
its retry succeeded. No feature source compilation fixes were required by this matrix.

Local checks for the workflow fix: generator regeneration and `--check`, release
packaging tests, and `git diff --check` pass. Feature patch hashes remain those in
the validation manifest. These remote results validate compilation and packaging,
not GPU runtime correctness, inference performance, model quality, or native
TurboQuant support on backends that still use CPU fallback.
