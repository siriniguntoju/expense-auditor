import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import Study from "./Study";
type Expense = {
  id: string;
  receipt_id: string | null;
  amount: string;
  currency: string;
  category: string;
};
type Report = {
  id: string;
  title: string;
  employee: string;
  expenses: Expense[];
};
type Flag = {
  rule: string;
  lines: string[];
  severity: string;
  explanation: string;
  evidence: Record<string, unknown>;
};
type Packet = {
  judgment?: {
    status: string;
    advice?: {
      assessment: string;
      explanation: string;
      question_for_reviewer: string;
    };
  };
  report: Report;
  flags: Flag[];
  intake_mode: string;
  policy_version?: string;
};
type Run = {
  created?: string;
  id: string;
  report_id: string;
  status: string;
  packet: Packet | null;
  events?: {
    seq: number;
    kind: string;
    body: Record<string, unknown>;
    created: string;
  }[];
};
type Event = {
  type: string;
  stepName?: string;
  message?: string;
  snapshot?: { stage: string; packet: Packet };
};
async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch(url, options);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: "Request failed" }));
    throw Error(e.detail || "Request failed");
  }
  return r.json();
}
function App() {
  const [study, setStudy] = useState(false),
    [mode, setMode] = useState("fixture_replay");
  const [config, setConfig] = useState({
    live_enabled: false,
    receipts: 200,
    reports: 50,
  });
  const [reports, setReports] = useState<Report[]>([]),
    [selected, setSelected] = useState("report-01");
  const [run, setRun] = useState<Run | null>(null),
    [history, setHistory] = useState<Run[]>([]);
  const [events, setEvents] = useState<Event[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [comment, setComment] = useState(""),
    [receipt, setReceipt] = useState<string | null>(null);
  const refresh = () => api<Run[]>("/api/runs").then(setHistory);
  useEffect(() => {
    Promise.all([
      api<Report[]>("/api/reports").then(setReports),
      api<typeof config>("/api/health").then(setConfig),
      refresh(),
    ]).catch((e) => setError(e.message));
  }, []);
  async function load(id: string) {
    setError("");
    setReceipt(null);
    setComment("");
    try {
      const r = await api<Run>("/api/runs/" + id);
      setRun(r);
      if (r.status === "failed")
        setError(
          String(
            r.events?.find((e) => e.kind === "RUN_ERROR")?.body.message ||
              "Analysis failed. Check the local agent services and retry.",
          ),
        );
      setSelected(r.report_id);
      setEvents(
        (r.events || [])
          .filter((e) => e.kind !== "review")
          .map((e) => e.body as Event),
      );
    } catch (e) {
      setError(String(e));
    }
  }
  async function analyze() {
    setBusy(true);
    setError("");
    setEvents([]);
    setReceipt(null);
    setComment("");
    const id = crypto.randomUUID();
    setRun({ id, report_id: selected, status: "running", packet: null });
    try {
      const response = await fetch("/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          threadId: selected,
          runId: id,
          messages: [],
          tools: [],
          context: [],
          forwardedProps: { report_id: selected, mode },
        }),
      });
      if (!response.ok || !response.body)
        throw Error("Could not start analysis");
      const reader = response.body.getReader(),
        decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder
          .decode(value, { stream: true })
          .replace(/\r\n/g, "\n");
        let end;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          const data = chunk
            .split("\n")
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trimStart())
            .join("\n");
          if (!data) continue;
          const ev: Event = JSON.parse(data);
          setEvents((old) => [...old, ev]);
          if (ev.snapshot)
            setRun((old) =>
              old ? { ...old, packet: ev.snapshot!.packet } : null,
            );
          if (ev.type === "RUN_ERROR")
            setError(ev.message || "Analysis failed");
        }
      }
      await load(id);
      await refresh();
    } catch (e) {
      setError(String(e));
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  async function review(action: string) {
    if (!run) return;
    setError("");
    setBusy(true);
    try {
      setRun(
        await api<Run>("/api/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: run.id, action, comment }),
        }),
      );
      setComment("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const report = run?.packet?.report || reports.find((r) => r.id === selected);
  const pending = run?.status === "pending_review";
  if (study) return <Study onClose={() => setStudy(false)} />;
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <span className="mark">ea</span> Expense Auditor
        </div>
        <p className="eyebrow">REVIEW WORKSPACE</p>
        <h2>Expense reports</h2>
        <p className="muted">
          {reports.length} synthetic cases · {config.receipts} receipts
        </p>
        <nav>
          {reports.map((r) => (
            <button
              disabled={busy}
              className={"report " + (selected === r.id ? "active" : "")}
              key={r.id}
              onClick={() => {
                setSelected(r.id);
                setRun(null);
                setEvents([]);
                setReceipt(null);
                setError("");
              }}
            >
              <span>{r.id.replace("report-", "#")}</span>
              <strong>{r.title}</strong>
              <small>{r.employee}</small>
            </button>
          ))}
        </nav>
        <div className="aside-note">
          Portfolio demo
          <br />
          <b>No real expenses. No payments.</b>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">MULTI-AGENT EXPENSE AUDITOR</p>
            <h1>A clearer path to review.</h1>
            <p className="muted">
              Evidence first. A person makes the final decision.
            </p>
          </div>
          <button disabled={busy} onClick={() => setStudy(true)}>
            Timed review study
          </button>
        </header>
        <div className="notice">
          <b>{run?.packet?.intake_mode || mode}</b>{" "}
          {mode === "fixture_replay"
            ? "Synthetic label replay measures the checking workflow, not extraction accuracy."
            : mode === "gemini_cached"
              ? "Reuses saved real Gemini extractions; missing cache entries fail without making calls."
              : "Gemini reads synthetic receipt images. Requires a confirmed free-tier project; stops on provider errors."}
          <label className="mode-picker">
            Extraction mode{" "}
            <select
              disabled={busy}
              value={mode}
              onChange={(e) => {
                setMode(e.target.value);
                setRun(null);
                setEvents([]);
              }}
            >
              <option value="fixture_replay">Offline fixture replay</option>
              <option value="gemini_cached">Cached Gemini results</option>
              <option value="gemini_live" disabled={!config.live_enabled}>
                Live Gemini {config.live_enabled ? "" : "(not enabled)"}
              </option>
            </select>
          </label>
        </div>
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        <section className="report-head">
          <div>
            <p className="eyebrow">{selected.toUpperCase()}</p>
            <h2>{report?.title || "Loading report…"}</h2>
            <span className="muted">
              {report?.employee} · {report?.expenses.length || 0} expense lines
            </span>
          </div>
          <button
            className="primary"
            disabled={busy || !report}
            onClick={analyze}
          >
            {busy ? "Working…" : "Analyze report ↗"}
          </button>
        </section>
        <div className="grid">
          <section className="card">
            <div className="section-title">
              <h3>Expense evidence</h3>
              <span className="pill">
                {run?.status.replaceAll("_", " ") || "Ready to analyze"}
              </span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Line</th>
                  <th>Category</th>
                  <th>Claim</th>
                  <th>Receipt</th>
                </tr>
              </thead>
              <tbody>
                {report?.expenses.map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td>{e.category}</td>
                    <td className="amount">
                      {e.currency} {e.amount}
                    </td>
                    <td>
                      {e.receipt_id ? (
                        <button
                          className="link"
                          onClick={() => setReceipt(e.receipt_id)}
                        >
                          View {e.receipt_id} ↗
                        </button>
                      ) : (
                        <span className="missing">Missing</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {receipt && (
              <div className="receipt">
                <button onClick={() => setReceipt(null)}>Close receipt</button>
                <img
                  src={"/api/receipts/" + receipt}
                  alt={"Synthetic receipt " + receipt}
                />
              </div>
            )}
            {run?.packet?.judgment?.advice && (
              <article className="finding review">
                <b>Model advisory · human decision required</b>
                <p>{run.packet.judgment.advice.explanation}</p>
                <p>{run.packet.judgment.advice.question_for_reviewer}</p>
              </article>
            )}
            <h3 className="spaced">
              Findings{" "}
              <span className="count">{run?.packet?.flags.length || 0}</span>
            </h3>
            {!run && (
              <p className="empty">
                Run the agents to collect policy checks and audit evidence.
              </p>
            )}
            {run?.packet?.flags.map((f, i) => (
              <article className={"finding " + f.severity} key={i}>
                <div>
                  <b>{f.rule.replaceAll("_", " ")}</b>
                  <span className="pill">{f.severity}</span>
                </div>
                <p>{f.explanation}</p>
                <small>Lines: {f.lines.join(", ")}</small>
                <details>
                  <summary>Supporting evidence</summary>
                  <pre>{JSON.stringify(f.evidence, null, 2)}</pre>
                </details>
              </article>
            ))}
            {run?.status !== "running" && run?.packet?.flags.length === 0 && (
              <p className="clear">
                No issues found by the configured rules. Human review is still
                required.
              </p>
            )}
          </section>
          <section className="card">
            <h3>Agent timeline</h3>
            <p className="muted">A2A agents · MCP tools · AG-UI stream</p>
            <ol className="timeline">
              {["intake", "policy", "audit"].map((step, i) => {
                const done = events.some(
                    (e) => e.type === "STEP_FINISHED" && e.stepName === step,
                  ),
                  started = events.some(
                    (e) => e.type === "STEP_STARTED" && e.stepName === step,
                  );
                return (
                  <li key={step}>
                    <span className={done ? "done" : ""}>
                      {done ? "✓" : i + 1}
                    </span>
                    <div>
                      <b>
                        {step === "intake"
                          ? "Receipt intake"
                          : step === "policy"
                            ? "Policy & currency"
                            : "Audit checks"}
                      </b>
                      <small>
                        {done ? "Completed" : started ? "Running" : "Waiting"}
                      </small>
                    </div>
                  </li>
                );
              })}
            </ol>
            <details>
              <summary>Protocol events ({events.length})</summary>
              <div className="event-list">
                {events.map((e, i) => (
                  <div key={i}>
                    {e.type} {e.stepName || ""}
                  </div>
                ))}
              </div>
            </details>
            <hr />
            <h3>Reviewer decision</h3>
            <p className="muted">
              Approval records your review only. It never transfers money.
            </p>
            <label htmlFor="comment">Review note</label>
            <textarea
              id="comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              maxLength={1000}
              placeholder="Add context for the review history…"
            />
            <div className="actions">
              <button
                className="primary"
                disabled={!pending || busy}
                onClick={() => review("approve")}
              >
                Approve
              </button>
              <button
                className="reject"
                disabled={!pending || busy}
                onClick={() => review("reject")}
              >
                Reject
              </button>
              <button
                disabled={!run?.packet || busy || !comment.trim()}
                onClick={() => review("comment")}
              >
                Save note
              </button>
            </div>
            {run?.events
              ?.filter((e) => e.kind === "review")
              .map((e) => (
                <div className="review-note" key={e.seq}>
                  <b>{String(e.body.action)}</b>
                  <p>{String(e.body.comment || "No note added.")}</p>
                  <small>{new Date(e.created).toLocaleString()}</small>
                </div>
              ))}
          </section>
        </div>
        <section className="card history">
          <h3>Recent runs</h3>
          <p className="muted">
            Saved in the configured database. Open a run to replay its evidence
            and decisions.
          </p>
          <div>
            {history.map((r) => (
              <button disabled={busy} key={r.id} onClick={() => load(r.id)}>
                {r.report_id} · {r.status.replaceAll("_", " ")}{" "}
                <small>
                  {new Date(r.created || Date.now()).toLocaleTimeString()}
                </small>
              </button>
            ))}
          </div>
        </section>
        <footer>
          Synthetic data only · Policy v2 · Fixed demonstration exchange rates ·
          Local development app
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
