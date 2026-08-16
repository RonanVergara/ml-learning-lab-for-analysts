# ML Learning Lab for Analysts

ML Learning Lab is a local Streamlit course for an analyst moving from Excel, Power BI, BPO analytics, and Microsoft Fabric into machine learning with Python and scikit-learn.

## Milestone status

This repository currently implements **Milestone 1.1 only**: the revised production vertical slice required by the approved plan. It includes the learning shell, orientation entry, one complete Foundations lesson, typed activity/lab registries, executable trusted setup and checkpoint contracts, complete startup curriculum validation, a bounded child-process code lab, row-validated progress restore, application-specific duplicate-instance detection, rotating local logs, and a validated CSV/PNG/XLSX/IPYNB/Markdown/HTML/JSON evidence package.

Milestone 2 has deliberately not started. It requires explicit user approval after review of this slice.

## Supported environment

- 64-bit Windows 11
- 64-bit CPython 3.13.x
- Exact packages in `requirements.lock`
- Internet access for first-time dependency installation only

## Start

Double-click `Launch ML Learning Lab.cmd`. The launcher creates `.venv`, installs the tested dependency lock, starts Streamlit on `127.0.0.1:8501`, and opens the browser.

Progress and rotating logs are stored under `%LOCALAPPDATA%\MLLearningLab`, not in the repository.

## Repository map

- `app.py` — Streamlit application shell and Milestone 1 screens
- `ml_lab/` — content contracts, registries, startup validation, storage, runner, and export services
- `content/` — versioned curriculum manifest
- `tests/` — automated content, storage, runner, export, and UI checks
- `scripts/` — Windows bootstrap and review-artifact builder
- `docs/` — learner, operator, developer, and content-authoring guides

## Documentation

- [Quick start](docs/quick-start.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Learner guide](docs/learner-guide.md)
- [Developer guide](docs/developer-guide.md)
- [Content-authoring guide](docs/content-authoring-guide.md)
- [Milestone 1.1 review checklist](docs/milestone-1-review.md)

## Safety and privacy

The app binds to loopback and uses no telemetry. The bounded runner is a trusted-local teaching safeguard, not a secure arbitrary-code sandbox. Do not paste untrusted code into a learning lab.
