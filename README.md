# llama-cpp-isa

The official [llama.cpp](https://github.com/ggml-org/llama.cpp) repository as a Git submodule plus selectable local feature patches. Feature code lives in `patches/*.patch`; applying it changes the checkout's working files, never its commits.

```sh
git clone --recurse-submodules <this-repository-url>
cd llama-cpp-isa
./configure.py
```

For an existing clone with an uninitialized submodule, run `git submodule update --init --recursive`.

Requires Python 3 (with curses) and Git on Linux/macOS. The interactive selector supports:

- **↑/↓** to navigate and **Space** to toggle the highlighted patch.
- Type to search names and descriptions; **Backspace** deletes a character and **Ctrl+U** clears the search.
- **Ctrl+A** selects all patches; **Ctrl+N** selects none, including patches hidden by search.
- **Enter** applies the selection; **Esc** cancels without applying it.

The menu automatically selects dependencies and disables dependent features when needed. With `--enable`, supply the complete selection explicitly.

For scripts:

```sh
./configure.py --list
./configure.py --all
./configure.py --enable turboquant turboquant_vulkan  # exact selection
./configure.py --enable moe_expert_cache
./configure.py --none                               # back to upstream
```

`--all` enables the complete maintained patch set, including experimental features.

## Build normally

After selecting patches, use upstream's normal build process:

```sh
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build -j
```

For Vulkan, add `-DGGML_VULKAN=ON` when configuring CMake. The selector does not select a build backend or change your CMake settings. Rebuild after changing patches; do not switch patches while a build or inference process is running.

## Available patches

| Patch | What it adds | Usage |
| --- | --- | --- |
| `turboquant` | Experimental CPU implementations of 2/3/4-bit KV cache and TQ3_1S/TQ4_1S weight quantization | `-fa on -ctk turbo4_0 -ctv turbo4_0` |
| `turboquant_vulkan` | Vulkan turbo4 KV storage, scalar/CM1 attention, and scaled WHT rotation; requires `turboquant` | Build with Vulkan, use `-ctk turbo4_0 -ctv turbo4_0` |
| `turboquant_metal` | Metal turbo2/3/4 KV writes, turbo4 attention and native WHT; requires `turboquant` | Build with Metal, use `-fa on -ctk turbo4_0 -ctv turbo4_0` |
| `moe_expert_cache` | Device-resident cache of MoE expert slices to reduce repeated host transfers | `--moe-expert-cache 1024` (MiB per participating backend; default 0 disables it) |
| `emerald_mtp` | Persistent source-fragment speculation from imported text and verified conversations | `--spec-type emerald-mtp --spec-emerald-mtp-file ./emeraldmtp.bin` |
| `hauhaucs_fastmtp` | HauhauCS FastMTP: Qwen3.5 MTP draft-vocabulary trimming and full-vocabulary logits mapping | `./configure.py --enable hauhaucs_fastmtp`; requires an MTP-only model with `d2t` and trimmed `output.weight` |

TurboQuant provides experimental CPU reference implementations and optional Vulkan and Metal acceleration. Vulkan accelerates turbo4/turbo4 with modern scalar attention and cooperative-matrix (CM1) prefill where device and shape checks permit. A single effective attention row retains the scalar path; grouped-query decode may use CM1. WHT supports 32/64/128-element groups and optional scales; subgroup shuffles accelerate supported devices, with a shared-memory fallback. With `turboquant_metal`, Metal stores turbo2/3/4 caches using 128-element rotation groups and accelerates turbo4/turbo4 attention with equal padded K/V head sizes of 128, 256, or 512. The Metal patch includes native standalone F32 WHT for 32/64/128-element groups and optional scales. It has been run successfully on a Mac Studio. Turbo2/3 attention, mixed cache formats, and other head shapes use CPU fallback. TQ weights use CPU implementations. When a device cannot write the requested TurboQuant cache types, that layer's K/V cache is allocated on CPU. Check startup logs for actual placement; CPU fallback can reduce performance.

CPU TurboQuant dot products use bounded block scratch instead of allocating per key row. SYCL and RPC conservatively reject unsupported TurboQuant operations. HIP/CUDA/MUSA do not yet have a native TurboQuant cache pipeline; AMD ROCm can therefore still place these caches on CPU. See [validation and benchmark limits](docs/turboquant-validation.md) for measured operator results and backend-specific status. `llama-bench` accepts canonical TurboQuant cache names.

The release workflow compiles and links the affected shaders on its Apple Silicon runner as well as building the host code. For operation comparisons on a Mac, build `test-backend-ops` and run `test-backend-ops -b Metal -o SET_ROWS -p 'type_dst=turbo'` and `test-backend-ops -b Metal -o FLASH_ATTN_EXT -p 'type_K=turbo4_0'` (check `--help` for your build's filtering options).

The MoE cache helps only workloads that transfer CPU-resident expert weights to a device. It needs additional device memory and is not a substitute for full expert offload. It falls back to host transfers if a cache allocation or copy cannot be used. Performance and long-context model quality require workload-specific evaluation.

## EmeraldMTP source-fragment speculation

`emerald_mtp` is an independent experimental patch. It proposes continuations from exact token fragments in imported text and learned conversations. The target model verifies proposals through upstream speculative sampling, including grammar constraints. It does not add files to the model context or train model weights.

```sh
./configure.py --enable emerald_mtp
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build -j --target llama-server pretrain-emerald-mtp

llama.cpp/build/bin/pretrain-emerald-mtp \
  -m model.gguf --input ./project --output ./emeraldmtp.bin

llama.cpp/build/bin/llama-server -m model.gguf \
  --spec-type emerald-mtp \
  --spec-emerald-mtp-n-auto \
  --spec-emerald-mtp-file ./emeraldmtp.bin
```

Pretraining is optional: the server creates a missing database at startup and fills it from prompts and verified replies. Its parent directory must exist and be writable.

See [emerald_mtp.md](docs/emerald_mtp.md) for documentation on drafting, learning, and database storage, and [validation results](docs/emerald-mtp-validation.md) for measured performance and validation limits.

## Keeping local work safe

The selector refuses to switch if managed files differ from the recorded selection, if anything is staged inside `llama.cpp`, or if an untracked file would be overwritten. Unrelated untracked files and build directories are preserved. There is no `reset --hard`, `clean`, cherry-pick, or commit step.

Keep `.patch-state/` until you have disabled all patches. It stores the exact applied patch contents so an edited patch file can be replaced or disabled correctly. A lock serializes selector invocations, and a pending selection allows recovery after interruption around application. If interrupted files match neither selection, the script stops for manual recovery.

Before using another Git tool to edit, stash, or update `llama.cpp`, disable patches. If you already made local edits, save them outside the checkout and restore the managed files to the active selection before switching. Plain `git stash` does not include patch-created untracked files by default.

## Maintaining patches

The ordered catalog and exact upstream revision are in `patches/series.json`. The submodule pointer must match its `base`. To add a feature:

1. Start with `./configure.py --none` and a clean checkout.
2. Develop the change in a disposable checkout of the pinned upstream revision. For a dependent feature, apply its dependencies there first.
3. Export a binary-capable Git diff as `patches/<feature_name>.patch`. Include added files (plain `git diff` omits untracked files). Do not commit feature changes inside the upstream checkout.
4. Add its name, description, and any `requires` entries to `series.json`, in dependency order.
5. Test it individually, with its dependencies, and with `--all`. Verify `--none` returns a clean checkout.

To update upstream, first disable all patches, fetch and check out the desired official revision, then update `series.json`'s `base`. Rebase the patch files in a disposable checkout, run the tests/builds, and update the parent repository's submodule pointer with `git add llama.cpp`. An upstream update can require source changes; the selector deliberately refuses to guess at conflicts.

```sh
ctest --test-dir llama.cpp/build -R test-turbo-quant --output-on-failure
```

## GitHub release builds

The **Release** workflow builds all maintained patches on the pinned upstream base. Pushes to `main` or `master` that change the submodule, patches, patch manager, or release automation publish an `isa-<run-number>-<commit>` prerelease after every platform build and packaging job succeeds. In **Actions → Release → Run workflow**, leave `create_release` unchecked for compile verification, or check it to publish. Build-only runs retain a complete `release-bundle` artifact for seven days.

The matrix follows upstream's release recipes: macOS ARM64/Intel, iOS XCFramework, Linux x64/ARM64 CPU and Vulkan, Linux x64 ROCm/OpenVINO/SYCL, Linux x64/ARM64 CUDA, Android ARM64, Android/Linux ARM64 Snapdragon, Windows x64/ARM64 CPU, Windows CUDA/Vulkan/OpenCL/ROCm/OpenVINO/SYCL, and the UI. Upstream's custom s390x runner and disabled openEuler/KleidiAI builds are omitted. GPU jobs compile on hosted runners; they do not establish GPU runtime correctness or performance. All TurboQuant formats remain experimental, and only turbo4 has Vulkan acceleration.

A Linux preparation job uses `configure.py --all`, archives the exact patched tree including added files, and checks that `--none` restores pristine upstream. Every platform consumes that same archive. The release includes upstream-style download links, runtime packages, `SHA256SUMS`, and a manifest with the parent commit, upstream base, enabled features, and patch hashes. Publication uses a draft until all uploads complete. An already published release is left unchanged on retries.

Build recipes and dependency setup actions come from the pinned `llama.cpp/.github/` files. GitHub requires reusable workflows in this parent repository, so `.github/workflows/release-builds.yml` is generated, with a drift check before builds. After updating upstream or changing the adaptation script:

```sh
python3 -m pip install PyYAML==6.0.2
python3 .github/scripts/generate-build-workflow.py
python3 .github/scripts/generate-build-workflow.py --check
```

The matrix downloads substantial SDKs and uses GitHub Actions runner time. GitHub Actions must be enabled and repository policy must allow the publish job's `contents: write` permission; no custom release secret is required. Manual dispatch becomes available once the workflow is on the default branch.

The repository skill at `.agents/skills/compile-verifier/SKILL.md` diagnoses these builds and carries fixes through the patch workflow. It defaults manual verification runs to `create_release=false` and uses existing session authorization for commits and pushes.
