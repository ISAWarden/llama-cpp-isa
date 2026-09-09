# Integration lessons and useful patch examples

These are routing clues, not frozen APIs. Search symbols in the current pinned source and the current patch files. The root AGENTS.md owns the general source map and project-wide invariants.

## Find a relevant example

| Change | Existing patch and useful surface |
| --- | --- |
| CPU quantization format / KV cache | `turboquant.patch`: type registration, quantize/dequantize and dot products, CPU attention, argument names, tests |
| Dependent GPU implementation | `turboquant_vulkan.patch`: depends on `turboquant`; host pipeline selection, shader generation, SET_ROWS, flash attention and rotation |
| Runtime option reaching backend state | `moe_expert_cache.patch`: common arguments/parameters → context parameters → backend cache API; fallback and eviction behavior |
| Narrow model-graph optimization | `hauhaucs_fastmtp.patch`: draft-vocabulary trimming and `d2t` mapping back into the full logits vocabulary |
| Shared common component, executable and server lifecycle | `emerald_mtp.patch`: common library, tool CMake/install, server integration, persistent database, C++ and opt-in Python tests |

Start with `rg '^diff --git' patches/<name>.patch`, then inspect relevant hunks and symbols. Avoid loading an entire large patch when a few touched paths answer the question.

## Shared registration surfaces

Changes to common arguments or parameters often need both parsing and propagation to the target context/backend; a help entry alone proves neither. For a new speculative type, inspect the enum/count assertion, name-to-type and type-to-name mappings, draft limits, implementation priority, and factory dispatch. Validate required cross-option combinations after all arguments are parsed and before model loading or large context allocation; retain defensive initialization checks. A missing model path is a useful test sentinel: the missing-parameter error must win without attempting to load the model. Help/completion should remain available for incomplete configurations. Common option visibility is scoped by `.set_examples(...)`; expose a flag only to tools that initialize and support it.

CMake is a common patch collision point. During EmeraldMTP, adding tests at EOF conflicted with TurboQuant's EOF additions. Prefer a stable nearby registration block or adjust hunk placement while preserving normal context; do not add a fake dependency or globally reduce patch context to hide the conflict. Check existing `target_compile_features` before adding a redundant language requirement. New tools need normal tools registration, executable naming, links, and installation, not just a compilable source file.

## Speculation, server state and persistence

A no-draft-model speculator may skip draft-model initialization entirely. Obtain its target vocabulary/model configuration from the actual server initialization path rather than assuming `draft.ctx_tgt` is populated. Inspect initialization catch blocks: upstream may log an optional-speculator failure and continue, whereas a requested mode requiring a database must fail startup if that database is absent or incompatible.

Learn only at request/committed-token boundaries, not from decode batches. Verification can contain rejected drafts, replayed tokens and tokens after the request's stop condition. Ordinary sampling and the final reply token also need observation. Separate learning hooks from existing speculator `begin`/accept callbacks when their lifecycle differs. Test slot reuse, concurrent slots, prompt reuse, cancellation, stop conditions, context shifts and restarts with independent counts where possible.

A dense model does not exercise recurrent checkpoint restoration. EmeraldMTP's Qwen3.5 test deliberately imports an incorrect continuation, confirms rejected proposals and actual checkpoint restores in logs, and checks both greedy parity and exact persisted counts. A grammar-constrained request alone may only cause lookup misses; require evidence of rejection when rejection handling is the test's purpose.

For persistence work, validate complete/incomplete journal transactions separately, malformed lengths/offsets with valid checksums, writer lifetime locking, atomic replacement, and write failure while inference continues. Avoid destructor auto-save that commits a partially failed import. Apply retention when reopening under a smaller limit, even without new observations. A background worker can still stall inference if disk work holds a shared lookup mutex; measure that contention rather than assuming asynchronous means free.

Fingerprint effective tokenizer configuration, not just token count or model filename. If import cannot reproduce tokenizer metadata overrides, reject them explicitly. Keep imported and learned provenance separate when eviction must preserve source data.

## Kernels and performance evidence

For TurboQuant-related changes, preserve upstream type IDs, rotate WHT inputs consistently in reference comparisons, and size quantization test buffers for the actual dot-product input type. Vulkan support for turbo4 does not imply support for every TurboQuant type. Test affected backend operations, not just dense generation. An MoE cache change needs actual cache hits and a workload that transfers expert weights; preserve fallback and entries evicted within a batch.

Use a separately built pristine baseline at the same pin. Match hardware, model/hash, backend, compiler/build flags, threads, context, batching, flash attention, sampling and grammar settings. Distinguish first requests from repeated/learned requests and separate matching fragments from unrelated text. Avoid benchmarking concurrently with your own builds or corpus indexing. Do not stop another running server merely to improve benchmark conditions; report relevant environmental limits.

Report throughput and latency alongside acceptance, lookup overhead, indexing speed, database size and peak memory when relevant. Report unique bytes as well as total input bytes: EmeraldMTP's approximately 1 GB import repeated about 24 MB of project source, so it is not evidence for a 1 GB unique index. Scale claims to the actual tested corpus and backend. See the parent `docs/emerald-mtp-validation.md` for the concrete experiment and reproduction commands when working on that feature.
