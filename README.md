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
| `emerald_mtp` | Persistent source-fragment speculation from imported text and verified conversations | `--spec-type emerald-mtp --spec-emerald-mtp-file ./emeraldmtp.bin` |

| `hauhaucs_fastmtp` | HauhauCS FastMTP: Qwen3.5 MTP draft-vocabulary trimming and full-vocabulary logits mapping | `./configure.py --enable hauhaucs_fastmtp`; requires an MTP-only model with `d2t` and trimmed `output.weight` |

TurboQuant provides experimental CPU reference implementations and Vulkan acceleration for turbo4/turbo4. Turbo2, turbo3, and TQ weights use CPU implementations. Unsupported operations may fall back to CPU. Check startup logs for the actual placement and backend.

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
  --spec-emerald-mtp-n-min 8 --spec-emerald-mtp-n-max 16 \
  --spec-emerald-mtp-file ./emeraldmtp.bin
```

Pretraining is optional: the server creates a missing database at startup and fills it from prompts and verified replies. Its parent directory must exist and be writable. Existing databases are loaded and validated.

The importer loads the GGUF vocabulary without weights. Each file is tokenized separately with whitespace preserved, no added special tokens, and no interpretation of special-token spellings. Repeat `--input` for multiple files or directories. Traversal is sorted; symlinks, `.git`, binary files, and invalid UTF-8 are skipped and reported. An unreadable selected file fails the import. Repeat `--include` and `--exclude` for relative-path globs: `*` stays within a path component, `**` crosses directories, and `?` matches one character. Exclusions win. Glob-filter skip messages are shown only with `--verbose`; filtered files still count in the skipped-file total.

```sh
llama.cpp/build/bin/pretrain-emerald-mtp -m model.gguf \
  --input ./src --input ./docs --include '**/*.cpp' --include '**/*.md' \
  --exclude '**/generated/**' --output ./emeraldmtp.bin --append
```

An existing output requires explicit `--append`; a failed import does not save partial observations. This tool is the only source-file import interface. File reading and tokenization use up to 8 CPU workers by default; `--threads N` (or `-t N`) selects 1–256 workers, with 1 selecting serial execution. Database insertion stays in sorted file order. Worker lookahead is bounded to twice the worker count and 32 MiB of discovered source bytes; a larger file runs alone. This is not a RAM limit: tokenization needs additional working memory and files may change after discovery. To omit installed Python dependencies, use `--exclude '**/.venv/**'`. Discovery, tokenization/indexing, and saving report progress on stderr, including periodic lines when redirected. The final summary reports selected/imported files, skipped reasons, imported bytes and tokens, n-gram occurrences added, newly imported distinct n-grams, and database totals. The top 10 stored n-grams (each `n-match + 1` tokens) are ranked by combined imported and learned frequency, with escaped text previews capped at 160 bytes. Database totals and rankings include previous data when appending.

`--spec-type emerald-mtp` requires `--spec-emerald-mtp-file PATH`; a missing path is rejected during argument parsing, before model loading or context allocation. The default lookup length is 24 tokens (`--n-match` in the importer). A newly created server database also defaults to 24 tokens. The server and append importer infer it from an existing database; an explicit `--spec-emerald-mtp-n-match` or `--n-match` must agree. Draft lengths default to 8–16 and must satisfy `1 <= n-min <= n-max`; all lengths are limited to 1024. Upstream context, batch, and remaining-output limits still apply. `--spec-type emerald-mtp,ngram-mod` tries EmeraldMTP first and falls through on insufficient matches. Synthetic acceptance options and `tokenizer.*` metadata overrides are rejected.

One context graph and open-addressed hash index serve all server slots. An exact initial lookup resolves hash collisions; drafts then follow cached winning-token and successor-node links. Observations update winners immediately using saturating imported-plus-learned counts, with lower token ID breaking ties. Text prompts are observed once when ready for generation; committed output tokens, including the final token, are learned as the server processes them. Rejected drafts and checkpoint/decode replay do not update the database. Slot release clears sequence tracking. Learning is disabled for multimodal prompts. Tokens that trigger a stop condition are included; later tokens in the verified batch are excluded.

The little-endian `EGRAPH01` database stores aligned sections for packed token ranges, context nodes, continuation counts, and a persisted tagged hash index. Context nodes cache the winning token and successor ID. It retains 64-bit offsets/counts and full tokenizer GGUF metadata as a collision-free compatibility identity, including vocabulary, merges, special-token settings, and other `tokenizer.*` fields. See the [context graph format](docs/emerald_mtp.md) for the layout and lookup rules. Checksummed append transactions preserve learned observations between snapshots. Recovery discards an incomplete final journal transaction; malformed or incompatible databases are rejected. An OS writer lock on the adjacent `.lock` file remains held throughout server/importer lifetime. Stop the server before appending with the importer.

The server worker flushes at one-second intervals and drains at orderly shutdown. An abrupt exit can lose observations not yet flushed. A persistence failure is reported and pauses learning while existing lookups remain available. Compaction atomically replaces the database and temporarily requires space for a second copy. Journal writes, snapshot packing, checksumming, disk sync, and snapshot replacement run outside the database mutex. Snapshot generation copying, learning, and retention still take that mutex and can delay lookups; compaction needs extra RAM for the captured graph and serialization buffers.

`--max-size-gb` (importer) and `--spec-emerald-mtp-max-size-gb` (server) limit compacted file contents, using decimal GB; `0` means unlimited. Retention removes the least recently observed learned entries first and preserves imported counts. Imports whose protected contents exceed the limit fail. Learning pauses when the limit leaves no room for learned entries. Compaction bounds journal growth without forcing a snapshot on every flush merely because a limit is configured; the limit does not bound RAM or temporary disk usage.

Build and run `test-emerald-mtp` and `test-arg-parser`. The opt-in `test-emerald-mtp-bench [corpus_tokens] [queries]` target measures exact hits, misses, and contexts with many alternatives. Opt-in Python importer/server tests under `llama.cpp/tests/test-emerald-mtp-*.py` require a local GGUF and accept `--help`. See [validation results](docs/emerald-mtp-validation.md) for measured performance, corpus details, and validation limits.

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

The matrix follows upstream's release recipes: macOS ARM64/Intel, iOS XCFramework, Linux x64/ARM64 CPU and Vulkan, Linux x64 ROCm/OpenVINO/SYCL, Android ARM64, Windows x64/ARM64 CPU, Windows CUDA/Vulkan/OpenCL/ROCm/OpenVINO/SYCL, and the UI. Upstream's custom s390x runner and disabled openEuler/KleidiAI builds are omitted. GPU jobs compile on hosted runners; they do not establish GPU runtime correctness or performance. All TurboQuant formats remain experimental, and only turbo4 has Vulkan acceleration.

A Linux preparation job uses `configure.py --all`, archives the exact patched tree including added files, and checks that `--none` restores pristine upstream. Every platform consumes that same archive. The release includes upstream-style download links, runtime packages, `SHA256SUMS`, and a manifest with the parent commit, upstream base, enabled features, and patch hashes. Publication uses a draft until all uploads complete. An already published release is left unchanged on retries.

Build recipes and dependency setup actions come from the pinned `llama.cpp/.github/` files. GitHub requires reusable workflows in this parent repository, so `.github/workflows/release-builds.yml` is generated, with a drift check before builds. After updating upstream or changing the adaptation script:

```sh
python3 -m pip install PyYAML==6.0.2
python3 .github/scripts/generate-build-workflow.py
python3 .github/scripts/generate-build-workflow.py --check
```

The matrix downloads substantial SDKs and uses GitHub Actions runner time. GitHub Actions must be enabled and repository policy must allow the publish job's `contents: write` permission; no custom release secret is required. Manual dispatch becomes available once the workflow is on the default branch.

The repository skill at `.agents/skills/compile-verifier/SKILL.md` diagnoses these builds and carries fixes through the patch workflow. It defaults manual verification runs to `create_release=false` and uses existing session authorization for commits and pushes.
