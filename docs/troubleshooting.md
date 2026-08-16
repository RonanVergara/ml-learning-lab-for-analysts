# Troubleshooting

## Python 3.13 is not found

Install 64-bit CPython 3.13 from the official Windows installer and include the Python Launcher. Verify `py -3.13 --version`, then rerun the launcher.

## First-time dependency installation fails

- Confirm internet access and available disk space.
- Read `%LOCALAPPDATA%\MLLearningLab\logs\launcher.log`.
- Keep `requirements.lock` beside the launcher; do not substitute `requirements.in`.
- If the private environment is incomplete, close the app and rename `.venv` to `.venv.failed`. Relaunch to create a clean environment. Delete the renamed folder only after the new environment works.

## The browser does not open

Visit `http://127.0.0.1:8501` manually. If the health endpoint is already active, the launcher reuses the running instance.

## Port 8501 is occupied by another application

Stop the unrelated process using port 8501 and relaunch. Milestone 1 intentionally uses a fixed loopback port so duplicate-instance detection remains predictable.

## A code lab rejects an edit

Read the editable-line count and checkpoint message. A lesson permits only its declared assignments and operations. Restore the working region with **Reset editable region**. The safeguard is intentionally narrower than a notebook.

## A code run times out

The child process and its process tree are stopped. Reset the region and make only the requested edits. Details are written to the application log without recording your code.

## Progress will not import

The app validates UTF-8 JSON, SHA-256 integrity, schema version, and content version before restore. Use an export produced by this content version. A confirmed restore creates a database backup under `%LOCALAPPDATA%\MLLearningLab\backups` before replacement.

## Logs and recovery

- Application log: `%LOCALAPPDATA%\MLLearningLab\logs\ml-learning-lab.log`
- Launcher log: `%LOCALAPPDATA%\MLLearningLab\logs\launcher.log`
- Progress database: `%LOCALAPPDATA%\MLLearningLab\state\progress.db`
- Automatic backups: `%LOCALAPPDATA%\MLLearningLab\backups`

Both logs are size-bounded and rotated. Logs must never contain learner source code or dataset contents.
