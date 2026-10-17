import { useEffect, useId, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { copyText } from "../lib/clipboard";
import { GROUNDING_LABELS } from "../lib/format";
import { shouldAnimate } from "../lib/text";
import type { ChatMessage, ChatResponse, Evidence, Finding } from "../types";
import { EvidenceList } from "./EvidenceList";
import { Markdown } from "./Markdown";
import { useToast } from "./Toasts";

export interface ChatEntry {
  question: string;
  response?: ChatResponse;
  error?: string;
}

interface Props {
  projectId: string;
  findings: Finding[];
  entries: ChatEntry[];
  onEntries: (updater: (prev: ChatEntry[]) => ChatEntry[]) => void;
  onOpenFinding: (id: string) => void;
  onEvidence: (evidence: Evidence) => void;
  prefill?: { text: string; key: number } | null;
}

/** Reveals an answer word by word so long answers feel alive. Skipped for reduced motion and in tests. */
function Reveal({ text, onDone }: { text: string; onDone: () => void }) {
  const words = text.split(/(\s+)/);
  const [shown, setShown] = useState(shouldAnimate() ? 0 : words.length);
  useEffect(() => {
    if (shown >= words.length) {
      onDone();
      return;
    }
    const t = setTimeout(() => setShown((n) => Math.min(words.length, n + 8)), 22);
    return () => clearTimeout(t);
  }, [shown, words.length, onDone]);
  return <Markdown>{words.slice(0, shown).join("")}</Markdown>;
}

function suggestionsFor(findings: Finding[]): string[] {
  const top = findings[0];
  const list = [
    "Which finding should we address first, and why?",
    "What assumptions does the plan rely on most?",
  ];
  if (top) list.splice(1, 0, `What is the evidence behind "${top.title}"?`);
  if (findings.some((f) => f.category === "contradiction")) list.push("Where does the material contradict itself?");
  return list.slice(0, 4);
}

export function ChatPanel({ projectId, findings, entries, onEntries, onOpenFinding, onEvidence, prefill }: Props) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Set<number>>(() => new Set(entries.map((_, i) => i)));
  const inputId = useId();
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const titleOf = (id: string) => findings.find((f) => f.id === id)?.title ?? id;

  useEffect(() => {
    if (prefill) {
      setText(prefill.text);
      inputRef.current?.focus();
    }
  }, [prefill]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const history: ChatMessage[] = entries
      .filter((e) => e.response)
      .slice(-3)
      .flatMap((e) => [
        { role: "user" as const, content: e.question },
        { role: "assistant" as const, content: e.response!.answer.slice(0, 3900) },
      ]);
    onEntries((prev) => [...prev, { question: q }]);
    setText("");
    setBusy(true);
    try {
      const response = await api.chat(projectId, q, history);
      onEntries((prev) => prev.map((e, i) => (i === prev.length - 1 ? { ...e, response } : e)));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "The question could not be answered.";
      onEntries((prev) => prev.map((e, i) => (i === prev.length - 1 ? { ...e, error: message } : e)));
      setDone((d) => new Set(d).add(entries.length));
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView?.({ block: "nearest" }), 0);
    }
  };

  const lastIndex = entries.length - 1;

  return (
    <div className="chat">
      <p className="hint">
        Answers come only from your uploaded material and the findings. When the material does not say, the answer
        says so.
      </p>

      <div className="chat__log" aria-live="polite">
        {entries.length === 0 && (
          <div className="suggestions" role="group" aria-label="Suggested questions">
            {suggestionsFor(findings).map((s) => (
              <button key={s} type="button" onClick={() => ask(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
        )}

        {entries.map((entry, index) => {
          const finished = done.has(index) || !shouldAnimate();
          return (
            <div key={index} className="stack">
              <div className="msg msg--user">
                <span className="visually-hidden">You asked: </span>
                {entry.question}
              </div>
              {entry.response && (
                <div className="msg">
                  <span className="visually-hidden">Answer: </span>
                  {finished ? (
                    <Markdown>{entry.response.answer}</Markdown>
                  ) : (
                    <Reveal text={entry.response.answer} onDone={() => setDone((d) => new Set(d).add(index))} />
                  )}
                  {finished && (
                    <>
                      {entry.response.evidence.length > 0 && <EvidenceList evidence={entry.response.evidence} onOpen={onEvidence} />}
                      <div className="msg__meta">
                        <strong className={`ground ground--${entry.response.grounding}`}>{GROUNDING_LABELS[entry.response.grounding]}</strong>
                        {entry.response.finding_ids.map((id) => (
                          <button key={id} type="button" className="link-btn" onClick={() => onOpenFinding(id)}>
                            Related finding: {titleOf(id)}
                          </button>
                        ))}
                        <button
                          type="button"
                          className="link-btn"
                          onClick={async () => toast.show((await copyText(entry.response!.answer)) ? "Answer copied." : "Copy was blocked by the browser.", "info")}
                        >
                          Copy answer
                        </button>
                        <span>
                          Model {entry.response.model.role} ({entry.response.model.provider}/{entry.response.model.model})
                        </span>
                      </div>
                      {entry.response.warnings.map((w) => (
                        <p key={w} className="hint" style={{ marginTop: 6 }}>
                          {w}
                        </p>
                      ))}
                      {index === lastIndex && (entry.response.follow_ups?.length ?? 0) > 0 && (
                        <div className="suggestions" role="group" aria-label="Suggested follow-ups">
                          {entry.response.follow_ups!.map((s) => (
                            <button key={s} type="button" onClick={() => ask(s)} disabled={busy}>
                              {s}
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
              {entry.error && (
                <div className="notice notice--error" role="alert">
                  <strong>No answer</strong>
                  {entry.error}
                </div>
              )}
              {!entry.response && !entry.error && (
                <p className="typing" role="status">
                  <span className="spinner" aria-hidden="true" /> Looking through your material…
                </p>
              )}
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      <form
        className="chat__form"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <label className="field-label" htmlFor={inputId}>
          Ask a follow-up question
        </label>
        <textarea
          id={inputId}
          ref={inputRef}
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              ask(text);
            }
          }}
          placeholder="For example: what happens if the launch date slips?"
        />
        <div className="chat__row">
          <span className="hint">Press Ctrl+Enter to send.</span>
          {entries.length > 0 && (
            <button type="button" className="link-btn" onClick={() => onEntries(() => [])} disabled={busy}>
              Clear conversation
            </button>
          )}
          <button type="submit" className="btn" disabled={busy || text.trim() === ""}>
            {busy ? "Asking…" : "Ask"}
          </button>
        </div>
      </form>
    </div>
  );
}
