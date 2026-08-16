# Developer guide

## Runtime and setup

Personal V1 targets only 64-bit Windows 11 and CPython 3.13.x. `requirements.in` records direct choices; `requirements.lock` is the complete transitive environment tested by the launcher.

For development:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Build the review artifact with:

```powershell
.\.venv\Scripts\python.exe scripts\build_milestone1_artifact.py
```

## Architecture

- `content.py` validates the versioned curriculum and objective references with Pydantic.
- `storage.py` owns SQLite state, SHA-256 progress envelopes, preview, backup, transactional restore, and reset.
- `runner.py` validates bounded ASTs and controls the short-lived worker.
- `runner_worker.py` runs with isolated Python mode and a minimal built-in allowlist.
- `exporter.py` creates and validates the real multi-format package.
- `app.py` renders pages and writes durable progress only after explicit submissions.

Production data defaults to `%LOCALAPPDATA%\MLLearningLab`. Tests may set `MLLAB_DATA_DIR` to isolate state.

## Runner safeguard

Never describe the runner as a sandbox. The trust model is a local learner editing a bounded region. Validation blocks imports, attributes, unknown names, file/network/process operations, and dynamic evaluation in the Milestone 1 policy. The parent process also enforces time and output limits and terminates the Windows process tree.

Later lab policies must add operations narrowly and receive runner regression tests.

## Progress versions

- `schema_version` is an integer and changes with storage shape.
- `content_version` is semantic and changes when stable curriculum IDs or completion meaning change.
- Restore currently accepts only the exact Milestone 1 schema and content version. Later migrations must be explicit and tested.

## Export contract

`build_vertical_slice_package` returns ZIP bytes and an inventory. `validate_package` verifies ZIP CRC, schemas, workbook sheets, notebook format and relative path, PNG, UTF-8 briefs, inventory, and hashes. Full projects will use the same service boundary.

## Logging

The Python logger rotates at 1 MiB with five backups. The launcher independently rotates its log. Never log learner source, complete data rows, environment variables, or restore contents.

## Release procedure for Milestone 1

1. Install the exact lock in a clean Python 3.13 environment.
2. Run compilation and all tests.
3. Build and validate the evidence ZIP.
4. Run the launcher and manually complete the vertical slice.
5. Verify restart/resume and one export/restore cycle.
6. Stop and request user review; do not begin Milestone 2.
