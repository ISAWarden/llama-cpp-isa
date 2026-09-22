# EmeraldMTP drafting validation

## Mode selection validation (2026-09-11)

Regular drafting defaults to an 8–16-token range. `--spec-emerald-mtp-n-auto` selects automatic drafting and rejects either explicit manual length flag, including default values and either argument order.

The database and argument-parser tests passed in independent-feature and all-six-feature CPU builds. Checks cover frequency winners and ties, minimum-length suppression, manual budgets above 16, automatic lookup, mode-dependent allocation limits, invalid ranges, and conflicting flags. Server smoke tests using Qwen2.5-Coder-1.5B Q8_0 matched pristine-upstream greedy tokens with accepted drafts in default regular mode, explicit 3–32 regular mode, and automatic mode. Mixed flags failed before loading a deliberately nonexistent model. Disposable selector round trips returned upstream clean; the managed checkout remained untouched because its server is running.

Logs and smoke results are retained under `/tmp/emerald-modes.0TWKE3YE/`. The performance measurements below cover automatic drafting from the previous validation run; no new performance claims are made for restoring mode selection.

## Automatic drafting validation (2026-09-10)

Local validation on 2026-09-10 used the pinned upstream `5202104b59ada9005db079eea43882a2b7bf5802`, GCC 14.2.0, Release CPU builds with `GGML_NATIVE=OFF`, and an AMD Ryzen AI 9 HX 370. An existing user server remained running; its load was not controlled. No agent builds, imports, or other inference runs overlapped the timed requests or lookup benchmark. These are local experimental measurements, not deployment guarantees.

## Correctness

- The server, importer, database tests, and argument-parser tests built with EmeraldMTP alone and with all six selectable patches enabled in CPU builds. Both focused test suites passed in both configurations.
- An independent variable-length continuation oracle matched drafts over 1,200 randomized observation rounds. Tests cover immediate single-token eligibility, permanent ambiguity, longer-context recovery, partial drafts, cycles, runtime budgets, context depths 1 and 1024, and slot learning hooks.
- Retention and reload checks preserve first-continuation witnesses and conflicts after frequency eviction. A smaller reopening limit cannot discard witnesses from journal history. Capacity exhaustion and persistence failure disable automatic drafting across restart.
- Snapshot and journal checks cover malformed fields, interrupted tails, tokenizer mismatch, concurrent observation/flush/draft calls, and exact frequency accounting. AddressSanitizer and UndefinedBehaviorSanitizer passed with the database and C++ test source instrumented; the linked upstream libraries were not instrumented.
- The real-tokenizer importer suite passed, including deterministic serial/two-worker/eight-worker imports and appends, filtering, failed-import preservation, and size limits.
- The real-model server suite passed greedy token parity against pristine upstream, stochastic grammar constraints, deliberately rejected drafts, write failure, concurrent slots, prompt reuse, final tokens, stop strings, context shifts, cancellation, restart, and flushed-data recovery after process interruption. An independent Python decoder checked both learned frequency counts and permanent continuation witnesses.
- Feature-only and all-feature selector round trips returned the disposable verification checkout to pristine upstream. The managed checkout and running user server were left unchanged.
- Hybrid/recurrent model checkpoint verification and GPU runtime verification were not run for this revision.

The automatic measurements below use `--spec-emerald-mtp-n-auto`. Regular frequency-based drafting is now the default; manual length flags and auto are mutually exclusive.

## Model measurements

Model: Qwen2.5-Coder-1.5B Q8_0, SHA-256 `29871c94d15727a6e243f79a37113d4ae625a6215b5e800bf41a23af2da32832`. All compared servers used four CPU threads, context 2048, two slots, flash attention on, 96 requested output tokens, temperature 0, seed 123, and identical request settings. Each server received an eight-token warmup before measured requests.

The matching prompt asks for C++ binary search and has an imported upstream-generated continuation. The unrelated prompt asks about Saturn's rings. Each prompt was requested three times, serially. “First” means its first request after warmup; “repeat” is the mean of the next two requests, after learning. The previous EmeraldMTP baseline uses `n-min=3`, `n-max=16`, and `n-match=24`; auto uses maximum context depth 24 and its internal cap of 16. Both imported the same source text into fresh databases.

| Mode | Prompt | First tokens/s | Repeat tokens/s | First wall seconds | Repeat wall seconds | Accepted / drafted, all 3 requests |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Upstream before | matching | 17.18 | 17.81 | 5.779 | 5.614 | — |
| Upstream before | unrelated | 17.57 | 14.28 | 5.578 | 6.845 | — |
| Automatic EmeraldMTP | matching | 43.71 | 54.66 | 2.607 | 2.122 | 267 / 267 |
| Automatic EmeraldMTP | unrelated | 9.42 | 63.38 | 10.290 | 1.707 | 186 / 492 |
| Previous EmeraldMTP, 3–16 | matching | 62.79 | 66.95 | 1.820 | 1.708 | 267 / 267 |
| Previous EmeraldMTP, 3–16 | unrelated | 15.99 | 51.79 | 6.150 | 2.040 | 168 / 168 |
| Upstream after | matching | 18.67 | 17.24 | 5.409 | 5.898 | — |
| Upstream after | unrelated | 18.11 | 18.56 | 5.419 | 5.343 | — |

The mean no-speculation decode rate was 16.49 tokens/s before and 18.07 after (+9.6% drift). Background load was uncontrolled.

Upstream was measured before and after the two speculative modes to expose timing drift. All implementations produced matching greedy token sequences for these prompts. Automatic drafting can accelerate learned or imported continuations, but aggressive guesses from one occurrence can slow an unrelated first reply. These fixtures do not establish general acceptance rates or quality/performance on larger models.

The previous patch used for comparison has SHA-256 `e70e424d9fab908e4e0cd503a00b30dd1628190f0ad5b07096420a7f6f85769e`.

## Lookup and storage measurements

One run per implementation used `test-emerald-mtp-bench 200000 20000`: seed 42, 200,000 random corpus tokens, maximum depth 24, and 1,024 alternatives sharing a context. Each lookup case has 1,000 warmup queries and 20,000 measured queries; every result is checked. Learning is inactive during timed lookups. The auto miss changes the newest token to an absent ID, and ambiguous fanout returns no draft; the previous fixed-context benchmark changes the oldest token for misses and chooses a frequency winner for fanout. Thus the two fanout cases measure different decisions.

| Implementation | File bytes | Index ms | Save ms | Load ms | Peak process RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Previous EmeraldMTP | 18,452,544 | 34.8 | 109.4 | 59.4 | 79.6 |
| Automatic EmeraldMTP | 94,951,936 | 738.7 | 314.2 | 1659.9 | 431.9 |

| Implementation | Lookup | p50 ns | p95 ns | p99 ns |
| --- | --- | ---: | ---: | ---: |
| Previous EmeraldMTP | hit16 | 110 | 320 | 421 |
| Previous EmeraldMTP | miss | 60 | 170 | 231 |
| Previous EmeraldMTP | fanout1024 | 50 | 51 | 51 |
| Automatic EmeraldMTP | hit16 | 3096 | 5069 | 5971 |
| Automatic EmeraldMTP | miss | 40 | 50 | 51 |
| Automatic EmeraldMTP | fanout1024 | 171 | 181 | 181 |

The permanent trie adds substantial indexing, snapshot, and memory cost because it retains contexts of every length, including evicted frequency history. The compacted file limit does not bound RAM. Larger unique corpora need separate capacity measurements; these synthetic results are not an inference-speed prediction.

## Reproduction

Build pristine upstream and the feature separately at the pinned base, with matching compiler and CMake settings. The model suite uses a fresh output directory:

```sh
ctest --test-dir llama.cpp/build -R '^(test-emerald-mtp|test-arg-parser)$' --output-on-failure
python3 llama.cpp/tests/test-emerald-mtp-import.py \
  --importer llama.cpp/build/bin/pretrain-emerald-mtp --model model.gguf
python3 llama.cpp/tests/test-emerald-mtp-server.py \
  --server llama.cpp/build/bin/llama-server --upstream /path/to/pristine/llama-server \
  --importer llama.cpp/build/bin/pretrain-emerald-mtp --model model.gguf \
  --output-dir /tmp/emerald-auto-validation
llama.cpp/build/bin/test-emerald-mtp-bench 200000 20000
```

Local logs, comparison JSON, and helper commands for this run are retained under `/tmp/emerald-auto.MeS0BLXS/`.
