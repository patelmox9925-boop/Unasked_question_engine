import type { Evidence } from "../types";

interface Props {
  evidence: Evidence[];
  emptyText?: string;
  onOpen?: (evidence: Evidence) => void;
}

export function EvidenceList({ evidence, emptyText, onOpen }: Props) {
  if (evidence.length === 0) {
    return emptyText ? <p className="hint">{emptyText}</p> : null;
  }
  return (
    <div className="evidence">
      {evidence.map((e) => (
        <figure key={`${e.kind}-${e.chunk_id}`} className={e.kind === "related" ? "evidence__item evidence__item--related" : "evidence__item"}>
          <blockquote>{e.excerpt}</blockquote>
          <figcaption>
            <span className="evidence__source">{e.source_label}</span>
            {e.kind === "related" ? (
              <span className="tag-info">Closest passage found by search. The model did not cite it.</span>
            ) : e.quote_verified ? (
              <span className="tag-ok">Exact quote verified in source</span>
            ) : (
              <span className="tag-warn">Start of the relevant section. The model&apos;s quote could not be verified.</span>
            )}
            {onOpen && (
              <button type="button" className="link-btn" onClick={() => onOpen(e)}>
                View in source
              </button>
            )}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
