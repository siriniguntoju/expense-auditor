# Human review timing protocol

## Purpose
Measure descriptive review time and decision agreement on four synthetic reports, each in manual and assisted conditions. The 15 → 3 minute figure is a target, not an observation. Never insert automated browser clicks or fabricated durations into participant results.

## Participants and assignments
Use the builder plus 2–3 consenting volunteers. Each uses a different anonymous code. No names, email addresses or client information are needed. Eight reviews per person: four cases × two conditions. The app alternates which condition comes first using participant-code parity and case index. This is counterbalancing, not a randomized controlled experiment.

Manual condition: receipt images, claimed amounts/categories, policy and rates; no generated flags or revealing case titles. Assisted condition: the same evidence plus machine-generated flags. Choose fixture fields for a workflow study or real cached Gemini fields for a model-backed study. Do not mix evidence modes within a participant.

## Procedure
Read the policy before starting. Press Start only when ready to work without interruption. Inspect each claim and receipt. Approve if no correction or follow-up is needed; otherwise reject. The decision stops the timer. Continue until all eight reviews are completed. Use the same code after a reload to resume; interrupted trials include interruption time and should be disclosed rather than silently removed.

The server starts time after assisted evidence is prepared. This measures human review effort; model inference and preparation latency are excluded. The app persists each start/finish using server timestamps and prevents a completed assignment from being overwritten.

## Reporting
The `/api/study` endpoint returns raw anonymous trials, completion counts, paired manual/assisted medians, percentage change and agreement with seeded review labels. Unpaired trials are excluded from timing comparisons. Report sample size, evidence mode, hardware/date, interruptions and participant familiarity. Compare like modes; do not pool fixture and real-Gemini studies into a single OCR-assisted claim.

Small repeated-case studies have learning, selection and order effects. Do not state causal productivity improvement or generalize to finance teams from this sample. If no human trials exist, report **not measured**. If the observed reduction is below the target, publish the observation unchanged.
