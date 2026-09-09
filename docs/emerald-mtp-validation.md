# EmeraldMTP validation

Local validation on 2026-09-08 used the `EGRAPH01` context graph, pinned upstream `5202104b59ada9005db079eea43882a2b7bf5802`, GCC 14.2.0, Release builds, and an AMD Ryzen AI 9 HX 370 on Linux 6.18.49. Model validation and lookup measurements used the CPU backend. The managed Release build with `GGML_VULKAN=ON` also compiled the server, importer, benchmark, and database/argument tests; those two test suites passed with all five patches enabled. This does not establish Vulkan inference performance or deployment performance on other machines.

## Correctness and persistence

- `test-emerald-mtp` and `test-arg-parser` passed with EmeraldMTP selected independently. The database suite also passed with AddressSanitizer and UndefinedBehaviorSanitizer instrumenting the database and test code.
- Randomized drafts matched an independent frequency map over 1,200 observation rounds, including imported and learned counts, winner changes, index growth, multi-token walks, minimum lengths, and reloads.
- Independent-feature and all-feature selector round trips returned a disposable checkout to pristine upstream; the managed checkout retains all five selected features.
- Dedicated checks covered successors appearing after cached misses, changed winners, bounded graph cycles, eviction restoring imported winners, a configured size limit retaining ordinary journal flushes, and persistence of eviction when reopening without a limit. A mostly repeated 5,000-token observation also verified that only novel token ranges allocate storage.
- Concurrent observations, drafts, and explicit/background flushes preserved all 9,000 learned n-gram occurrences after reopening.
- Malformed section offsets, node ranges, successor IDs, cached tokens, continuation offsets, index slots, tags, checksums, and incomplete journal tails were exercised.
- A local Linux linker-wrapped `fsync` check blocked the disk sync of a journal and then a snapshot. In both cases, another thread completed an observation and draft before the blocked sync was released; reopening preserved the expected counts.
- The Python importer suite passed with a real GGUF vocabulary. Serial, two-worker, and eight-worker imports and appends produced byte-identical files. Traversal, filtering, invalid input, size limits, locking, and failed-import preservation were checked.

The real-model server suite used Qwen2.5-Coder-1.5B Q8_0, SHA-256 `29871c94d15727a6e243f79a37113d4ae625a6215b5e800bf41a23af2da32832`. Both the feature and a separately built pristine upstream server used four CPU threads, context 2048, two slots, flash attention on, and identical sampling/request settings. Greedy token parity, stochastic grammar constraints, deliberately rejected proposals, persistence failure, concurrent slots, prompt reuse, final-token accounting, stop strings, context shifts, cancellation, restart, and flushed-data recovery after process interruption passed. An independent Python decoder checked persisted counts. The final token-storage revision additionally matched saved pristine-upstream tokens and exact learned counts through a restart.

A Qwen3.5-2B Q8_0 checkpoint test also passed greedy parity and exact persisted counts after rejected-draft checkpoint replay. The test exercised 70 proposed tokens, of which 21 were accepted. This is a correctness fixture, not an acceptance-rate estimate for general workloads.

## Lookup measurements

Run the opt-in benchmark independently of inference, builds, and indexing jobs:

```sh
cmake --build llama.cpp/build --target test-emerald-mtp-bench
llama.cpp/build/bin/test-emerald-mtp-bench 200000 20000
llama.cpp/build/bin/test-emerald-mtp-bench 1000000 20000
```

The benchmark uses seed 42, random token IDs, `n_match=24`, a synthetic tokenizer identity, and 1,024 additional continuations sharing one context. It reloads the saved graph before timing. Each case uses 1,000 warmup queries and 20,000 measured queries, with every returned token checked. Hit queries request 16 tokens; miss queries change the initial token to an absent ID; the branching case returns one winning token. Learning and persistence are inactive during these lookup timings.

Values below are medians across three runs of each reported percentile, in nanoseconds:

| Corpus tokens | Query | p50 | p95 | p99 |
| --- | --- | ---: | ---: | ---: |
| 200,000 | Exact hit, 16 tokens | 220 | 721 | 1,262 |
| 200,000 | Miss | 161 | 371 | 621 |
| 200,000 | Context with 1,024 alternatives | 60 | 61 | 71 |
| 1,000,000 | Exact hit, 16 tokens | 401 | 732 | 1,222 |
| 1,000,000 | Miss | 170 | 380 | 651 |
| 1,000,000 | Context with 1,024 alternatives | 60 | 61 | 61 |

| Corpus tokens | Compacted file | Indexing | Snapshot save | Validated reload | Peak process RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 200,000 | 18,452,544 bytes | 66.1 ms | 162.7 ms | 78.6 ms | 79.1 MiB |
| 1,000,000 | 87,008,320 bytes | 296.4 ms | 839.2 ms | 507.4 ms | 339.0 MiB |

RSS is the peak over construction, snapshot generation, reload, and queries, not steady-state lookup memory. Synthetic files use a short identity string; real databases additionally store full tokenizer metadata. Graph nodes and the persisted index consume storage, and compaction allocates a captured graph and temporary buffers. The snapshot copy, learning, and retention can still delay lookup under the database mutex.

These microbenchmarks measure lookup work only. They do not establish acceptance, model quality, end-to-end throughput, cold-cache behavior, or lookup tail latency during a large snapshot capture. The server fixtures establish correctness on the tested models; source overlap, repeated requests, model/backend speed, and persistence activity determine practical inference gains.
