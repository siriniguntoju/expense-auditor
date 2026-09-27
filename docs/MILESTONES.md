# Build notes and interview guide

This is the smaller Project 3 MVP. Each stage is independently inspectable. All receipts, employees, policies and exchange rates are synthetic.

| Milestone | Delivered | Validation | Interview explanation |
|---|---|---|---|
| M1 — Data and grading | 20 rendered PNG receipts, 10 reports, independent expected-flag labels, strict schemas and deterministic grading | Initial 2 foundation tests passed | Ground truth is a separate input to the grader. Missing output must not disappear from the denominator. A tiny synthetic set is a regression suite, not a generalization claim. |
| M2 — Intake | Fixture replay for the demo; separate opt-in Gemini image + structured-output adapter | Schema and fixture tests; no live Gemini calls | Replaying labels proves plumbing, not OCR quality. Structured output validates shape; it does not establish factual correctness. |
| M3 — Policy tools | Versioned YAML rules/rates, two real stdio MCP servers, deterministic ADK sequence | Conversion boundaries, invalid values, and real MCP calls passed | Use Decimal for money, fixed rate provenance for reproducibility, deterministic rules for policy. ADK coordinates tools without requiring an LLM. |
| M4 — Agent communication | Three separately runnable A2A services with Agent Cards; fixed orchestrator order | Real A2A JSON-RPC pipeline test and all 10 benchmark reports completed | A2A connects agents; MCP connects tools. Cards advertise capabilities, but client calls stay on configured URLs. A2A 1.0 requires the version header. |
| M5 — Reviewer | React/TypeScript UI, AG-UI SSE events, receipt images, evidence, approve/reject/comment, SQLite replay | Stream ordering, persisted decisions, double-decision conflict, failure and restart tests; browser approval and rejection verified | Human review is a durable state transition. Approval does not cause a payment. AG-UI streams progress; separate application endpoints store decisions. |
| M6 — Reproducibility | Pinned direct dependencies, npm lockfile, CI, Docker Compose, measured results and demo script | 16 Python tests passed; lint, TypeScript build, full offline benchmark and four-service Docker smoke test passed locally | Report measured outcomes and limitations separately from spec targets. A checked-in CI workflow is not evidence that hosted CI has run. |

## Important files

- `data/generate.py`: reproducible synthetic data generator; no business/customer data is imported.
- `data/policy.yaml`, `data/rates.yaml`: transparent rules and fixed USD conversion rates, each with a version.
- `auditor/schema.py`: rejects unexpected fields and invalid expense amounts/currencies.
- `auditor/intake.py`: validated fixture replay and optional Gemini image extraction; neither changes policy.
- `tools_mcp/`: independently callable currency and policy tools exposed through MCP.
- `auditor/policy_agent.py`: ADK sequence for currency normalization and policy evaluation.
- `auditor/checks.py`: small, inspectable policy and audit heuristics with evidence per flag.
- `auditor/services/app.py`: shared A2A service factory for the three separate agent processes.
- `auditor/a2a_client.py`: card discovery, A2A version negotiation and typed wire request.
- `auditor/api.py`: fixed orchestration, AG-UI streaming and application API. A disconnected browser does not cancel a running analysis.
- `auditor/store.py`: SQLite run/event history and transaction-protected review decisions. An interrupted run is marked failed on restart; it is not silently resumed.
- `web/src/main.tsx`: reviewer interface and small parser for the emitted AG-UI event subset.
- `evals/grading.py`: exact flag matching on rule + affected lines; six-field extraction grader for future live measurements.
- `evals/run.py`: full offline protocol benchmark. Agent calls use ASGI transport in-process; MCP servers are real subprocesses. The interactive app uses separate HTTP processes.
- `evals/live_extract.py`: deliberately separate, opt-in image extraction benchmark, default one receipt, no automatic retries.
- `tests/`: foundation, numeric boundaries, protocol and persistence/failure tests.

## Deliberate limits

The original larger scope calls for 200 receipts / 50 reports, PostgreSQL, live multimodal intake, ambiguity reasoning and a timed reviewer study. This MVP uses 20 / 10, SQLite, fixture intake in the UI and deterministic audit rules. The live extraction CLI is implemented but has not been measured or connected into the reviewer pipeline. No upload handling, authentication, deployment hardening, full AG-UI client SDK, A2A push notifications, cross-report duplicate search or payment execution.

ADK 2.10.0 still supports `SequentialAgent` but emits a deprecation notice recommending `Workflow`. This small two-stage sequence is pinned and tested; migration is a follow-up. The test client also emits a Starlette/httpx deprecation notice. No warnings are suppressed.

## Known benchmark error

The duplicate fingerprint uses normalized merchant + date + total + currency. Report 07 has two equal-value charges at the same merchant on the same day. They are labeled as split-charge review, but the fingerprint additionally flags a duplicate. This is one false positive. It illustrates why duplicate detection needs receipt identifiers and human review; the benchmark retains the case and error rather than changing labels to inflate precision.
