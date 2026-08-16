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

- `content.py` defines strict, versioned curriculum and executable lab contracts with Pydantic.
- `registry.py`, `activities.py`, `lab_contracts.py`, and `labs.py` map declared content types to independently testable handlers. Both core specs carry only common metadata plus a generic configuration object. Activity/lab packages own their type-specific schemas; handlers own validation, rendering, child IDs, evaluation, and—for labs—request construction/execution. UI code dispatches through these registries instead of branching on content types.
- `validation.py` performs the complete cached startup audit: stable and duplicate IDs, module/objective mappings, explanations, option uniqueness, registry resolution, activity-specific rules, runner policy, trusted setup/checkpoint compilation and execution, and traceability.
- `storage.py` owns SQLite state, SHA-256 progress envelopes, row-level schema/content validation, preview, backup, transactional restore, and reset.
- `runner.py` validates bounded ASTs and controls the short-lived worker.
- `runner_worker.py` executes trusted setup, learner code with a minimal built-in allowlist, then trusted checkpoint expressions in isolated Python mode.
- `exporter.py` creates and validates the real multi-format package.
- `app.py` renders pages and writes durable progress only after explicit submissions.

Production data defaults to `%LOCALAPPDATA%\MLLearningLab`. Tests may set `MLLAB_DATA_DIR` to isolate state.

## Runner safeguard

Never describe the runner as a sandbox. The trust model is a local learner editing a bounded region. Each lab declares trusted setup code and exported objects, editable names, calls, attributes, line/byte bounds, timeout, output limit, and executable checkpoints. Validation blocks imports, private attributes, unknown names, file/network/process operations, and dynamic evaluation in learner code. The parent process also enforces time and output limits, terminates the Windows process tree, and removes the temporary working directory.

Trusted setup and checkpoint expressions are content-author code, not learner code. Startup runs the starter contract in a child process and rejects setup, export, runtime, timeout, output, or checkpoint failures. Later lab policies must add operations narrowly and receive runner regression tests. The Milestone 1.1 suite includes a pandas DataFrame contract plus source-size, output-size, timeout, worker cleanup, and descendant-process cleanup cases.

## Application identity and duplicate instances

`app-metadata.json` declares the application ID, build version, supported Python line, and fixed port. The launcher owns `%LOCALAPPDATA%\MLLearningLab\state\instance.json`, containing the application ID, normalized project root, launcher PID, port, and start time. A second launcher reuses an instance only when the marker identity, live owner process, and Streamlit health endpoint all agree. A healthy but unidentified Streamlit service on port 8501 is rejected. The owning launcher removes its marker on shutdown; stale markers are removed only after the recorded process is gone.

## Progress versions

- `schema_version` is an integer and changes with storage shape.
- `content_version` is semantic and changes when stable curriculum IDs or completion meaning change.
- Restore currently accepts only the exact Milestone 1.1 schema and content version. Before any backup or database mutation, every progress, quiz-attempt, and setting row is validated for exact fields, types, stable IDs, allowed states, content version, timezone-aware timestamps, JSON shape/size, value bounds, and duplicate keys. Later migrations must be explicit and tested.

## Export contract

`build_vertical_slice_package` returns ZIP bytes and an inventory. `validate_package` verifies ZIP CRC, schemas, workbook sheets, notebook format and relative path, PNG, UTF-8 briefs, inventory, and hashes. Full projects will use the same service boundary.

## Logging

The Python logger rotates at 1 MiB with five backups. The launcher independently rotates its log. Never log learner source, complete data rows, environment variables, or restore contents.

## Release procedure for Milestone 1.1

1. Install the exact lock in a clean Python 3.13 environment.
2. Run compilation and all tests.
3. Parse the launcher, run the complete startup curriculum audit, and run all automated tests.
4. Exercise verified duplicate-instance reuse and unidentified-instance rejection.
5. Build and validate the Milestone 1.1 evidence ZIP.
6. Run the launcher and manually complete the vertical slice.
7. Verify restart/resume and one export/restore cycle.
8. Stop and request user review; do not begin Milestone 2.
