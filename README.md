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

| Patch | What it adds | Usage |
| --- | --- | --- |
| `turboquant` | Experimental CPU implementations of 2/3/4-bit KV cache and TQ3_1S/TQ4_1S weight quantization | `-fa on -ctk turbo4_0 -ctv turbo4_0` |
| `turboquant_vulkan` | Vulkan turbo4 KV storage, attention, and WHT rotation; requires `turboquant` | Build with Vulkan, use `-ctk turbo4_0 -ctv turbo4_0` |
| `moe_expert_cache` | Device-resident cache of MoE expert slices to reduce repeated host transfers | `--moe-expert-cache 1024` (MiB per participating backend; default 0 disables it) |

TurboQuant provides experimental CPU reference implementations and Vulkan acceleration for turbo4/turbo4. Turbo2, turbo3, and TQ weights use CPU implementations. Unsupported operations may fall back to CPU. Check startup logs for the actual placement and backend.

The MoE cache helps only workloads that transfer CPU-resident expert weights to a device. It needs additional device memory and is not a substitute for full expert offload. It falls back to host transfers if a cache allocation or copy cannot be used. Performance and long-context model quality require workload-specific evaluation.

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
