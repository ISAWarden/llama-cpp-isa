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

## Validation

On Linux x86-64, the Release CPU build passes `test-quantize-fns`,
`test-ptq1_0-element-map`, and `test-pq2-row-shapes`. Filtered CPU `MUL_MAT`,
`MUL_MAT_ID`, and `GET_ROWS` tests pass for both formats. Independent Prism,
TurboQuant, and all/none selector round trips restore pristine upstream.

Vulkan runtime and the remote release matrix are under verification. Compilation
alone does not establish device runtime correctness, model quality, or a speedup
over upstream. No performance improvement is claimed for this port.
