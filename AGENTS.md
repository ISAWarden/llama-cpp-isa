# Working in llama-cpp-isa

This project focuses on pristine, fastest-possible AI inference research and deployment. Pursue measurable improvements in throughput, latency, and memory use while preserving correctness, model quality, and deployment reliability. Keep the official upstream base clean and express our improvements as selectable patches. Compare performance against upstream under matching hardware, model, and runtime settings; distinguish experimental results from deployment-ready behavior.

This root `AGENTS.md` is the authoritative project instruction file for the entire workspace, including `llama.cpp/`. Do not look for, read, or follow other agent instruction files, including `llama.cpp/AGENTS.md`. Use upstream source and technical documentation as references, not its agent or contribution workflows. Read `README.md` for usage and `patches/series.json` for the ordered feature catalog and pinned base.

## Layout and setup

- `llama.cpp/`: official Git submodule; its revision must match the base in `patches/series.json`.
- `patches/<feature_name>.patch`: feature implementation; this is the source of truth for our changes.
- `patches/series.json`: application order, dependency declarations, and upstream revision.
- `configure.py`: Python standard-library patch manager with a curses selector.
- `.patch-state/`: ignored local selection state, saved patch contents, and application lock.

For a fresh clone, use `git clone --recurse-submodules`. For an existing clone with an uninitialized submodule, use `git submodule update --init --recursive`.

Start with `git status --short` and `./configure.py --list`. Applied patches normally make the submodule dirty. Do not treat those changes as accidental edits.

## Finding your way around llama.cpp

Paths below are relative to `llama.cpp/`:

| Area | Start here |
| --- | --- |
| Public inference API | `include/llama.h` |
| Decode execution and graph construction | `src/llama-context.cpp`, `src/llama-graph.cpp`, `src/llama-batch.cpp` |
| Model architectures and loading | `src/models/`, `src/llama-arch.cpp`, `src/llama-model.cpp`, `src/llama-model-loader.cpp` |
| KV cache and recurrent state | `src/llama-kv-cache*`, `src/llama-memory*` |
| Sampling and tokenization | `src/llama-sampler.cpp`, `src/llama-vocab.cpp` |
| Tensor types, operations, and quantization | `ggml/include/ggml.h`, `ggml/src/ggml.c`, `ggml/src/ggml-quants.*`, `ggml/src/ggml-common.h` |
| Backend scheduling, allocation, and transfers | `ggml/src/ggml-backend.cpp`, `ggml/src/ggml-alloc.c`, `ggml/include/ggml-backend.h` |
| CPU kernels | `ggml/src/ggml-cpu/`, especially `ops.cpp` and `ggml-cpu.c` |
| GPU kernels | `ggml/src/ggml-vulkan/` and its `vulkan-shaders/`; other backends live in `ggml/src/ggml-cuda/`, `ggml-metal/`, `ggml-hip/`, etc. |
| Shared runtime options and utilities | `common/arg.cpp`, `common/common.*`, and the rest of `common/` |
| Serving and command-line inference | `tools/server/`, `tools/cli/`; web UI in `tools/ui/` |
| Performance and quality measurement | `tools/llama-bench/`, `tools/batched-bench/`, `tools/perplexity/` |
| Model conversion and weight quantization | `convert_hf_to_gguf.py`, `conversion/`, `gguf-py/`, `tools/quantize/`, `tools/imatrix/` |
| Build configuration and technical docs | `CMakeLists.txt`, `cmake/`, per-directory CMake files, `docs/build.md`, `docs/backend/` |

Trace inference changes from CLI options through context/graph construction to backend kernels. Use `rg` for symbols and `rg --files` for paths; inspect only the relevant areas. Find a feature's touched files with `rg '^diff --git' patches/<feature_name>.patch` from the project root. Build outputs normally live under `llama.cpp/build/bin/`.

## Patch workflow

- Keep feature changes in patch files, never as feature commits inside `llama.cpp`.
- Develop patch changes in a disposable checkout of the pinned base. Apply any dependencies first, then the feature being edited. Export only that feature's diff against its dependency baseline, including new files and binary changes (`git diff --binary` with an appropriately prepared temporary index).
- Update the patch file and run `./configure.py --all` or `--enable <complete feature list>` to apply it. The manager uses saved patch contents to reverse the previous version safely.
- Direct edits in the managed checkout cause the selector to refuse switching. Preserve user edits; do not bypass this with reset or clean.
- Keep `.patch-state/` while patches are active. Disable patches before changing upstream revisions or using stash on the managed checkout. Do not switch patches during builds or inference.
- When adding a patch, declare dependencies and place it after them in `series.json`. Verify enabled, disabled, and dependent combinations.
- To update upstream, disable patches, update the submodule checkout, port and validate patches, then update both the catalog base and parent gitlink. Do not update the pin incidentally.

Interactive controls: arrows navigate, Space toggles, typing filters, Ctrl+A selects all, Ctrl+N selects none, Enter applies, Esc cancels. Dependencies toggle automatically. CLI `--enable` requires the complete selection explicitly.

## Features and implementation details

- `turboquant`: experimental CPU 2/3/4-bit KV cache and TQ3_1S/TQ4_1S weights.
- `turboquant_vulkan`: depends on `turboquant`; accelerates turbo4 KV cache and attention with WHT rotation on Vulkan. Do not assume other TurboQuant formats have GPU support.
- `moe_expert_cache`: optional device-resident MoE expert slices, configured in MiB with `--moe-expert-cache`; default 0 disables it. Preserve host-transfer fallback and handle entries evicted within a batch.
- Preserve upstream quantization type IDs when adding formats. WHT rotation must be handled consistently in quantization, attention, and test comparisons. Quantization test buffers must use the actual dot-product input type's row size.

## Verification

Build feature changes using upstream CMake:

```sh
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build -j
ctest --test-dir llama.cpp/build -R 'test-turbo-quant|test-arg-parser|test-quantize-fns' --output-on-failure
```

Use a separate build directory with `-DGGML_VULKAN=ON` for Vulkan changes. Run relevant `test-backend-ops` cases for SET_ROWS and FLASH_ATTN_EXT on the affected backend. Check the executable's help for filtering options. Model smoke tests should use canonical cache names, e.g. `-fa on -ctk turbo4_0 -ctv turbo4_0`.

Test patch changes with an all/none round trip in a disposable checkout or a managed checkout free of user edits, then restore the original selection. Disabling all patches should leave upstream clean. A dense-model smoke test does not validate MoE cache hits; measure performance and quality on relevant workloads before making claims.

## Conventions

Keep documentation about current behavior and usage. Do not add migration documents or backward-compatibility narratives. Prefer small changes and existing test infrastructure. Do not commit, push, or contact upstream maintainers unless the user requests it.
