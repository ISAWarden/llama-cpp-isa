# Disposable development and selector verification

Commands run from the parent project root unless stated otherwise. Use a new temporary directory per task; never reuse a fixed `/tmp` path from a previous session. `mktemp -d` works on this project's Linux/macOS patch-manager hosts.

## Prepare the feature checkout

```sh
project_root="$PWD"
patch_work=$(mktemp -d -t isa-patch.XXXXXXXX)
patch_base=$(python3 -c 'import json; print(json.load(open("patches/series.json"))["base"])')
git -C llama.cpp worktree add --detach "$patch_work/llama.cpp" "$patch_base"
```

Read the selected feature's `requires` recursively, and apply the dependency closure in catalog order using `git -C "$patch_work/llama.cpp" apply "$project_root/patches/<dependency>.patch"`. Apply its existing feature patch last when editing one. Independent new features start with pristine upstream. Do not apply `--all` as the development baseline: it makes independent export and undeclared-dependency detection harder.

Edit source here without making feature commits. The export helper reconstructs the dependency baseline in a temporary index; neither dependency nor feature changes need to be staged in the real index. Keep scratch scripts, results, models, and notes outside this checkout, and put builds in ignored build directories. The helper refuses omitted untracked files so additions cannot silently disappear from a patch.

The helper does not decide feature scope. If you intentionally remove a dependency-provided file, list that deletion; if you accidentally reverted a dependency, restore it before export. Review the resulting feature diff against the dependency baseline.

## Test the selector independently

After exporting and registering the feature, create a separate selector sandbox. This keeps direct development edits out of selector state and lets a running managed server continue uninterrupted.

```sh
patch_verify=$(mktemp -d -t isa-verify.XXXXXXXX)
mkdir "$patch_verify/patches"
cp configure.py "$patch_verify/configure.py"
cp patches/series.json patches/*.patch "$patch_verify/patches/"
git -C llama.cpp worktree add --detach "$patch_verify/llama.cpp" "$patch_base"
python3 "$patch_verify/configure.py" --enable my_feature
```

For a dependent feature, `--enable` must list its complete transitive dependency closure as well as the feature. The CLI does not auto-add dependencies. Run applicable builds/tests on this selection, then use `--all` and verify coexistence. Copy revised patches/catalog into this sandbox before reapplying through its manager; its saved patch contents reverse previous versions. Do not directly edit the selector-managed sandbox.

```sh
cmake -S "$patch_verify/llama.cpp" -B "$patch_verify/llama.cpp/build" \
  -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=ON
cmake --build "$patch_verify/llama.cpp/build" --parallel 4 --target <relevant-targets>
ctest --test-dir "$patch_verify/llama.cpp/build" -R '<relevant-tests>' --output-on-failure
# After all builds and inference in this sandbox have stopped:
python3 "$patch_verify/configure.py" --all
# Build/test the combined selection, then:
python3 "$patch_verify/configure.py" --none
git -C "$patch_verify/llama.cpp" status --short
```

Choose parallelism for the host; four jobs is only an example. A new test target may require explicit CMake reconfiguration before a multi-target build recognizes it. Use a separate Vulkan build directory with `-DGGML_VULKAN=ON` for Vulkan changes. All patches applied to a CPU build does not establish Vulkan compilation or execution.

A fresh sandbox's original selection is none. An all/none and feature/none round trip should leave no tracked changes or patch-created files; ignored build outputs may remain. If you used the original managed checkout, restore its recorded complete selection. If it stayed busy throughout, leave it untouched and report the new feature as unselected.

Clean up only temporary artifacts you created. Do not force-remove a development worktree containing the sole copy of unexported work. Keep enough build/log information to substantiate the delivered verification.
