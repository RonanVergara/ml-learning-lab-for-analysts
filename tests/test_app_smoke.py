from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_home_and_lesson_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLLAB_DATA_DIR", str(tmp_path / "local-app-data"))
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "ML Learning Lab for Analysts"
    assert any("Milestone 1.1 review slice" in caption.value for caption in app.caption)

    app.sidebar.radio[0].set_value("Learn: F1").run()
    assert not app.exception
    assert app.title[0].value == "Reporting, rules, or machine learning?"
    assert any("Takeaway" in markdown.value for markdown in app.markdown)


def test_evidence_export_screen_builds_valid_package(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLLAB_DATA_DIR", str(tmp_path / "local-app-data"))
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.sidebar.radio[0].set_value("Evidence export").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "Milestone 1.1 evidence package"
    assert any("Validated 7 artifacts" in success.value for success in app.success)


def test_complete_lesson_persists_across_app_restart(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "local-app-data"
    monkeypatch.setenv("MLLAB_DATA_DIR", str(data_dir))
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.sidebar.radio[0].set_value("Learn: F1").run()

    app.radio[0].set_value("Explore").run()
    answers = ["reporting", "rules", "ml", "reporting", "rules", "ml"]
    for selectbox, answer in zip(app.selectbox, answers, strict=True):
        selectbox.set_value(answer)
    app.button[0].click().run()
    assert any("Activity complete" in success.value for success in app.success)

    app.radio[0].set_value("Code").run()
    source = "\n".join(
        [
            'yesterday_volume = "reporting"',
            'critical_routing = "rules"',
            'repeat_contact_risk = "ml"',
        ]
    )
    app.text_area[0].set_value(source)
    next(button for button in app.button if button.label == "Run checkpoint").click().run()
    assert any("All checkpoints passed" in success.value for success in app.success)

    app.radio[0].set_value("Check").run()
    correct_answers = [0, 1, 1]
    for radio, answer in zip(app.radio[1:4], correct_answers, strict=True):
        radio.set_value(answer)
    app.button[0].click().run()
    assert any("Vertical-slice lesson complete" in success.value for success in app.success)

    restarted = AppTest.from_file(APP_PATH, default_timeout=30).run()
    restarted.sidebar.radio[0].set_value("Learn: F1").run()
    assert any("Vertical-slice lesson complete" in success.value for success in restarted.success)
