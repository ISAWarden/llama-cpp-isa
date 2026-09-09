---
name: patch-maker
description: Create or revise selectable llama-cpp-isa feature patches, including dependency baselines, isolated development, binary-capable exports, catalog registration, and local verification. Use for patch implementation and porting; use compile-verifier for requested remote release-build verification.
---

# Patch Maker

Deliver the feature in `patches/<feature_name>.patch`, with its catalog entry, current usage documentation, and evidence appropriate to the change. The patch file is the implementation source of truth.

## Establish the baseline

Read the root `AGENTS.md`, `README.md`, and `patches/series.json`; the root instruction file also governs disposable upstream checkouts. Do not read upstream or nested agent instructions. Get the current pin and feature order from the catalog rather than copying a revision from this skill.

Start with `git status --short` and `./configure.py --list`. Record the original selection and existing parent changes. A dirty submodule is normal when patches are selected. Inspect the relevant patch surfaces with `rg '^diff --git' patches/<feature>.patch` before searching upstream code.

Check whether a build or inference process is using the checkout before switching it. A server can run as `./build/bin/llama-server`; its executable arguments alone do not identify its checkout. On Linux, inspect `/proc/<pid>/cwd` and `/proc/<pid>/exe`; use platform equivalents elsewhere. If the managed checkout is busy or has user edits, do all development and round trips in disposable checkouts. Leave the running process and original selection intact; no confirmation is needed to continue in isolation.

## Develop and export

Use [references/workflow.md](references/workflow.md) for the disposable-checkout commands and selector round trip. Develop at the pinned base with only the feature's transitive dependencies applied, followed by the existing feature patch if editing one. Dependency order follows the catalog. Keep the dependency patch versions stable during development; if they change, reconcile the checkout before exporting.

Export only the feature's difference from that dependency baseline. A diff against upstream HEAD would include dependencies; a plain worktree diff would miss added files. The bundled exporter handles a temporary index, binary/new/deleted files, whitespace checks, omitted edits, and reconstruction verification:

```sh
python3 .agents/skills/patch-maker/scripts/export_patch.py \
  --project . --checkout "$patch_work/llama.cpp" --feature my_feature \
  --files common/example.cpp common/example.h tests/test-example.cpp
```

For a new dependent feature, repeat `--requires dependency_name`. For an existing feature, dependencies come from its catalog entry. Explicitly listed ignored files are included too, allowing intentional binary assets; do not list build outputs. List actual files explicitly, including deleted paths; use `git status --short` and `git ls-files --others --exclude-standard` to review the list. The helper intentionally refuses staged changes, omitted non-ignored files, and the managed checkout. It replaces only the named patch after successful checks; it does not register, apply, commit, or push it. Run `--help` for its interface. After modifying the helper, run `python3 .agents/skills/patch-maker/scripts/test_export_patch.py --project .` for isolated export regression checks.

Review the export's touched files and diff. Keep the upstream pin and gitlink unchanged unless updating upstream is the user's task. Register a new feature after its dependencies in `series.json`; an independent feature needs no `requires` entry. Update README usage with actual defaults, supported backends, and experimental limits.

## Verify and finish

Apply the exported patch through a copied or eligible managed `configure.py`, not by editing the managed source. Test the feature with its dependency closure and with all maintained patches. Build and run relevant targets before switching a checkout; disabling all must leave upstream clean. Restore the original selection in every managed checkout used. Selector refusals preserve evidence: inspect the recorded selection and local diff instead of deleting `.patch-state/`, resetting, cleaning, or repeatedly forcing the same failed operation.

Choose checks based on changed behavior. Read [references/integration-lessons.md](references/integration-lessons.md) when changing common/server plumbing, speculation, kernels, persistence, tools, or performance-sensitive code. It identifies useful existing patches and lessons that prevent misleading validation. Do not run unrelated model or backend suites just because another feature needed them.

Verify the final exported revision after fixes; an earlier passing build is not evidence for later relevant edits. Check `git diff --check`, catalog order, unchanged pin, and agreement between the exported patch and tested source. Report what changed, exact tested configurations, measured results and their limits, and the final selection. Preserve unrelated parent changes. No feature commits inside upstream; commit/push/publication require the user's request. Remote build verification, when requested, uses the repository's sibling `compile-verifier` skill.
