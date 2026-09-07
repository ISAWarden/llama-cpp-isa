---
name: compile-verifier
description: Verify llama-cpp-isa changes through its GitHub Actions release builds, inspect failed job logs, fix patch or workflow compilation errors, and retry a bounded verification loop. Use when asked to run remote compile verification or diagnose failed release builds.
---

# Compile Verifier

Read the root `AGENTS.md`, `README.md`, and `patches/series.json`. The parent repository owns release automation; `llama.cpp/` is the pinned official submodule with selectable patches. Do not read agent instructions inside the submodule.

## Scope and access

Use existing session authorization. A request to push changes and run the verification loop authorizes those commits, pushes, and workflow dispatches; merely installing this skill or asking for log diagnosis does not. Do not infer permission to publish a release from compile verification. Preserve unrelated edits and stage only the intended parent-repository files.

Discover the repository and branch rather than assuming an owner:

```sh
git status --short
./configure.py --list
git remote -v
git branch --show-current
gh repo view --json nameWithOwner,url
gh auth status
```

Use configured Git authentication. If the user supplied a specific deploy-key path, use it through `GIT_SSH_COMMAND` with `IdentitiesOnly=yes`; keep private keys outside the repository and never print them. Do not replace working credentials or disable host-key verification. If required authorization or credentials are absent, complete local work and report what is needed for the remote step.

## Local verification and fixes

- Source fixes belong in `patches/*.patch`. Develop in a disposable checkout of `series.json`'s base, apply dependencies first, and export only the feature diff against its dependency baseline with a temporary index and `git diff --binary`, including added files. Never make feature commits inside `llama.cpp/` or change the upstream pin incidentally.
- Apply revised patches with `./configure.py --all` or `--enable <complete selection>`. If the managed checkout has user edits, use an isolated checkout; do not reset or clean it. Preserve the original selection and verify the all/none round trip in isolation.
- Build relevant targets using `cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release`, then `cmake --build llama.cpp/build --parallel <appropriate job count>`. For Vulkan failures, use a separate build directory with `-DGGML_VULKAN=ON`.
- Run the relevant `ctest --test-dir <build-dir> -R 'test-turbo-quant|test-arg-parser|test-quantize-fns' --output-on-failure`. Vulkan correctness changes also need affected SET_ROWS and FLASH_ATTN_EXT backend tests where hardware is available. Compilation alone does not validate GPU execution, MoE hits, model quality, or performance.
- `.github/workflows/release-builds.yml` is generated from pinned upstream build recipes. Change `.github/scripts/generate-build-workflow.py` for project adaptations, then regenerate; do not hand-edit the generated file. Run `python3 .github/scripts/generate-build-workflow.py --check` (requires PyYAML). Release packaging also reuses upstream's merge scripts and platform labels.
- Run `git diff --check` and inspect the parent diff before any authorized commit. Applied patches normally make the submodule dirty; stage the patch files, not a new gitlink.

## Push and dispatch

With commit/push authorization, commit only intended parent files and push the current branch. Resolve `$repo`, `$branch`, and `$sha` from the commands above. Avoid logging secrets.

```sh
gh workflow run release.yml --repo "$repo" --ref "$branch" -f create_release=false
gh run list --repo "$repo" --workflow release.yml --commit "$sha" \
  --event workflow_dispatch --json databaseId,headSha,createdAt,url,status,conclusion
```

Record dispatch time and select the new manual run matching the exact pushed SHA, not a concurrent push run. The workflow must exist on the default branch before GitHub permits manual dispatch. If an authorized push to `main`/`master` already triggered Release, monitor that run rather than dispatching duplicate builds; those push runs publish prereleases automatically.

Build-only mode runs preparation, the whole platform matrix, and final packaging, but skips publication. Set `create_release=true` only when publishing was requested. No deploy-key secret is needed by the workflow; its publish job uses `GITHUB_TOKEN`.

## Diagnose and retry

Poll `gh run view <run-id> --repo "$repo" --json status,conclusion,jobs,url` at reasonable intervals while providing progress updates. Inspect failing jobs as they finish; the matrix has `fail-fast: false`. A cancelled or skipped job is not a passing build.

Use `gh run view <run-id> --repo "$repo" --log-failed`, or download one job log with `gh api "repos/$repo/actions/jobs/<job-id>/logs"` to a temporary directory. Search logs for compiler errors, linker failures, shader failures, and the first failing command. Diagnose source errors through the responsible patch, and workflow errors through the generator or parent scripts. Fix the smallest responsible surface and run the closest local check before committing and retrying an authorized loop.

Stop after three fix attempts for the same unresolved failure class, or when remaining failures require missing credentials, runner availability, quota, or an external service change. Do not retry infrastructure failures indefinitely. Preserve completed fixes and report a concrete blocker.

Report the branch, exact SHA, run URL, root causes and fixes, local checks, final workflow conclusion, and any platforms or runtime behavior still unverified. Confirm publication only when the publish job actually succeeded.
