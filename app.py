from __future__ import annotations

import logging

import streamlit as st

from ml_lab.activities import build_activity_registry
from ml_lab.config import APP_NAME, APP_VERSION, CONTENT_VERSION, configure_logging, data_root
from ml_lab.content import LessonSpec, load_curriculum
from ml_lab.exporter import build_vertical_slice_package, validate_package
from ml_lab.labs import build_lab_registry
from ml_lab.storage import ProgressStore, RestoreError
from ml_lab.validation import validate_curriculum_startup

st.set_page_config(
    page_title="ML Learning Lab",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOGGER = configure_logging()


@st.cache_resource
def activity_handlers():
    return build_activity_registry()


@st.cache_resource
def lab_handlers():
    return build_lab_registry()


@st.cache_resource
def curriculum():
    spec = load_curriculum()
    report = validate_curriculum_startup(spec, activity_handlers(), lab_handlers())
    LOGGER.info(
        "Curriculum validated lessons=%s objectives=%s activities=%s labs=%s checks=%s checkpoints=%s",
        report.lessons,
        report.objectives,
        report.activities,
        report.labs,
        report.knowledge_checks,
        report.lab_checkpoints,
    )
    return spec


@st.cache_resource
def progress_store():
    return ProgressStore()


def required_lesson_items(lesson: LessonSpec) -> list[str]:
    return [
        f"activity:{lesson.activity.id}",
        f"lab:{lesson.lab.id}",
        f"check:{lesson.id}",
    ]


def refresh_lesson_completion(store: ProgressStore, lesson: LessonSpec) -> None:
    if all(store.is_completed(item_id) for item_id in required_lesson_items(lesson)):
        store.mark_completed(f"lesson:{lesson.id}", "lesson")


def status_label(store: ProgressStore, item_id: str) -> str:
    return "Complete" if store.is_completed(item_id) else "Not started"


def render_home(store: ProgressStore, lesson: LessonSpec) -> None:
    st.title(APP_NAME)
    st.caption("Milestone 1.1 review slice · local, practical, and built for analysts")
    st.info(
        "This review build intentionally contains the orientation entry and one complete "
        "Foundations lesson. Milestone 2 will add the full orientation and Foundations module."
    )
    items = required_lesson_items(lesson)
    summary = store.status_summary(items)
    left, middle, right = st.columns(3)
    left.metric("Vertical-slice progress", f"{summary['completed']} / {summary['total']}")
    middle.metric("Lesson", status_label(store, f"lesson:{lesson.id}"))
    right.metric("Course completion", "In progress")
    st.subheader("Your open learning path")
    st.markdown(
        "**Start here:** Python & pandas warm-up → **Foundations:** Reporting, rules, or ML? "
        "→ Regression → Classification"
    )
    st.write(
        "Navigation is open. In this review build you can enter the lesson immediately, inspect "
        "progress storage, and generate the end-to-end evidence package."
    )


def render_orientation() -> None:
    spec = curriculum().orientation_entry
    st.title(spec.title)
    st.write(spec.description)
    st.subheader("A familiar bridge")
    st.dataframe(spec.excel_python_map, use_container_width=True, hide_index=True)
    st.markdown(
        "In the full orientation, you will edit only two to four lines at first. Setup code stays "
        "visible and read-only, so you can focus on the one Python idea being practiced."
    )
    st.info("The two complete orientation lessons are a Milestone 2 deliverable.")


def render_activity(store: ProgressStore, lesson: LessonSpec) -> None:
    activity = lesson.activity
    st.subheader(activity.title)
    st.write(activity.instructions)
    handler = activity_handlers().require(activity.type)
    evaluation = handler.render(activity)
    if evaluation is not None:
        for item in evaluation.items:
            if item.correct:
                st.success(f"{item.prompt} — {item.rationale}")
            else:
                st.error(f"{item.prompt} — {item.rationale}")
        if evaluation.passed:
            store.mark_completed(f"activity:{activity.id}", "activity")
            st.success("Activity complete. You chose the simplest suitable tool each time.")
        else:
            st.warning("Review the explanations, adjust your choices, and try again.")
    if store.is_completed(f"activity:{activity.id}"):
        st.caption("✓ Explore activity saved")


def render_code_lab(store: ProgressStore, lesson: LessonSpec) -> None:
    lab = lesson.lab
    st.subheader(lab.title)
    st.write(lab.instructions)
    handler = lab_handlers().require(lab.type)
    run_result = handler.render(lab)
    if run_result is not None:
        result = run_result
        st.session_state[f"result_{lab.id}"] = {
            "status": result.status,
            "error": result.error,
            "checks": result.checks,
            "duration_ms": result.duration_ms,
        }
        if result.passed:
            store.mark_completed(f"lab:{lab.id}", "code_lab", {"duration_ms": result.duration_ms})
    result = st.session_state.get(f"result_{lab.id}")
    if result:
        if result["status"] == "passed":
            st.success(f"All checkpoints passed in {result['duration_ms']} ms.")
        elif result["status"] == "check_failed":
            st.warning("The code ran, but one or more labels need another look.")
        else:
            st.error(result["error"])
        for check in result["checks"]:
            icon = "✓" if check["passed"] else "○"
            st.write(f"{icon} **{check['name']}** — {check['message']}")
    if store.is_completed(f"lab:{lab.id}"):
        st.caption("✓ Code checkpoint saved")


def render_check(store: ProgressStore, lesson: LessonSpec) -> None:
    st.subheader("Check your understanding")
    selections: dict[str, int | None] = {}
    for number, check in enumerate(lesson.checks, start=1):
        labels = [option.label for option in check.options]
        selected = st.radio(
            f"{number}. {check.prompt}",
            options=[None, *range(len(labels))],
            format_func=lambda value, labels=labels: "Choose an answer…" if value is None else labels[value],
            key=f"knowledge_{check.id}",
        )
        selections[check.id] = selected
    if st.button("Submit lesson check", type="primary"):
        score = 0
        for check in lesson.checks:
            selected = selections[check.id]
            if selected is None:
                st.warning(f"Answer: {check.prompt}")
                continue
            option = check.options[selected]
            if selected == check.correct_index:
                score += 1
                st.success(option.rationale)
            else:
                st.error(option.rationale)
                st.info(check.options[check.correct_index].rationale)
        st.write(f"Score: **{score} / {len(lesson.checks)}**")
        if score == len(lesson.checks):
            store.mark_completed(f"check:{lesson.id}", "knowledge_check", {"score": score})
            st.success("Knowledge check complete.")
        else:
            st.warning("Review the feedback and retry. All three answers complete this slice.")
    if store.is_completed(f"check:{lesson.id}"):
        st.caption("✓ Knowledge check saved")


def render_lesson(store: ProgressStore, lesson: LessonSpec) -> None:
    st.title(lesson.title)
    st.caption(f"ML Foundations · {lesson.duration_minutes} minutes · Objective {lesson.objective_ids[0]}")
    st.info(lesson.scenario)
    stage = st.radio(
        "Lesson step",
        ["Understand", "Explore", "Code", "Check"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if stage == "Understand":
        for section in lesson.understand:
            st.subheader(section["title"])
            st.write(section["body"])
    elif stage == "Explore":
        render_activity(store, lesson)
    elif stage == "Code":
        render_code_lab(store, lesson)
    else:
        render_check(store, lesson)
    refresh_lesson_completion(store, lesson)
    st.divider()
    st.markdown(f"**Takeaway:** {lesson.takeaway}")
    items = required_lesson_items(lesson)
    summary = store.status_summary(items)
    st.progress(summary["completed"] / summary["total"], text=f"Lesson evidence: {summary['completed']} / {summary['total']}")
    if summary["is_complete"]:
        st.success("Vertical-slice lesson complete. Your status is stored locally.")


def render_export() -> None:
    st.title("Milestone 1.1 evidence package")
    st.write(
        "This uses the real project export pipeline to prove that portable analyst artifacts can "
        "be generated without Jupyter, Kaleido, Chrome, or PBIX tooling."
    )
    package = build_vertical_slice_package()
    report = validate_package(package.data)
    st.success(f"Validated {report['artifact_count']} artifacts from {report['rows']} synthetic rows.")
    st.code("\n".join(report["artifacts"]), language=None)
    st.download_button(
        "Download validated evidence ZIP",
        data=package.data,
        file_name=package.filename,
        mime="application/zip",
        type="primary",
    )


def render_progress(store: ProgressStore, lesson: LessonSpec) -> None:
    st.title("Progress & settings")
    paths = data_root()
    st.caption(f"Local data: {paths}")
    rows = [
        {"Evidence": item_id, "Status": status_label(store, item_id)}
        for item_id in required_lesson_items(lesson)
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.subheader("Export progress")
    st.download_button(
        "Download versioned progress JSON",
        data=store.export_bytes(),
        file_name="ml-learning-lab-progress.json",
        mime="application/json",
    )
    st.subheader("Import and restore")
    upload = st.file_uploader("Choose a progress JSON file", type=["json"])
    if upload is not None:
        data = upload.getvalue()
        try:
            preview = store.preview_restore(data)
            st.json(
                {
                    "schema_version": preview.schema_version,
                    "content_version": preview.content_version,
                    "app_version": preview.app_version,
                    "exported_at": preview.exported_at,
                    "progress_records": preview.progress_records,
                }
            )
            confirmed = st.checkbox("Replace current progress after creating a backup")
            if st.button("Restore this progress", disabled=not confirmed):
                backup = store.restore(data)
                LOGGER.info("Progress restored; backup=%s", backup)
                st.success(f"Progress restored. Backup created at {backup}")
                st.cache_resource.clear()
                st.rerun()
        except RestoreError as exc:
            st.error(str(exc))
    st.subheader("Reset")
    reset_confirmed = st.checkbox("I understand reset creates a backup, then clears this profile")
    if st.button("Reset local progress", disabled=not reset_confirmed):
        store.reset()
        LOGGER.info("Local progress reset after backup")
        st.cache_resource.clear()
        st.rerun()


def main() -> None:
    spec = curriculum()
    store = progress_store()
    lesson = spec.lessons[0]
    st.sidebar.title("ML Learning Lab")
    page = st.sidebar.radio(
        "Navigate",
        ["Home", "Start here", "Learn: F1", "Evidence export", "Progress & settings"],
    )
    st.sidebar.caption(f"App {APP_VERSION} · Content {CONTENT_VERSION}")
    st.sidebar.caption("Runs locally on 127.0.0.1")
    if page == "Home":
        render_home(store, lesson)
    elif page == "Start here":
        render_orientation()
    elif page == "Learn: F1":
        render_lesson(store, lesson)
    elif page == "Evidence export":
        render_export()
    else:
        render_progress(store, lesson)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger("ml_learning_lab").exception("Unhandled application error")
        raise
