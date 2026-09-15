# Reliability discoveries

## 2026-09-15 — Retrying file writes after cancellation or partial failure

**Issue:** Draining the collector buffer before a failed append can lose events.
Retrying a partial append can duplicate records or leave invalid NDJSON.

**Root cause:** Removing a batch from the buffer is separate from acknowledging
its disk write. Cancelling an await of `asyncio.to_thread` does not stop the
underlying thread.

**Solution:** Retain drained batches until the write succeeds, serialize flushes,
and retain a shielded write task across cancellation. Roll failed appends back to
the original file length before retrying.

**Prevention:** Exercise disk errors, partial writes, concurrent flushes, and
shutdown during a blocked write in `tests/collector/test_persistence_recovery.py`.
This is single-writer recovery within a running process: pending batches remain
in memory, and rollback itself can fail. It is not crash durability.

## 2026-09-15 — Search selection across asynchronous replay loading

**Issue:** Search navigation can select an event but leave replay at another
index, or have a delayed replay response reset the search position.

**Root cause:** Search and replay used different event lists and independently
updated selection and replay position.

**Solution:** Route search clicks through one store action, use the same merged
event ordering as the display, and retain the target until replay loading
completes. Load replay only when its bundle belongs to the selected session.

**Prevention:** Keep App-level tests with deferred bundle/replay responses and
real search/store behavior in `frontend/src/__tests__/SearchNavigation.test.tsx`.
