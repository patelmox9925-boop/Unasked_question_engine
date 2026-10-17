import { useEffect, useId, useRef, useState } from "react";
import { CATEGORY_LABELS, LEVEL_LABELS, STATUS_HELP, STATUS_LABELS } from "../lib/format";
import type { Evidence, Finding, TriageEntry, TriageStatus } from "../types";
import { EvidenceList } from "./EvidenceList";

interface Props {
  finding: Finding;
  rank: number;
  open: boolean;
  selected: boolean;
  flash: boolean;
  triage: TriageEntry | undefined;
  onToggle: () => void;
  onSelect: () => void;
  onTriage: (entry: TriageEntry) => void;
  onEvidence: (evidence: Evidence) => void;
  onCopyQuestion: () => void;
  onCopyFinding: () => void;
  onAsk: () => void;
}

const DECISION_LABEL: Record<TriageStatus, string> = {
  open: "Not decided",
  accepted: "Accepted",
  dismissed: "Dismissed",
  resolved: "Resolved",
};

function ScoreItem({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {value}
        <span className="visually-hidden"> out of 10</span>
      </dd>
      <span className="scorebar" aria-hidden="true">
        <i style={{ width: `${value * 10}%` }} />
      </span>
    </div>
  );
}

export function FindingRow(props: Props) {
  const { finding: f, rank, open, selected, flash, triage, onToggle, onSelect, onTriage } = props;
  const bodyId = useId();
  const level = f.priority_level ?? "low";
  const score = f.priority_score !== null ? Math.round(f.priority_score) : null;
  const status: TriageStatus = triage?.status ?? "open";
  const [note, setNote] = useState(triage?.note ?? "");
  const rowRef = useRef<HTMLElement>(null);

  useEffect(() => setNote(triage?.note ?? ""), [triage?.note]);
  useEffect(() => {
    if (selected) rowRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [selected]);

  const decide = (next: TriageStatus) => onTriage({ status: status === next ? "open" : next, note });

  return (
    <article
      ref={rowRef}
      className={`finding finding--${level}${open ? " is-open" : ""}${selected ? " is-selected" : ""}${flash ? " finding--flash" : ""}${
        status === "dismissed" ? " is-dismissed" : ""
      }`}
      id={`finding-${f.id}`}
      onClick={onSelect}
    >
      <div className="finding__meta">
        <span className="finding__rank" aria-hidden="true">
          {rank}
        </span>
        <span
          className={`badge badge--${level}`}
          aria-label={`Priority ${LEVEL_LABELS[level]}${score !== null ? `, score ${score} out of 100` : ""}`}
        >
          {LEVEL_LABELS[level]}
          {score !== null ? ` ${score}` : ""}
        </span>
        <span className="tag">{CATEGORY_LABELS[f.category]}</span>
        <span className="tag tag--soft" title={STATUS_HELP[f.epistemic_status]}>
          {STATUS_LABELS[f.epistemic_status]}
        </span>
        {f.origin === "demo" && <span className="chip">Demo data</span>}
        {status !== "open" && <span className={`decision decision--${status}`}>{DECISION_LABEL[status]}</span>}
      </div>

      <h3 className="finding__title">
        <button type="button" className="finding__toggle" aria-expanded={open} aria-controls={bodyId} onClick={onToggle}>
          <svg className="finding__chev" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M7 4l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{f.title}</span>
        </button>
      </h3>

      <p className="question">
        <span className="visually-hidden">Unanswered question: </span>
        <mark>{f.critical_question}</mark>
      </p>

      {open && (
        <div className="finding__body" id={bodyId}>
          <div className="finding__cols">
            <div className="finding__main">
              <section>
                <h4>What we found</h4>
                <p>{f.explanation}</p>
              </section>
              <section>
                <h4>Why it matters</h4>
                <p>{f.why_it_matters}</p>
              </section>
              {f.why_overlooked && (
                <section>
                  <h4>Why it is easy to miss</h4>
                  <p>{f.why_overlooked}</p>
                </section>
              )}
              <section>
                <h4>Recommended action</h4>
                <p>{f.recommended_action}</p>
              </section>
              {f.disagreement_note && (
                <p className="note note--disagree">
                  <strong>Models disagreed. </strong>
                  {f.disagreement_note}
                </p>
              )}
            </div>

            <div className="finding__side">
              <section>
                <h4>Evidence</h4>
                <EvidenceList
                  evidence={f.evidence}
                  emptyText="No passage in your material directly supports this item."
                  onOpen={props.onEvidence}
                />
                {f.evidence_note && <p className="note" style={{ marginTop: 8 }}>{f.evidence_note}</p>}
              </section>
              <section>
                <h4>How it was ranked</h4>
                <dl className="scores">
                  <ScoreItem label="Impact" value={f.impact} />
                  <ScoreItem label="Likelihood" value={f.likelihood} />
                  <ScoreItem label="Urgency" value={f.urgency} />
                </dl>
                {f.score_explanation && <p className="hint" style={{ marginTop: 8 }}>{f.score_explanation}</p>}
                {f.raised_by.length > 0 && <p className="hint">Raised by: {f.raised_by.join(", ")}</p>}
              </section>
            </div>
          </div>

          <div className="triage" role="group" aria-label={`Your decision on ${f.title}`}>
            <div className="triage__buttons">
              {(["accepted", "resolved", "dismissed"] as const).map((s) => (
                <button key={s} type="button" className={`tbtn tbtn--${s}`} aria-pressed={status === s} onClick={() => decide(s)}>
                  {s === "accepted" ? "Accept, needs action" : s === "resolved" ? "Mark resolved" : "Dismiss"}
                </button>
              ))}
            </div>
            <label className="visually-hidden" htmlFor={`note-${f.id}`}>
              Note for finding {rank}
            </label>
            <input
              id={`note-${f.id}`}
              className="input triage__note"
              placeholder="Add a note (kept in the exported report)"
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onBlur={() => note !== (triage?.note ?? "") && onTriage({ status, note })}
              onKeyDown={(e) => e.key === "Enter" && onTriage({ status, note })}
            />
          </div>

          <div className="finding__actions">
            <button type="button" className="btn btn--quiet btn--small" onClick={props.onCopyQuestion}>
              Copy the question
            </button>
            <button type="button" className="btn btn--quiet btn--small" onClick={props.onCopyFinding}>
              Copy as text
            </button>
            {f.origin !== "demo" && (
              <button type="button" className="btn btn--quiet btn--small" onClick={props.onAsk}>
                Ask about this
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
