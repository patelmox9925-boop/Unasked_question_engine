import { useEffect, useState } from "react";
import type { AnalysisStatus, ProjectResponse, StepStatus } from "../types";

interface Props {
  project: ProjectResponse | null;
  status: AnalysisStatus | null;
  error: string | null;
  onRetry: () => void;
  onBack: () => void;
}

const STATUS_WORD: Record<StepStatus, string> = {
  pending: "Waiting",
  running: "In progress",
  done: "Done",
  skipped: "Skipped",
  failed: "Failed",
};

function Icon({ status }: { status: StepStatus }) {
  if (status === "running") {
    return (
      <span className="progress__icon progress__icon--running" aria-hidden="true">
        <span className="spinner" />
      </span>
    );
  }
  const glyph = { pending: "", done: "✓", skipped: "–", failed: "✕" }[status];
  return (
    <span className={`progress__icon progress__icon--${status}`} aria-hidden="true">
      {glyph}
    </span>
  );
}

export function ProgressView({ project, status, error, onRetry, onBack }: Props) {
  const failed = status?.state === "failed" || Boolean(error);
  const steps = status?.steps ?? [];
  const finished = steps.filter((s) => ["done", "skipped", "failed"].includes(s.status)).length;
  const percent = steps.length ? Math.round((finished / steps.length) * 100) : 0;
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (failed) return;
    const t = setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [failed]);
  const messages = [
    ...(project?.rejected ?? []).map((r) => `${r.filename}: ${r.message}`),
    ...(project?.documents ?? []).flatMap((d) => d.warnings.map((w) => `${d.filename}: ${w}`)),
  ];

  return (
    <div className="page page--narrow">
      <h1 className="page__title">{failed ? "The analysis stopped" : "Analyzing your project"}</h1>
      <p className="page__lead">
        {failed
          ? "Nothing was made up to fill the gap. You can try again or change the input."
          : "This can take a minute or two, depending on the models and the size of your material."}
      </p>

      {failed && (
        <div className="notice notice--error" role="alert" style={{ marginBottom: 18 }}>
          <strong>What happened</strong>
          {error ?? status?.error ?? "The analysis failed."}
        </div>
      )}

      {messages.length > 0 && (
        <div className="notice notice--warn" style={{ marginBottom: 18 }}>
          <strong>About your files</strong>
          <ul>
            {messages.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      <section className="card" aria-label="Analysis progress">
        {steps.length > 0 && !failed && (
          <div className="pbar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label="Analysis progress">
            <i style={{ width: `${Math.max(6, percent)}%` }} />
            <span>{seconds}s</span>
          </div>
        )}
        {steps.length === 0 ? (
          <p className="typing" role="status">
            <span className="spinner" aria-hidden="true" /> Reading your files…
          </p>
        ) : (
          <ol className="progress-list" aria-live="polite">
            {steps.map((step) => (
              <li key={step.key} data-status={step.status}>
                <Icon status={step.status} />
                <div>
                  <div className="progress__label">
                    {step.label} <span className="visually-hidden">: {STATUS_WORD[step.status]}</span>
                  </div>
                  {step.detail && <div className="progress__detail">{step.detail}</div>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {failed && (
        <div className="hero__actions" style={{ marginTop: 18 }}>
          {project && (
            <button type="button" className="btn" onClick={onRetry}>
              Run the analysis again
            </button>
          )}
          <button type="button" className="btn btn--quiet" onClick={onBack}>
            Change the input
          </button>
        </div>
      )}
    </div>
  );
}
