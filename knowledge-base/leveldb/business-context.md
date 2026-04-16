# LevelDB — Business Context

## Overview
LevelDB is a fast key-value storage library by Google. It provides an ordered
mapping from string keys to string values, backed by a log-structured
merge-tree (LSM-tree). It is embedded (not a server), single-process, and
optimized for workloads with high write throughput and range scans.

## Core Architecture
- Write path: `Write` → WAL log → MemTable → (when full) → Immutable MemTable → SSTable
- Read path: MemTable → Immutable MemTable → SSTable files (newest first, level-by-level)
- Compaction: background thread merges SSTable files to reduce read amplification
  and reclaim space from overwritten/deleted keys.

## Key Concepts
- **MemTable**: in-memory sorted skiplist for recent writes.
- **SSTable (Sorted String Table)**: immutable on-disk sorted file produced
  either by flushing a MemTable or by compacting other SSTables.
- **WAL (Write-Ahead Log)**: crash recovery journal; every write is appended
  here before being applied to the MemTable.
- **Manifest / VersionSet**: tracks which SSTable files are live at each level
  and how they are ordered. Each `VersionEdit` records an atomic change to the
  file set (adds/deletes). The current state is reconstructed by replaying
  edits from the manifest.
- **Compaction**: merges overlapping SSTables across levels (L0 → L1 → …),
  preserving the newest version of each key and dropping keys made obsolete by
  deletes or overwrites.
- **Block / BlockBuilder**: an SSTable is composed of data blocks + a
  restart-indexed encoding + an index block + metaindex + footer.
- **Cache**: sharded LRU cache — `block_cache` (reused decoded data blocks),
  `table_cache` (open SSTable handles).
- **Bloom filter**: per-SSTable filter block used to skip reads that definitely
  miss.
- **Snapshot / Sequence number**: every write gets a monotonically increasing
  sequence number; reads at a snapshot see only writes with a sequence ≤ the
  snapshot's.
- **Internal key**: `user_key | sequence_number | value_type` — user key
  concatenated with sequence and a tombstone/value tag. Needed to make the LSM
  store versioned; the user never sees these.

## Directory Structure
- `db/` — core database logic: `DBImpl` (the `DB` implementation), compaction,
  recovery, write batch, memtable, log reader/writer, version set, table cache.
- `table/` — SSTable read/write: `Table`, `Block`, `BlockBuilder`, on-disk
  `format`, merging/two-level iterators.
- `util/` — infrastructure primitives: `Arena` memory allocator, LRU `Cache`,
  `Env` (filesystem/threading abstraction), coding (varints, fixed ints), CRC,
  Bloom filter, comparator, status, options.
- `include/leveldb/` — public API headers (`DB`, `Options`, `Slice`, `Status`,
  `Iterator`, `WriteBatch`, `Comparator`, `FilterPolicy`, `Cache`, `Env`).
- `helpers/memenv/` — in-memory `Env` implementation used by tests.
- `port/` — platform-specific primitives (threads, atomics) behind a common
  interface.

## Naming Conventions
- `rep_` → internal representation pointer (pimpl idiom).
- `Ref()` / `Unref()` → manual reference counting; `Unref()` decrements and
  deletes at zero.
- `user_key` vs `internal_key` → user-visible key vs key augmented with
  sequence + type tag.
- `*_test.cc` and `*_bench.cc` → tests and benchmarks (skipped by this pilot).
- `Impl` suffix → the concrete implementation of a public pure-virtual
  interface (e.g. `DB` / `DBImpl`, `Env` / `PosixEnv`).
- `SequenceNumber`, `ValueType`, `InternalKey` live in `db/dbformat.h` and are
  fundamental to how the LSM encodes history.

## Threading & Lifecycle
- LevelDB is thread-safe for concurrent reads/writes on the same `DB*`.
- A single background thread performs compaction and memtable flushes,
  coordinated via a mutex in `DBImpl`.
- Most internal invariants are guarded by `DBImpl::mutex_`; lock-holding
  conventions are marked in comments (e.g. `GUARDED_BY(mutex_)`).

## Why This Codebase Is Worth Studying
Production-quality C++: RAII everywhere, explicit ownership, minimal dynamic
dispatch, careful use of `port::` abstractions for portability, and a clean
separation between the public header API and the private implementation. A
good reference for LSM-tree engineering and for idiomatic pre-C++17 Google
C++ style.
