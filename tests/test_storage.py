from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ml_lab.storage import ProgressStore, RestoreError, _canonical_json


def make_store(tmp_path: Path) -> ProgressStore:
    return ProgressStore(tmp_path / "state" / "progress.db", tmp_path / "backups")


def reseal(envelope: dict[str, object]) -> bytes:
    payload = {key: value for key, value in envelope.items() if key != "integrity"}
    envelope["integrity"] = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    return json.dumps(envelope).encode("utf-8")


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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("item_id", "bad id with spaces", "item_id"),
        ("item_id", 123, "item_id"),
        ("item_type", "unknown", "item_type"),
        ("status", "started", "status"),
        ("content_version", "9.9.9", "content_version"),
        ("updated_at", "2026-08-16", "updated_at"),
        ("payload_json", "not-json", "payload_json"),
        ("payload_json", "[]", "payload_json"),
    ],
)
def test_progress_restore_validates_every_row_field_before_mutation(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    store = make_store(tmp_path)
    store.mark_completed("activity:F1-SORT", "activity", {"score": 6})
    envelope = json.loads(store.export_bytes())
    envelope["progress"][0][field] = value

    with pytest.raises(RestoreError, match=rf"progress row 1.*{message}"):
        store.restore(reseal(envelope))

    assert store.is_completed("activity:F1-SORT")
    assert not list((tmp_path / "backups").glob("progress-before-restore-*.db"))


def test_restore_rejects_missing_extra_and_duplicate_progress_rows(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_completed("activity:F1-SORT", "activity")
    original = json.loads(store.export_bytes())

    missing = deepcopy(original)
    del missing["progress"][0]["status"]
    with pytest.raises(RestoreError, match=r"progress row 1.*status"):
        store.preview_restore(reseal(missing))

    extra = deepcopy(original)
    extra["progress"][0]["unexpected"] = True
    with pytest.raises(RestoreError, match=r"progress row 1.*unexpected"):
        store.preview_restore(reseal(extra))

    duplicate = deepcopy(original)
    duplicate["progress"].append(deepcopy(duplicate["progress"][0]))
    with pytest.raises(RestoreError, match="duplicate item_id"):
        store.preview_restore(reseal(duplicate))


def test_quiz_and_setting_rows_are_validated_and_restorable(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_completed("lesson:F1-L1", "lesson")
    envelope = json.loads(store.export_bytes())
    timestamp = envelope["progress"][0]["updated_at"]
    envelope["quiz_attempts"] = [
        {
            "id": 1,
            "quiz_id": "F1-QUIZ",
            "score": 0.8,
            "answers_json": '{"F1-Q1": "a"}',
            "content_version": envelope["content_version"],
            "created_at": timestamp,
        }
    ]
    envelope["settings"] = [
        {"key": "font_scale", "value_json": "1.1", "updated_at": timestamp}
    ]

    signed = reseal(envelope)
    preview = store.preview_restore(signed)
    assert preview.quiz_attempts == 1
    assert preview.settings == 1
    assert store.restore(signed).exists()

    invalid_quiz = deepcopy(envelope)
    invalid_quiz["quiz_attempts"][0]["score"] = 1.5
    with pytest.raises(RestoreError, match=r"quiz_attempts row 1.*score"):
        store.preview_restore(reseal(invalid_quiz))

    invalid_quiz_type = deepcopy(envelope)
    invalid_quiz_type["quiz_attempts"][0]["score"] = "0.8"
    with pytest.raises(RestoreError, match=r"quiz_attempts row 1.*score"):
        store.preview_restore(reseal(invalid_quiz_type))

    invalid_answers = deepcopy(envelope)
    invalid_answers["quiz_attempts"][0]["answers_json"] = "[]"
    with pytest.raises(RestoreError, match=r"quiz_attempts row 1.*answers_json"):
        store.preview_restore(reseal(invalid_answers))

    invalid_setting = deepcopy(envelope)
    invalid_setting["settings"][0]["value_json"] = "not-json"
    with pytest.raises(RestoreError, match=r"settings row 1.*value_json"):
        store.preview_restore(reseal(invalid_setting))

    invalid_setting_type = deepcopy(envelope)
    invalid_setting_type["settings"][0]["key"] = 123
    with pytest.raises(RestoreError, match=r"settings row 1.*key"):
        store.preview_restore(reseal(invalid_setting_type))


def test_restore_rejects_non_object_envelope_and_non_hex_integrity(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(RestoreError, match="top-level JSON object"):
        store.preview_restore("[]")

    envelope = json.loads(store.export_bytes())
    envelope["integrity"]["digest"] = "z" * 64
    with pytest.raises(RestoreError, match="digest is malformed"):
        store.preview_restore(json.dumps(envelope))


def test_reset_creates_recoverable_backup(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.mark_completed("check:F1", "knowledge_check")
    store.reset()
    assert not store.completed_ids()
    assert list((tmp_path / "backups").glob("progress-before-restore-*.db"))
