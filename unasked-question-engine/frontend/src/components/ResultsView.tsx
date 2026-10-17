import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { copyText } from "../lib/clipboard";
import { applyFilters, emptyFilters, isFiltering } from "../lib/filters";
import { LEVEL_LABELS, LEVEL_ORDER } from "../lib/format";
import { readStored, writeStored } from "../lib/storage";
import { findingAsText } from "../lib/text";
import type { AnalysisResult, Evidence, TriageEntry, TriageStatus } from "../types";
import { ChatPanel, type ChatEntry } from "./ChatPanel";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { EvidenceList } from "./EvidenceList";
import { ExportBar } from "./ExportBar";
import { FilterBar } from "./FilterBar";
import { FindingRow } from "./FindingRow";
import { RiskMatrix } from "./RiskMatrix";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { useToast } from "./Toasts";

type TabKey = "findings" | "understanding" | "questions" | "ask";
const TIP_KEY = "uqe-tip-seen";

function Overview({ result, selectedCell, onCell }: { result: AnalysisResult; selectedCell: ReturnType<typeof emptyFilters>["cell"]; onCell: (c: ReturnType<typeof emptyFilters>["cell"]) => void }) {
  const risk = result.risk_summary;
  const total = result.findings.length;
  return (
    <section className="card overview" aria-labelledby="summary-title">
      <div className="overview__text">
        {result.origin === "demo" && (
          <p className="demo-banner">Demo data: these are predefined sample results, not an analysis of your project.</p>
        )}
        <div className="summary__level">
          <h2 className="summary__title" id="summary-title">
            Overall risk
          </h2>
          {risk && total > 0 && <span className={`badge badge--${risk.overall_level}`}>{LEVEL_LABELS[risk.overall_level]}</span>}
        </div>
        {result.overall_summary && <p className="summary__text">{result.overall_summary}</p>}
        {risk && (
          <>
            <p className="summary__text summary__text--muted">{risk.explanation}</p>
            {total > 0 && (
              <>
                <div className="meter" role="img" aria-label={LEVEL_ORDER.map((l) => `${risk.counts[l]} ${l}`).join(", ")}>
                  {LEVEL_ORDER.map((l) =>
                    risk.counts[l] > 0 ? <span key={l} className={`bg-${l}`} style={{ width: `${(risk.counts[l] / total) * 100}%` }} /> : null,
                  )}
                </div>
                <ul className="legend" aria-label="Findings by severity">
                  {LEVEL_ORDER.map((l) => (
                    <li key={l}>
                      <span className={`swatch bg-${l}`} aria-hidden="true" />
                      {LEVEL_LABELS[l]}: {risk.counts[l]}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}

        {result.warnings.length > 0 && (
          <div className="notice notice--warn">
            <strong>Read this first</strong>
            <ul>
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <details className="disclosure">
          <summary>How findings are ranked</summary>
          <p>{risk?.formula}</p>
        </details>
        <details className="disclosure">
          <summary>Models consulted and perspectives applied</summary>
          {result.models_consulted.length === 0 ? (
            <p>No live models were used for these results.</p>
          ) : (
            <ul className="chips" aria-label="Models">
              {result.models_consulted.map((m, i) => (
                <li key={i} className={`chip${m.succeeded ? "" : " chip--failed"}`}>
                  Model {m.role}: {m.provider}/{m.model}
                  {m.used_as_fallback ? " (fallback)" : ""}
                  {m.succeeded ? "" : " failed, not consulted"}
                </li>
              ))}
            </ul>
          )}
          {result.perspectives.length > 0 && (
            <ul className="chips" aria-label="Perspectives">
              {result.perspectives.map((p) => (
                <li key={p.key} className="chip" title={p.reason}>
                  {p.name}
                </li>
              ))}
            </ul>
          )}
        </details>
      </div>
      {total > 0 && (
        <div className="overview__matrix">
          <RiskMatrix findings={result.findings} selected={selectedCell} onSelect={onCell} />
        </div>
      )}
    </section>
  );
}

export function ResultsView({ result }: { result: AnalysisResult }) {
  const toast = useToast();
  const [tab, setTab] = useState<TabKey>("findings");
  const [filters, setFilters] = useState(emptyFilters);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [flashId, setFlashId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [prefill, setPrefill] = useState<{ text: string; key: number } | null>(null);
  const [triage, setTriage] = useState<Record<string, TriageEntry>>({});
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [showKeys, setShowKeys] = useState(false);
  const [tipSeen, setTipSeen] = useState(() => readStored(TIP_KEY) === "1");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getTriage(result.project_id)
      .then((t) => !cancelled && setTriage(t))
      .catch(() => undefined); // decisions are an extra; the results still work without them
    return () => {
      cancelled = true;
    };
  }, [result.project_id]);

  const visible = useMemo(() => applyFilters(result.findings, filters, triage), [result.findings, filters, triage]);
  const reviewed = result.findings.filter((f) => (triage[f.id]?.status ?? "open") !== "open").length;
  const activeId = selectedId && visible.some((f) => f.id === selectedId) ? selectedId : (visible[0]?.id ?? null);

  const tabs: { key: TabKey; label: string; count?: number }[] = [
    { key: "findings", label: "Findings", count: result.findings.length },
    ...(result.understanding ? [{ key: "understanding" as const, label: "What we understood" }] : []),
    { key: "questions", label: "Unanswered questions", count: result.unanswered_questions.length },
    { key: "ask", label: "Ask a follow-up" },
  ];

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const openFinding = (id: string) => {
    setTab("findings");
    setFilters(emptyFilters());
    setExpanded((prev) => new Set(prev).add(id));
    setSelectedId(id);
    setFlashId(id);
  };

  useEffect(() => {
    if (!flashId || tab !== "findings") return;
    document.getElementById(`finding-${flashId}`)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    const timer = setTimeout(() => setFlashId(null), 1800);
    return () => clearTimeout(timer);
  }, [flashId, tab]);

  const decide = useCallback(
    async (findingId: string, entry: TriageEntry) => {
      const before = triage[findingId];
      setTriage((prev) => ({ ...prev, [findingId]: entry }));
      try {
        await api.setTriage(result.project_id, findingId, entry);
      } catch (err) {
        setTriage((prev) => {
          const next = { ...prev };
          if (before) next[findingId] = before;
          else delete next[findingId];
          return next;
        });
        toast.show(err instanceof ApiError ? err.message : "Your decision could not be saved.", "error");
      }
    },
    [result.project_id, toast, triage],
  );

  const copy = async (text: string, done: string) => toast.show((await copyText(text)) ? done : "Copy was blocked by the browser.", "info");

  const askAbout = (title: string) => {
    setPrefill({ text: `About "${title}": `, key: Date.now() });
    setTab("ask");
  };

  // keyboard shortcuts for the findings list
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName ?? "";
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || target?.isContentEditable) return;
      if (e.key === "?") {
        e.preventDefault();
        setShowKeys(true);
        return;
      }
      if (e.key === "Escape") {
        if (filters.cell) setFilters((f) => ({ ...f, cell: null }));
        return;
      }
      if (tab !== "findings") return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      const index = visible.findIndex((f) => f.id === activeId);
      const current = index >= 0 ? visible[index] : undefined;
      if (e.key === "j" || e.key === "k") {
        const next = visible[Math.min(visible.length - 1, Math.max(0, index + (e.key === "j" ? 1 : -1)))];
        if (next) setSelectedId(next.id);
        return;
      }
      if (!current) return;
      const interactive = ["BUTTON", "A", "SUMMARY"].includes(tag);
      if (e.key === "o" || (e.key === "Enter" && !interactive)) {
        e.preventDefault();
        toggle(current.id);
      } else if (e.key === "a" || e.key === "d" || e.key === "r") {
        const status: TriageStatus = e.key === "a" ? "accepted" : e.key === "d" ? "dismissed" : "resolved";
        const now = triage[current.id];
        void decide(current.id, { status: now?.status === status ? "open" : status, note: now?.note ?? "" });
      } else if (e.key === "c") {
        void copy(current.critical_question, "Question copied.");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const onTabKey = (event: React.KeyboardEvent, index: number) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = tabs[(index + delta + tabs.length) % tabs.length];
    setTab(next.key);
    document.getElementById(`tab-${next.key}`)?.focus();
  };

  const dismissTip = () => {
    setTipSeen(true);
    writeStored(TIP_KEY, "1");
  };

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Analysis results</h1>
          <p className="page__lead">
            {result.findings.length === 0
              ? "No findings were produced for this material."
              : `${result.findings.length} findings, ranked by priority. ${reviewed} of ${result.findings.length} reviewed.`}
          </p>
        </div>
        <button type="button" className="btn btn--quiet btn--small" onClick={() => setShowKeys(true)}>
          Keyboard shortcuts
        </button>
      </div>

      {!tipSeen && result.findings.length > 0 && (
        <p className="tip" role="note">
          <span>
            Tip: click a square in the matrix to filter, open a finding to see its evidence, then accept, resolve or
            dismiss it. Press <kbd>?</kbd> for shortcuts.
          </span>
          <button type="button" className="link-btn" onClick={dismissTip}>
            Got it
          </button>
        </p>
      )}

      <Overview
        result={result}
        selectedCell={filters.cell}
        onCell={(cell) => {
          setFilters((f) => ({ ...f, cell }));
          setTab("findings");
        }}
      />

      <div className="toolbar">
        <div className="tabs" role="tablist" aria-label="Results sections">
          {tabs.map((t, i) => (
            <button
              key={t.key}
              id={`tab-${t.key}`}
              type="button"
              role="tab"
              className="tab"
              aria-selected={tab === t.key}
              aria-controls={`panel-${t.key}`}
              tabIndex={tab === t.key ? 0 : -1}
              onClick={() => setTab(t.key)}
              onKeyDown={(e) => onTabKey(e, i)}
            >
              {t.label}
              {t.count !== undefined && <span className="tab__count">{t.count}</span>}
            </button>
          ))}
        </div>
        <ExportBar projectId={result.project_id} />
      </div>

      {tab === "findings" && (
        <div role="tabpanel" id="panel-findings" aria-labelledby="tab-findings">
          {result.findings.length === 0 ? (
            <div className="empty">
              <h3>Nothing to show</h3>
              <p>The models did not report any findings. Try adding more detail about scope, budget, timeline and users.</p>
            </div>
          ) : (
            <>
              <FilterBar ref={searchRef} findings={result.findings} triage={triage} filters={filters} onChange={setFilters} shown={visible.length} />
              <div className="list-head">
                <span />
                <span>
                  <button type="button" className="link-btn" onClick={() => setExpanded(new Set(visible.map((f) => f.id)))}>
                    Expand all
                  </button>
                  {expanded.size > 0 && (
                    <button type="button" className="link-btn" onClick={() => setExpanded(new Set())}>
                      Collapse all
                    </button>
                  )}
                </span>
              </div>
              {visible.length === 0 ? (
                <div className="empty">
                  <h3>No findings match these filters</h3>
                  <p>Remove a filter to see more.</p>
                  {isFiltering(filters) && (
                    <button type="button" className="btn btn--quiet" onClick={() => setFilters({ ...emptyFilters(), sort: filters.sort })}>
                      Clear filters
                    </button>
                  )}
                </div>
              ) : (
                <div className="finding-list">
                  {visible.map((f, i) => (
                    <FindingRow
                      key={f.id}
                      finding={f}
                      rank={i + 1}
                      open={expanded.has(f.id)}
                      selected={activeId === f.id}
                      flash={flashId === f.id}
                      triage={triage[f.id]}
                      onToggle={() => toggle(f.id)}
                      onSelect={() => setSelectedId(f.id)}
                      onTriage={(entry) => decide(f.id, entry)}
                      onEvidence={setEvidence}
                      onCopyQuestion={() => copy(f.critical_question, "Question copied.")}
                      onCopyFinding={() => copy(findingAsText(f), "Finding copied as text.")}
                      onAsk={() => askAbout(f.title)}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === "understanding" && result.understanding && (
        <div role="tabpanel" id="panel-understanding" aria-labelledby="tab-understanding" className="stack">
          <section className="card">
            <h2 className="section-title">What the models understood your project to be</h2>
            <p className="summary__text">{result.understanding.summary}</p>
            <p className="hint">If something here is wrong, the findings built on it may be wrong too. Correct your input and run again.</p>
          </section>
          {result.understanding.facts.length > 0 && (
            <section>
              <h2 className="section-title">Facts the analysis relied on</h2>
              <ul className="facts">
                {result.understanding.facts.map((fact, i) => (
                  <li key={i}>
                    <p>
                      {fact.statement} <span className="tag tag--soft">{fact.kind}</span>
                    </p>
                    <EvidenceList evidence={fact.evidence} onOpen={setEvidence} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {result.understanding.open_items.length > 0 && (
            <section>
              <h2 className="section-title">Left open in the material</h2>
              <ul className="questions">
                {result.understanding.open_items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {tab === "questions" && (
        <div role="tabpanel" id="panel-questions" aria-labelledby="tab-questions" className="stack">
          {result.unanswered_questions.length === 0 && result.findings.length === 0 ? (
            <div className="empty">
              <h3>No questions yet</h3>
              <p>Questions appear here when the analysis finds gaps in the material.</p>
            </div>
          ) : (
            <>
              {result.unanswered_questions.length > 0 && (
                <section>
                  <h2 className="section-title">Questions the material does not answer</h2>
                  <ul className="questions">
                    {result.unanswered_questions.map((q) => (
                      <li key={q}>
                        {q}
                        <span className="from">
                          <button type="button" className="link-btn" onClick={() => copy(q, "Question copied.")}>
                            Copy
                          </button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {result.findings.length > 0 && (
                <section>
                  <h2 className="section-title">Question behind each finding</h2>
                  <ul className="questions">
                    {result.findings.map((f) => (
                      <li key={f.id}>
                        {f.critical_question}
                        <span className="from">
                          From &ldquo;{f.title}&rdquo;{" "}
                          <button type="button" className="link-btn" onClick={() => openFinding(f.id)}>
                            View finding
                          </button>{" "}
                          <button type="button" className="link-btn" onClick={() => copy(f.critical_question, "Question copied.")}>
                            Copy
                          </button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      )}

      {tab === "ask" && (
        <div role="tabpanel" id="panel-ask" aria-labelledby="tab-ask">
          {result.origin === "demo" ? (
            <div className="empty">
              <h3>Follow-up questions need a live model</h3>
              <p>Demo results are predefined, so there is nothing for a model to ground its answers in.</p>
            </div>
          ) : (
            <ChatPanel
              projectId={result.project_id}
              findings={result.findings}
              entries={chat}
              onEntries={(updater) => setChat(updater)}
              onOpenFinding={openFinding}
              onEvidence={setEvidence}
              prefill={prefill}
            />
          )}
        </div>
      )}

      <EvidenceDrawer projectId={result.project_id} evidence={evidence} onClose={() => setEvidence(null)} />
      <ShortcutsDialog open={showKeys} onClose={() => setShowKeys(false)} />
    </div>
  );
}
