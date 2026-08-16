# Content-authoring guide

## Stable IDs and objectives

Every objective, lesson, activity, lab, check, quiz, and project requires a stable ID. Activities and assessments reference objective IDs. Startup validation rejects unknown references, while traceability tests detect missing evidence.

Changing the meaning of an existing stable ID requires a content-version decision and, when progress should survive, an explicit mapping.

## Explanations

- Begin with an analyst or BPO decision.
- Keep explanation chunks near 250 words or fewer.
- Connect to Excel, Power BI, or Fabric only when the analogy is technically accurate.
- Separate known facts, prediction-time information, and future outcomes.
- End with a business takeaway.

## Choosing an activity

Match the interaction to the objective. Use scenario sorting for problem framing, tables for data inspection, ordering for pipelines, calculators for metrics, and Plotly only for genuinely interactive visual relationships. Do not add a chart solely for consistency.

## Bounded editable regions

- Keep setup and evaluation visible but read-only.
- Orientation and early Foundations expose two to four editable lines.
- Declare exact assignment names, calls, line bounds, timeout, and output limit.
- Default code must pass schema validation and be recoverable with Reset.
- Add tests for valid, incorrect, forbidden, and excessive work whenever a policy expands.

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
