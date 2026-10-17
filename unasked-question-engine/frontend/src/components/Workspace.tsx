import { useId, useRef, useState } from "react";
import { formatBytes, validateFiles } from "../lib/format";
import type { ConfigStatus } from "../types";

interface Props {
  config: ConfigStatus | null;
  configError: string | null;
  busy: boolean;
  error: string | null;
  onSubmit: (description: string, files: File[]) => void;
  onRetryConfig: () => void;
  onDemo?: () => void;
  onSettings?: () => void;
}

const DEFAULT_LIMITS = { max_upload_mb: 10, max_files: 10, max_description_chars: 20000 };

export function Workspace({ config, configError, busy, error, onSubmit, onRetryConfig, onDemo, onSettings }: Props) {
  const limits = config?.limits ?? DEFAULT_LIMITS;
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const descId = useId();
  const fileHintId = useId();

  const tooLong = description.length > limits.max_description_chars;
  const hasInput = description.trim().length > 0 || files.length > 0;
  const live = config?.live_analysis_available ?? false;

  let blocker: string | null = null;
  if (!config && !configError) blocker = "Checking server configuration…";
  else if (configError) blocker = "The server could not be reached.";
  else if (!live) blocker = "Add an API key under Models to analyze.";
  else if (!hasInput) blocker = "Add a description or at least one file.";
  else if (tooLong) blocker = "The description is too long.";

  const addFiles = (incoming: FileList | File[]) => {
    const merged = [...files];
    for (const f of Array.from(incoming)) {
      if (!merged.some((m) => m.name === f.name && m.size === f.size)) merged.push(f);
    }
    const { accepted, problems: found } = validateFiles(merged, limits);
    setFiles(accepted);
    setProblems(found);
    if (inputRef.current) inputRef.current.value = "";
  };

  const TEMPLATES: [string, string][] = [
    ["Software launch", "We are building a web app for [users] and plan to launch in [month]. Team: [size]. Budget: [amount]. Key systems: [list]. Decisions already made: [list]."],
    ["Event or campaign", "We are running [event/campaign] on [date] for about [number] people. Budget: [amount]. Team and vendors: [list]. Success means: [goal]."],
    ["Process change", "We are changing how [process] works. Today: [current way]. Planned: [new way]. Teams affected: [list]. Rollout date: [date]."],
  ];

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (blocker || busy) return;
    onSubmit(description, files);
  };

  return (
    <div className="page">
      <h1 className="page__title">Analyze a project</h1>
      <p className="page__lead">
        Describe the project, upload its documents, or do both. Nothing is analysed until you press the button.
      </p>

      <form className="workspace" onSubmit={submit} noValidate>
        <div className="stack">
          {error && (
            <div className="notice notice--error" role="alert">
              <strong>That did not work</strong>
              {error}
            </div>
          )}

          <section className="card" aria-labelledby={`${descId}-h`}>
            <h2 id={`${descId}-h`}>Project description</h2>
            <label className="field-label" htmlFor={descId}>
              What are you building, and how is it supposed to work?
            </label>
            {description === "" && (
              <div className="suggestions" role="group" aria-label="Start from a template">
                {TEMPLATES.map(([name, text]) => (
                  <button key={name} type="button" onClick={() => setDescription(text)}>
                    {name} template
                  </button>
                ))}
              </div>
            )}
            <textarea
              id={descId}
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Goals, scope, timeline, budget, team, users, systems involved, decisions already made…"
              aria-describedby={`${descId}-count`}
            />
            <div id={`${descId}-count`} className={`counter${tooLong ? " counter--over" : ""}`}>
              {description.length.toLocaleString()} / {limits.max_description_chars.toLocaleString()} characters
            </div>
          </section>

          <section className="card" aria-labelledby="files-h">
            <h2 id="files-h">Documents and datasets</h2>
            <div
              className={`drop${dragging ? " drop--active" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                addFiles(e.dataTransfer.files);
              }}
            >
              <span className="drop__title">Drop files here or choose files</span>
              <span id={fileHintId} className="hint">
                PDF, DOCX, TXT, Markdown or CSV. Up to {limits.max_files} files, {limits.max_upload_mb} MB each.
              </span>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.md,.markdown,.csv"
                aria-label="Choose documents to upload"
                aria-describedby={fileHintId}
                onChange={(e) => e.target.files && addFiles(e.target.files)}
              />
            </div>

            {problems.length > 0 && (
              <div className="notice notice--warn" role="alert" style={{ marginTop: 12 }}>
                <strong>Some files were not added</strong>
                <ul>
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            )}

            {files.length > 0 && (
              <ul className="files" aria-label="Selected files">
                {files.map((f) => (
                  <li key={`${f.name}-${f.size}`}>
                    <span>
                      <span className="files__name">{f.name}</span>
                      <span className="files__size">{formatBytes(f.size)}</span>
                    </span>
                    <button
                      type="button"
                      className="link-btn"
                      onClick={() => setFiles(files.filter((x) => x !== f))}
                      aria-label={`Remove ${f.name}`}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="stack" aria-label="Analysis setup">
          <section className="card">
            <div className="settings-block__head">
              <h2>Models</h2>
              {onSettings && (
                <button type="button" className="link-btn" onClick={onSettings}>
                  Change
                </button>
              )}
            </div>
            {configError && (
              <div className="notice notice--error" role="alert">
                <strong>Server unavailable</strong>
                {configError}{" "}
                <button type="button" className="link-btn" onClick={onRetryConfig}>
                  Try again
                </button>
              </div>
            )}
            {!config && !configError && <p className="hint">Checking…</p>}
            {config && (
              <>
                <ul className="roles">
                  {(["A", "B", "C"] as const).map((role) => {
                    const r = config.roles[role];
                    const ready = r.primary_ready || r.fallback_ready;
                    return (
                      <li key={role} className="role">
                        <span className="role__name">
                          <span className={`dot${ready ? " dot--ok" : ""}`} aria-hidden="true" />
                          Model {role}: {ready ? "ready" : "not configured"}
                        </span>
                        <span className="role__task">{r.task}</span>
                        {ready && r.primary_ready && (
                          <span className="hint">
                            {r.provider} / {r.model}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {!live && (
                  <div className="notice notice--warn" style={{ marginTop: 14 }}>
                    <strong>Analysis is unavailable</strong>
                    Model A needs a provider, a model name and an API key.{" "}
                    {onSettings && (
                      <button type="button" className="link-btn" onClick={onSettings}>
                        Set up models
                      </button>
                    )}
                    {onDemo && (
                      <>
                        {" "}
                        Meanwhile you can explore a sample project with predefined, clearly labelled results.{" "}
                        <button type="button" className="link-btn" onClick={onDemo} disabled={busy}>
                          Try the sample project
                        </button>
                      </>
                    )}
                  </div>
                )}
                {live && !config.all_roles_ready && (
                  <p className="hint" style={{ marginTop: 12 }}>
                    Models without a configuration are skipped, and the results say so.
                  </p>
                )}
              </>
            )}
          </section>

          <div>
            <button type="submit" className="btn" disabled={Boolean(blocker) || busy} style={{ width: "100%" }}>
              {busy ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Uploading…
                </>
              ) : (
                "Analyze project"
              )}
            </button>
            <p className="hint" style={{ marginTop: 8 }} aria-live="polite">
              {blocker ?? "Your files are read on the server and kept in memory only."}
            </p>
          </div>
        </aside>
      </form>
    </div>
  );
}
