import { useEffect, useState } from "react";
type Expense = {
  id: string;
  receipt_id: string | null;
  amount: string;
  currency: string;
  category: string;
};
type Trial = {
  id: string;
  report_id: string;
  condition: string;
  started: string;
};
type Session = {
  trial: Trial;
  report: { expenses: Expense[] };
  packet: null | {
    flags: { rule: string; explanation: string; lines: string[] }[];
  };
};
type Summary = {
  trials: {
    participant: string;
    report_id: string;
    condition: string;
    finished: string | null;
  }[];
  completed_trials: number;
  paired_reports: number;
  participants: number;
  manual_median_seconds: number | null;
  assisted_median_seconds: number | null;
  reduction_percent: number | null;
  decision_agreement: number | null;
  measurement: string;
  policy: Record<string, unknown>;
  rates: Record<string, unknown>;
  cases: string[];
};
async function request<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(
    url,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const v = await r.json();
  if (!r.ok) throw Error(v.detail || "Study request failed");
  return v;
}
export default function Study({ onClose }: { onClose: () => void }) {
  const [summary, setSummary] = useState<Summary | null>(null),
    [session, setSession] = useState<Session | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [seconds, setSeconds] = useState(0);
  const [participant, setParticipant] = useState(
    () =>
      localStorage.getItem("study-participant") ||
      "P-" + crypto.randomUUID().slice(0, 8),
  );
  const [index, setIndex] = useState(0),
    [mode, setMode] = useState("fixture_replay");
  useEffect(() => {
    request<Summary>("/api/study")
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!session) return;
    const tick = () =>
      setSeconds(
        Math.floor((Date.now() - Date.parse(session.trial.started)) / 1000),
      );
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [session]);
  const cases = summary?.cases || [];
  // Alternate condition order by participant code and case to reduce one-direction learning bias.
  const flip =
    participant.split("").reduce((n, c) => n + c.charCodeAt(0), 0) % 2;
  const caseIndex = Math.floor(index / 2),
    report = cases[caseIndex];
  const condition =
    index % 2 === (caseIndex + flip) % 2 ? "manual" : "assisted";
  useEffect(() => {
    if (session || !summary) return;
    const flipCode =
      participant.split("").reduce((n, c) => n + c.charCodeAt(0), 0) % 2;
    const next = Array.from(
      { length: summary.cases.length * 2 },
      (_, i) => i,
    ).find((i) => {
      const conditionName =
        i % 2 === (Math.floor(i / 2) + flipCode) % 2 ? "manual" : "assisted";
      return !summary.trials.some(
        (t) =>
          t.participant === participant &&
          t.report_id === summary.cases[Math.floor(i / 2)] &&
          t.condition === conditionName &&
          t.finished,
      );
    });
    setIndex(next ?? summary.cases.length * 2);
  }, [summary, participant, session]);
  async function start() {
    setError("");
    setBusy(true);
    try {
      localStorage.setItem("study-participant", participant);
      setSession(
        await request<Session>("/api/study/start", {
          participant,
          report_id: report,
          condition,
          mode,
        }),
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function finish(decision: string) {
    if (!session) return;
    setBusy(true);
    try {
      await request("/api/study/" + session.trial.id + "/finish", { decision });
      setSession(null);
      setIndex(index + 1);
      setSummary(await request<Summary>("/api/study"));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="study-page">
      <header>
        <div>
          <p className="eyebrow">HUMAN REVIEW STUDY</p>
          <h1>Measure, then make the claim.</h1>
        </div>
        <button disabled={!!session} onClick={onClose}>
          Back to reviewer
        </button>
      </header>
      <div className="notice">
        Only real participant reviews belong here. Review the same four cases
        manually and with assistance. Times start after evidence is prepared;
        model latency is excluded. Repeated cases can create learning effects.
        Reject when any expense needs correction or further review.
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!session ? (
        <section className="card spaced">
          <h2>
            {report
              ? "Prepare your next review"
              : "Study assignments completed"}
          </h2>
          <label>
            Anonymous participant code{" "}
            <input
              value={participant}
              onChange={(e) => setParticipant(e.target.value)}
              pattern="[A-Za-z0-9_-]{3,30}"
            />
          </label>
          <label>
            Evidence source{" "}
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="fixture_replay">
                Fixture fields (workflow study)
              </option>
              <option value="gemini_cached">
                Cached Gemini fields (live-model study)
              </option>
            </select>
          </label>
          <p>
            {report
              ? `Case ${caseIndex + 1} of ${cases.length} · ${condition} review`
              : "Thank you. Measurements are saved locally."}
          </p>
          <p className="muted">
            Use a new anonymous code for each volunteer. Do not enter names or
            personal information. If a session is interrupted, resume it with
            the same code; elapsed time includes the interruption.
          </p>
          <button
            className="primary"
            disabled={busy || !report}
            onClick={start}
          >
            {busy ? "Preparing evidence…" : "Start timed review"}
          </button>
        </section>
      ) : (
        <section className="card spaced">
          <div className="section-title">
            <h2>
              {session.trial.condition === "manual"
                ? "Manual review"
                : "Assisted review"}{" "}
              · Case {caseIndex + 1}
            </h2>
            <span className="pill">
              Elapsed {Math.floor(seconds / 60)}:
              {String(seconds % 60).padStart(2, "0")}
            </span>
          </div>
          <div className="study-receipts">
            {session.report.expenses.map((e) => (
              <article key={e.id}>
                <h3>
                  {e.id} · {e.currency} {e.amount}
                </h3>
                <p>{e.category}</p>
                {e.receipt_id ? (
                  <img
                    src={"/api/receipts/" + e.receipt_id}
                    alt={"Synthetic receipt " + e.receipt_id}
                  />
                ) : (
                  <p>Receipt missing</p>
                )}
              </article>
            ))}
          </div>
          {session.packet && (
            <div>
              <h3>Assistant findings</h3>
              {session.packet.flags.length ? (
                session.packet.flags.map((f, i) => (
                  <p className="finding" key={i}>
                    <b>{f.rule}</b> · {f.lines.join(", ")}
                    <br />
                    {f.explanation}
                  </p>
                ))
              ) : (
                <p>No configured rule flags.</p>
              )}
            </div>
          )}
          <div className="actions">
            <button
              className="primary"
              disabled={busy}
              onClick={() => finish("approve")}
            >
              Approve and stop timer
            </button>
            <button
              className="reject"
              disabled={busy}
              onClick={() => finish("reject")}
            >
              Reject and stop timer
            </button>
          </div>
        </section>
      )}
      <section className="card spaced">
        <h3>Reference policy and fixed rates</h3>
        <ul className="policy-list">
          <li>
            Meals: up to ${String(summary?.policy.meal_limit || "75.00")} per
            expense and ${String(summary?.policy.meal_daily_limit || "100.00")}{" "}
            per day.
          </li>
          <li>
            Transport: up to $150 per expense. Lodging: up to $250 per expense.
          </li>
          <li>
            A receipt is required above $
            {String(summary?.policy.receipt_required_above || "25.00")}. Alcohol
            is not reimbursable.
          </li>
          <li>Fixed conversion: EUR 1 = USD 1.10; GBP 1 = USD 1.25.</li>
          <li>
            Synthetic holiday: September 7, 2026. Weekend and holiday expenses
            require review.
          </li>
        </ul>
        <p className="muted">
          Also check matching totals/currencies, duplicate claims, same-day
          split meals over the limit, weekends and listed holidays.
        </p>
      </section>
      <section className="card spaced">
        <h3>Measured results</h3>
        <p>
          {summary?.completed_trials || 0} completed trials ·{" "}
          {summary?.paired_reports || 0} paired reports ·{" "}
          {summary?.participants || 0} participants
        </p>
        <p>
          Manual median:{" "}
          {summary?.manual_median_seconds == null
            ? "Not measured"
            : Math.round(summary.manual_median_seconds) + " sec"}{" "}
          · Assisted median:{" "}
          {summary?.assisted_median_seconds == null
            ? "Not measured"
            : Math.round(summary.assisted_median_seconds) + " sec"}
        </p>
        <p>
          Median-time reduction:{" "}
          {summary?.reduction_percent == null
            ? "Not measured"
            : summary.reduction_percent + "%"}{" "}
          · Decision agreement:{" "}
          {summary?.decision_agreement == null
            ? "Not measured"
            : Math.round(summary.decision_agreement * 100) + "%"}
        </p>
        <p className="muted">
          These are descriptive self-timed results, not proof of causal time
          savings. Unpaired trials are excluded from the timing comparison.
          Target: 15 → 3 minutes; never substitute that target for a
          measurement.
        </p>
      </section>
    </main>
  );
}
