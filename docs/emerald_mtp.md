# EmeraldMTP context graph

EmeraldMTP proposes tokens from exact contexts in imported text and verified conversations. The target model verifies every proposal. The database contains tokenizer metadata, overlapping token ranges, context nodes, and observation counts; it contains no model weights, filenames, conversation IDs, or structured chat transcript.

The implementation is `common/emerald-mtp.cpp` in [the feature patch](../patches/emerald_mtp.patch).

## Lookup and learning

Each node represents one distinct `n_match`-token context. A compact open-addressed hash index finds the initial node. An eight-bit hash tag filters candidates before an exact token comparison; hashes never substitute for equality.

Each context caches its winning next token and a successor node. For example:

```text
context [10, 20, 30], winner 40
    -> context [20, 30, 40], winner 50
    -> context [30, 40, 50], winner 60
```

After the initial lookup, drafting follows node IDs and emits cached winners until `n_max` tokens or a missing successor. Cycles are permitted and bounded by `n_max`. Results shorter than `n_min` are discarded. Adjacent token ranges alone never establish a transition: the shifted context must exist in the exact index.

The winner has the greatest saturating `imported + learned` count; ties select the lower token ID. Counts and alternative-continuation chains are separate from the hot node array. Observations update the winner immediately. A changed winning token invalidates its successor; a missing successor is retried after new contexts are inserted. Packing or eviction rebuilds all links. Snapshots store resolved links, including missing-successor sentinels.

The server observes each text prompt once and learns only committed reply tokens. Rejected drafts, replayed decode batches, and tokens after a processed stop condition are excluded. Learning includes prompt/reply boundary fragments, clears tracking when a slot is released, and is disabled for multimodal prompts. All slots share one database.

## File organization

A file consists of a snapshot frame followed by checksummed journal frames. Integers are unsigned fixed-width little-endian. Token IDs are four bytes and must be nonnegative IDs below the active vocabulary size. IDs and offsets are eight bytes; `UINT64_MAX` denotes a missing node or empty index slot. Section offsets are relative to the snapshot payload. Serialization explicitly writes fields; it does not depend on C++ struct padding.

### Frame envelope

Every frame has a 64-byte header:

| Byte offset | Bytes | Field |
| --- | --- | --- |
| 0 | 8 | ASCII `EGRAPH01` format signature |
| 8 | 4 | Kind: 1 = snapshot, 2 = learned-observation journal |
| 12 | 4 | Reserved, zero |
| 16 | 8 | Payload length |
| 24 | 8 | Payload checksum |
| 32 | 32 | Reserved, zero |
| 64 | Payload length | Payload |

The checksum is FNV-1a over payload bytes: start at `14695981039346656037`; XOR each byte, then multiply by `1099511628211`, wrapping modulo `2^64`. It detects corruption and is not cryptographic authentication. The next frame starts immediately after the payload.

### Snapshot header

The snapshot payload starts with 128 bytes:

| Byte offset | Bytes | Field |
| --- | --- | --- |
| 0 | 4 | `n_match`, 1–1024 |
| 4 | 4 | Reserved, zero |
| 8 | 8 | Logical observation clock |
| 16 | 8 | Tokenizer identity byte count |
| 24 | 8 | Token count |
| 32 | 8 | Context-node count |
| 40 | 8 | Continuation-record count |
| 48 | 8 | Hash-table capacity |
| 56 | 8 | Tokenizer identity section offset, 128 |
| 64 | 8 | Token section offset |
| 72 | 8 | Context-node section offset |
| 80 | 8 | Continuation section offset |
| 88 | 8 | Hash-table section offset |
| 96 | 8 | Hash-tag section offset |
| 104 | 8 | End offset, equal to payload length |
| 112 | 16 | Reserved, zero |

Sections appear in that order. Each starts on a 64-byte boundary; padding and the padding through the end offset are zero. Since the first frame begins at file offset zero and its envelope is 64 bytes, snapshot sections are also aligned in the file. The loader checks exact offsets, lengths, alignment, and padding.

The tokenizer identity is the full serialized GGUF metadata after removing keys that do not start with `tokenizer.`. Vocabulary, merges, special tokens, and tokenizer settings participate in byte-for-byte equality. This is an opaque metadata blob, not a hash. Metadata overrides that cannot be reproduced by the importer are rejected.

The token section contains packed four-byte token IDs. Only novel fragments allocate token storage; overlapping observed windows share storage, including an exactly matching arena suffix across observation calls. Compaction retains the union of live `n_match + 1` token ranges and rewrites offsets.

### Context nodes

Each persisted node occupies 32 bytes:

| Record offset | Bytes | Field |
| --- | --- | --- |
| 0 | 8 | Key offset in the token array, measured in tokens |
| 8 | 8 | First continuation-record ID |
| 16 | 8 | Successor context-node ID, or `UINT64_MAX` |
| 24 | 4 | Number of continuations |
| 28 | 4 | Winning next token |

A node's alternatives are contiguous in the continuation section. Nodes collectively own all continuation records exactly once, in node order. Every node has at least one continuation. Node IDs are positions in this array, not source offsets or durable application identifiers.

The loader checks that every alternative has the node's exact key, that next tokens are unique within a node, and that the cached winning token follows the count/tie rules. It verifies each successor against an exact lookup of the winning shifted context. An invalid cache is rejected rather than trusted.

### Continuation records

Each continuation occupies 32 bytes:

| Record offset | Bytes | Field |
| --- | --- | --- |
| 0 | 8 | Offset of its `n_match + 1` token fragment |
| 8 | 8 | Imported observation count |
| 16 | 8 | Learned observation count |
| 24 | 8 | Logical clock at its most recent observation |

At least one count is nonzero. Recency is nonzero and no greater than the snapshot clock. Individual count increments and clock increments reject overflow. Winner scores saturate at `UINT64_MAX` when adding the two counts. Preserving the clock in the header keeps it monotonic even if retention removes the most recently observed entry.

### Context index

The index has a power-of-two capacity of at least 16, with at most half its slots occupied. Each slot stores an eight-byte context ID or `UINT64_MAX`; the tag section stores one byte per slot. Empty slots have zero tags. Occupied tags contain the high eight bits of the key hash. Linear probing begins at `hash & (capacity - 1)` and wraps at the capacity.

The key hash uses unsigned 64-bit arithmetic:

```text
h = 0x9e3779b97f4a7c15
for token in the n_match-token key:
    h ^= uint32(token) + 0x9e3779b97f4a7c15 + (h << 6) + (h >> 2)
h ^= h >> 30; h *= 0xbf58476d1ce4e5b9
h ^= h >> 27; h *= 0x94d049bb133111eb
h ^= h >> 31
```

The loader uses the persisted index after validating tags, slot ownership, probe reachability, and unique exact keys. Loading still reads and validates the entire snapshot; this implementation does not memory-map the file.

### Journal payload

Journal payloads contain consecutive sequence records, each comprising an eight-byte token count followed by that many four-byte token IDs. The frame kind is in the envelope. Sequence records have no padding.

Replay slides an `n_match + 1` window within each sequence, updates learned counts, advances the logical clock, and updates cached winners. It never forms windows across sequence records. Counts and contexts become visible to lookups when observed in memory, without waiting for disk persistence. Imported observations are saved in snapshots.

## Persistence and retention

An OS writer lock on `PATH.lock` lasts throughout server/importer lifetime. Stop the server before an importer appends. A missing server database is created and synced before serving requests; an existing malformed or incompatible file is rejected.

The worker flushes at roughly one-second intervals and drains at orderly shutdown. Journal flushing detaches pending observations under the database mutex, then writes and syncs outside that mutex. A separate persistence mutex serializes flushes and compactions.

Compaction copies a consistent graph generation under the database mutex. Packing, index/link construction, serialization, checksumming, writing, syncing, and replacement operate on that copy outside the database mutex. The live graph continues accepting observations; those observations remain pending for a subsequent transaction. Generation copying still takes time proportional to database memory and can delay lookups. Learning and retention also share the database mutex. This is not a lock-free implementation.

Compaction is requested for creation, imported changes, and retention that clears learned counts. Retention must be saved as a snapshot so replay cannot restore discarded observations. Journal growth triggers it when the pending payload or accumulated file growth crosses approximately twice the current snapshot-size estimate. A configured size limit alone does not force a snapshot on every dirty flush. Loading under a smaller size limit can request compaction.

A snapshot is written and synced to `PATH.tmp`, then atomically replaces `PATH`. POSIX also syncs the parent directory; Windows uses replacement with write-through flags. Loading does not recover from leftover temporary files. Peak memory includes the live graph, captured graph, packing buffers, and serialized snapshot. Temporary disk space must accommodate a second snapshot. The persisted context index and transitions trade additional storage for less lookup work.

Size limits use decimal GB and apply to compacted contents, including headers, alignment, metadata, and the index. Zero means unlimited. Retention clears learned counts from least recently observed entries first, preserving imported counts. Entries with no counts are removed and token ranges packed. Protected imports that cannot fit fail; runtime learning pauses when no learned entry can fit. Journal bytes, temporary disk space, and RAM are not covered by the limit.

A persistence failure is logged and pauses learning while existing lookups remain available. Abrupt exit can lose observations not yet flushed. The flush interval is not a strict durability deadline.

## Recovery and verification

The initial snapshot must be complete. After it, an incomplete final envelope or a valid envelope declaring a payload beyond EOF is treated as an interrupted append; the loader truncates to the last complete frame while holding the writer lock. Complete bad checksums, invalid signatures, malformed sections, invalid token IDs, and inconsistent graph caches are rejected.

`test-emerald-mtp` checks graph decisions against an independent frequency map, successor invalidation, cycles, retention, concurrent observation/flush/draft calls, persistence, recovery, and malformed files. `test-emerald-mtp-bench [corpus_tokens] [queries]` is an opt-in synthetic lookup benchmark. Python importer and server tests validate real tokenizer imports, independent persisted counts, target verification, and request lifecycle behavior. See [validation](emerald-mtp-validation.md) for tested configurations and measurement limits.
