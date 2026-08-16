from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml_lab.storage import ProgressStore, RestoreError, _canonical_json


def make_store(tmp_path: Path) -> ProgressStore:
    return ProgressStore(tmp_path / "state" / "progress.db", tmp_path / "backups")


def test_progress_export_preview_restore_and_backup(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_completed("activity:F1-SORT", "activity", {"score": 6})
    exported = store.export_bytes()
    preview = store.preview_restore(exported)
    assert preview.progress_records == 1

    store.mark_completed("lab:F1-LAB", "code_lab")
    backup = store.restore(exported)
    assert backup.exists()
    assert store.is_completed("activity:F1-SORT")
    assert not store.is_completed("lab:F1-LAB")


def test_tampered_progress_is_rejected_without_mutation(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_completed("activity:F1-SORT", "activity")
    envelope = json.loads(store.export_bytes())
    envelope["progress"] = []
    with pytest.raises(RestoreError, match="integrity"):
        store.restore(json.dumps(envelope))
    assert store.is_completed("activity:F1-SORT")


def test_incompatible_content_version_is_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    envelope = json.loads(store.export_bytes())
    envelope["content_version"] = "2.0.0"
    payload = {key: value for key, value in envelope.items() if key != "integrity"}
    envelope["integrity"]["digest"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
    with pytest.raises(RestoreError, match="incompatible content"):
        store.preview_restore(json.dumps(envelope))


def test_reset_creates_recoverable_backup(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_completed("check:F1", "knowledge_check")
    store.reset()
    assert not store.completed_ids()
    assert list((tmp_path / "backups").glob("progress-before-restore-*.db"))
