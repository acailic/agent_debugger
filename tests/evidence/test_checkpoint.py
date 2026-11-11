"""Independent checkpoint store tests (insert-only, durable, self-verifying)."""

import json
import stat

import pytest

from evidence.checkpoint import CheckpointError, CheckpointStore
from evidence.schema import FinalCheckpoint


def test_record_execution_start_is_insert_only(tmp_path):
    store = CheckpointStore(tmp_path)
    record = store.record_execution_start("exec-1", "gw-1", "svc-claims", "policy-7")
    assert record.execution_id == "exec-1"
    assert record.gateway_id == "gw-1"
    assert record.principal == "svc-claims"
    assert record.policy_version == "policy-7"
    with pytest.raises(CheckpointError):
        store.record_execution_start("exec-1", "gw-1", "other-principal", "policy-8")


def test_finalize_is_insert_only(tmp_path):
    store = CheckpointStore(tmp_path)
    checkpoint = store.finalize("exec-1", "gw-1", 3, "ab" * 32)
    with pytest.raises(CheckpointError):
        store.finalize("exec-1", "gw-1", 99, "ff" * 32)
    assert store.get_final("exec-1") == checkpoint


def test_finalize_stamps_store_key_and_verifies(tmp_path):
    store = CheckpointStore(tmp_path)
    checkpoint = store.finalize("exec-1", "gw-1", 3, "ab" * 32)
    assert checkpoint.checkpoint_key_id == store.key_id
    assert checkpoint.event_count == 3
    assert checkpoint.final_hash == "ab" * 32
    assert store.verify_final(checkpoint) is True


def test_verify_final_false_after_signature_tampering(tmp_path):
    store = CheckpointStore(tmp_path)
    checkpoint = store.finalize("exec-1", "gw-1", 3, "ab" * 32)
    flipped_bits = checkpoint.model_copy(update={"signature": "00" * 64})
    assert store.verify_final(flipped_bits) is False


def test_verify_final_false_after_body_tampering(tmp_path):
    store = CheckpointStore(tmp_path)
    checkpoint = store.finalize("exec-1", "gw-1", 3, "ab" * 32)
    truncated_chain = checkpoint.model_copy(update={"event_count": 2})
    assert store.verify_final(truncated_chain) is False


def test_get_start_and_get_final_roundtrip(tmp_path):
    store = CheckpointStore(tmp_path)
    start = store.record_execution_start("exec-1", "gw-1", "svc-claims", "policy-7")
    checkpoint = store.finalize("exec-1", "gw-1", 4, "cd" * 32)
    assert store.get_start("exec-1") == start
    assert store.get_final("exec-1") == checkpoint
    assert store.get_start("never-recorded") is None
    assert store.get_final("never-recorded") is None


def test_execution_ids_lists_starts_and_finals(tmp_path):
    store = CheckpointStore(tmp_path)
    store.record_execution_start("exec-a", "gw-1", "svc-claims", "policy-7")
    store.record_execution_start("exec-b", "gw-1", "svc-claims", "policy-7")
    store.finalize("exec-c", "gw-1", 1, "ab" * 32)
    assert store.execution_ids() == ["exec-a", "exec-b", "exec-c"]


def test_restart_reuses_database_and_same_key_id(tmp_path):
    first = CheckpointStore(tmp_path)
    start = first.record_execution_start("exec-1", "gw-1", "svc-claims", "policy-7")
    checkpoint = first.finalize("exec-1", "gw-1", 3, "ab" * 32)
    first_key_id = first.key_id
    first.close()

    second = CheckpointStore(tmp_path)
    assert second.key_id == first_key_id
    assert second.get_start("exec-1") == start
    assert second.get_final("exec-1") == checkpoint
    # Insert-only survives the restart too.
    with pytest.raises(CheckpointError):
        second.record_execution_start("exec-1", "gw-1", "svc-claims", "policy-7")
    with pytest.raises(CheckpointError):
        second.finalize("exec-1", "gw-1", 3, "ab" * 32)


def test_store_layout_is_self_contained(tmp_path):
    CheckpointStore(tmp_path)
    assert (tmp_path / "checkpoints.db").exists()
    assert (tmp_path / "checkpoint_key.pem").exists()
    assert (tmp_path / "checkpoint_key.pub.pem").exists()


def test_private_key_file_is_owner_read_write_only(tmp_path):
    CheckpointStore(tmp_path)
    mode = stat.S_IMODE((tmp_path / "checkpoint_key.pem").stat().st_mode)
    assert mode == 0o600


def test_dump_checkpoint_writes_verifiable_json(tmp_path):
    store = CheckpointStore(tmp_path)
    stored = store.finalize("exec-1", "gw-1", 5, "ab" * 32)
    out_file = tmp_path / "handoff" / "exec-1.checkpoint.json"

    dumped = store.dump_checkpoint("exec-1", out_file)

    assert dumped == stored
    parsed = FinalCheckpoint.model_validate(json.loads(out_file.read_text(encoding="utf-8")))
    assert parsed == stored
    assert store.verify_final(parsed) is True


def test_dump_checkpoint_unknown_execution_raises(tmp_path):
    store = CheckpointStore(tmp_path)
    with pytest.raises(CheckpointError):
        store.dump_checkpoint("never-finalized", tmp_path / "nope.json")
