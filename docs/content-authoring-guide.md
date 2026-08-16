# Content-authoring guide

## Stable IDs and objectives

Every objective, lesson, activity, lab, lab checkpoint, check, quiz, and project requires a stable ID. Activities and assessments reference objective IDs. Startup validation rejects malformed/duplicate IDs, unknown references, missing registry types, and objectives without assessed evidence.

Changing the meaning of an existing stable ID requires a content-version decision and, when progress should survive, an explicit mapping.

## Explanations

- Begin with an analyst or BPO decision.
- Keep explanation chunks near 250 words or fewer.
- Connect to Excel, Power BI, or Fabric only when the analogy is technically accurate.
- Separate known facts, prediction-time information, and future outcomes.
- End with a business takeaway.

## Choosing an activity

Match the interaction to the objective. Use scenario sorting for problem framing, tables for data inspection, ordering for pipelines, calculators for metrics, and Plotly only for genuinely interactive visual relationships. Do not add a chart solely for consistency.

Every activity declares a `type` plus a generic `configuration` object. Its handler, registered in `build_activity_registry()`, owns the type-specific configuration schema, validation, rendering, child IDs, and evaluation. Add a handler and direct tests before using a new type in curriculum JSON; startup refuses unregistered types. This keeps scenario-sorter fields out of the core curriculum contract and lets later timelines, tables, calculators, and Plotly simulations define only the data they need.

## Bounded editable regions

- Every lab declares a `type` plus a generic `configuration` object. Its registered handler owns the type-specific schema, startup validation, child checkpoint IDs, rendering, request construction, and execution.
- Keep display setup visible and read-only. Put executable content-author setup in `trusted_setup.code` and list only learner-visible objects in `trusted_setup.exports`.
- Orientation and early Foundations expose two to four editable lines.
- Declare the `bounded_python` lab type, exact assignment names, calls, attributes, line bounds, UTF-8 source-byte limit, timeout, and output limit.
- Default code must pass schema validation and be recoverable with Reset.
- Define each checkpoint with a stable ID, label, executable expression, and separate pass/fail messages. Expressions execute after learner code and must return a Python `bool`; explicitly wrap pandas/NumPy scalar comparisons with `bool(...)`.
- Never let an editable assignment overwrite a trusted export. Keep setup and checkpoint code deterministic and free from network or machine-specific dependencies.
- Add tests for valid, incorrect, forbidden, and excessive work whenever a policy expands.

For `bounded_python`, the trusted setup, starter, checkpoints, and policy live inside its `configuration`. New lab types require a handler registered in `build_lab_registry()`, without adding their fields to the core `LabSpec`. Startup compiles the setup and every checkpoint, validates the starter against its policy, and executes the complete starter contract. A deliberately incorrect starter may return `check_failed`; validation, setup, contract, runtime, timeout, and output failures stop application startup.

The runner is a trusted-local teaching safeguard, never a secure arbitrary-code sandbox.

## Knowledge checks and quizzes

- Map every item to an objective.
- Test interpretation and decisions, not trivia.
- Give every option a specific rationale.
- Avoid trick wording, overlapping answers, and unstated assumptions.
- Verify the correct answer against the lesson and code output.

## Project prediction contracts

Before authoring project data or code, declare:

1. Prediction moment.
2. Observation window.
3. Target and target window.
4. Features genuinely available at prediction time.
5. Unavailable or leaking fields.
6. Chronological or group-aware split strategy.

Synthetic generation must make targets fully observable under the declared contract.

## Review checklist

Review ML correctness, BPO analogy accuracy, leakage, validation, reading load, code/output agreement, deterministic reset, answer rationales, objective coverage, responsible use, accessibility, and content-version impact. Placeholder content cannot enter a completed milestone.
