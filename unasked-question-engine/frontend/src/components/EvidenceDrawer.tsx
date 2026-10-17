import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, api } from "../api";
import type { ChunkResponse, Evidence } from "../types";

interface Props {
  projectId: string;
  evidence: Evidence | null;
  onClose: () => void;
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Split `text` around the excerpt (whitespace- and case-insensitive; "..." marks gaps) so it can be highlighted. */
export function highlight(text: string, excerpt: string): ReactNode[] {
  const segments = excerpt
    .split(/\.\.\.|…/)
    .map((s) => s.trim())
    .filter((s) => s.length > 2);
  if (segments.length === 0) return [text];
  const pattern = segments.map((s) => s.split(/\s+/).map(escapeRe).join("\\s+")).join("|");
  let regex: RegExp;
  try {
    regex = new RegExp(`(${pattern})`, "gi");
  } catch {
    return [text];
  }
  const parts = text.split(regex);
  return parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part));
}

export function EvidenceDrawer({ projectId, evidence, onClose }: Props) {
  const [chunk, setChunk] = useState<ChunkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnTo = useRef<Element | null>(null);

  useEffect(() => {
    if (!evidence) return;
    returnTo.current = document.activeElement;
    setChunk(null);
    setError(null);
    let cancelled = false;
    api
      .getChunk(projectId, evidence.chunk_id)
      .then((c) => !cancelled && setChunk(c))
      .catch((err: unknown) => !cancelled && setError(err instanceof ApiError ? err.message : "The source could not be loaded."));
    closeRef.current?.focus();
    return () => {
      cancelled = true;
      (returnTo.current as HTMLElement | null)?.focus?.();
    };
  }, [evidence, projectId]);

  useEffect(() => {
    if (!evidence) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [evidence, onClose]);

  if (!evidence) return null;
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <div className="drawer__head">
          <div>
            <h2 id="drawer-title">Source passage</h2>
            <p className="hint">{evidence.source_label}</p>
          </div>
          <button ref={closeRef} type="button" className="icon-btn" onClick={onClose} aria-label="Close source passage">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        {error && (
          <div className="notice notice--error" role="alert">
            <strong>Could not open the source</strong>
            {error}
          </div>
        )}
        {!chunk && !error && (
          <p className="typing" role="status">
            <span className="spinner" aria-hidden="true" /> Loading the passage…
          </p>
        )}
        {chunk && (
          <>
            <pre className="drawer__text">{highlight(chunk.text, evidence.excerpt)}</pre>
            {chunk.flags.length > 0 && (
              <p className="note">This passage contains text that resembles instructions to an AI. It was treated as data only.</p>
            )}
            <p className="hint">
              {evidence.kind === "related"
                ? "Highlighted text is the closest match found by search. It was not cited by a model."
                : evidence.quote_verified
                  ? "The highlighted text is the exact quote the finding relies on."
                  : "The model's quote could not be verified, so only the start of this section is shown."}
            </p>
          </>
        )}
      </aside>
    </>
  );
}
