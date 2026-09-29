# Prism low-bit weights

`prism` ports PTQ1_0/PQ2_0 quantization and the folded-Hadamard weight runtime from
[PrismML-Eng/llama.cpp](https://github.com/PrismML-Eng/llama.cpp), reviewed at
[`87268f775d74cf8f7ffc6c22a95684aa55995533`](https://github.com/PrismML-Eng/llama.cpp/commit/87268f775d74cf8f7ffc6c22a95684aa55995533).
The official upstream pin is unchanged. Prism's separate speculative decoding,
KV mean-centering, and recurrent-state ring changes are not included.

```sh
./configure.py --enable quant_type_slots prism
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build -j
llama.cpp/build/bin/llama-cli -m model-PTQ1_0.gguf
```

Select the backend using the normal CMake options (`GGML_VULKAN`, `GGML_CUDA`,
`GGML_HIP`, `GGML_METAL`, or `GGML_SYCL`). The patch includes CPU, CUDA/HIP, Metal,
Vulkan and SYCL implementations. Backend availability and individual operation
support still depend on hardware and tensor shape. CPU fallback remains available.

| Format | Tensor type ID | Weights per block | Bytes per block |
| --- | --- | --- | --- |
| `PTQ1_0` | 143 | 128 | 28 (1.75 bits/weight) |
| `PQ2_0` | 142 | 128 | 34 (2.125 bits/weight) |

Both carry a half-precision scale per 128 weights. PTQ1_0 packs ternary values in
base 3; PQ2_0 uses two-bit symbols. Upstream `Q1_0`, `Q2_0`, and `TQ1_0` retain their
existing IDs and layouts. `quant_type_slots` reserves the shared type-table capacity
so Prism and TurboQuant can be selected independently or together; it adds no kernels.

Use compatible Prism/Bonsai GGUF files. For suitable ternary weights, the quantizer
also accepts:

```sh
llama.cpp/build/bin/llama-quantize input.gguf output-PTQ1_0.gguf PTQ1_0
llama.cpp/build/bin/llama-quantize input.gguf output-PQ2_0.gguf PQ2_0
```

These are low-bit weight formats, not KV-cache formats. Applying ternary quantization
to an arbitrary dense model is not a quality-preserving conversion. The runtime reads
`prism.hadamard.*` metadata to transform activations and embedding lookups for folded
weights, including tied output embeddings. The HF converter carries the corresponding
`hadamard_packing.json` contract into GGUF. Unsupported transform contracts are rejected.

Vulkan uses scalar/cooperative-matrix-1 matmul and integer-dot matvec paths. These
formats have no cooperative-matrix-2 decoder; that path uses dequantization fallback.
On-device PTQ1_0 encoding is not implemented, so unsupported copies/row writes fall
back to CPU. Weight inference does not require on-device encoding.

The optional Hopper Q1/PQ2 prefill path uses `-DGGML_CUDA_HOPPER_Q1=ON` and
`-DGGML_CUDA_CUTLASS_DIR=/path/to/cutlass`. It requires a compatible CUTLASS
checkout and an sm_90a build target. This opt-in path is not covered by the
default release matrix.

## Validation

Linux x86-64 Release builds pass the quantization tests, host PTQ element-mapping
and packed-dot tests, PQ row-shape tests, and `test-prism-model`. The combined
selection also passes `test-turbo-quant`, `test-arg-parser`, and the Prism model test.
Independent Prism, TurboQuant, and all/none selector round trips restore pristine upstream.

On AMD Radeon Graphics (RADV GFX1150), Vulkan passes 473 filtered `MUL_MAT`,
`MUL_MAT_ID`, and `GET_ROWS` cases for Prism types, and 35 Hadamard cases including
signed transforms and widths through 8192. Unsupported shape cases are skipped.

`test-prism-model` generates tiny deterministic Llama fixtures, including a tied
embedding/output variant. It compares unfolded F32, folded F32, PQ2_0 and PTQ1_0
logits after actual GGUF writing, quantization, loading, and decode. It passes on
CPU and Vulkan. Relative logit RMS error is below 3e-7 for folded F32 and below
0.009 for both quantized formats in these fixtures. This tests the runtime
contract; it does not measure real-model quality. Run its CPU test through CTest,
or `build/bin/test-prism-model --gpu` in a build with the desired GPU backend.

The full remote release build matrix and packaging passed on
`codex/prism-quantization` at `10a806bbb390b5c508f1a43f4b889dc5abb12666`
([verification run](https://github.com/ISAWarden/llama-cpp-isa/actions/runs/36609558867)),
including CUDA, HIP/ROCm, Metal shader compilation, Vulkan, and SYCL. Windows ARM64
passed after retrying an LLVM OpenMP download that failed with an SSL connection
error. Publication was disabled.

Runtime validation covers CPU and Vulkan; the other GPU backends have build
coverage only. Compilation alone does not establish device runtime correctness,
real-model quality, or a speedup over upstream. No performance improvement is
claimed for this port.
