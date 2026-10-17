import { useRef } from "react";
import { bucket, type MatrixCell } from "../lib/filters";
import type { Finding } from "../types";

interface Props {
  findings: Finding[];
  selected: MatrixCell | null;
  onSelect?: (cell: MatrixCell | null) => void;
  /** Static illustration (landing page): no buttons, no focus stops. */
  decorative?: boolean;
}

const RANGE_LABELS = ["1-2", "3-4", "5-6", "7-8", "9-10"];

function zone(impact: number, likelihood: number): "critical" | "high" | "medium" | "low" {
  const p = impact * likelihood;
  if (p >= 15) return "critical";
  if (p >= 9) return "high";
  if (p >= 4) return "medium";
  return "low";
}

export function RiskMatrix({ findings, selected, onSelect, decorative = false }: Props) {
  const grid = useRef<HTMLDivElement>(null);
  const cells = new Map<string, Finding[]>();
  for (const f of findings) {
    const key = `${bucket(f.impact)}-${bucket(f.likelihood)}`;
    cells.set(key, [...(cells.get(key) ?? []), f]);
  }
  const rows = [5, 4, 3, 2, 1]; // impact, high at the top
  const cols = [1, 2, 3, 4, 5]; // likelihood, high on the right

  const onKey = (event: React.KeyboardEvent, impact: number, likelihood: number) => {
    const move: Record<string, [number, number]> = {
      ArrowUp: [1, 0],
      ArrowDown: [-1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const delta = move[event.key];
    if (!delta) return;
    event.preventDefault();
    const ni = Math.min(5, Math.max(1, impact + delta[0]));
    const nl = Math.min(5, Math.max(1, likelihood + delta[1]));
    grid.current?.querySelector<HTMLButtonElement>(`[data-cell="${ni}-${nl}"]`)?.focus();
  };

  const focusCell = selected ?? { impact: 5, likelihood: 5 };

  return (
    <figure className="matrix" aria-label="Risk matrix">
      <div className="matrix__y" aria-hidden="true">
        <span>Impact</span>
      </div>
      <div className="matrix__body">
        <div
          className="matrix__grid"
          ref={grid}
          role={decorative ? "img" : "group"}
          aria-label={decorative ? "Example risk matrix" : "Findings by impact and likelihood. Select a square to filter the list."}
        >
          {rows.map((impact) =>
            cols.map((likelihood) => {
              const list = cells.get(`${impact}-${likelihood}`) ?? [];
              const isSel = selected?.impact === impact && selected?.likelihood === likelihood;
              const label = `Impact ${RANGE_LABELS[impact - 1]}, likelihood ${RANGE_LABELS[likelihood - 1]}: ${
                list.length === 0 ? "no findings" : `${list.length} finding${list.length === 1 ? "" : "s"}`
              }`;
              const body = (
                <>
                  {list.length > 0 && <span className="matrix__count">{list.length}</span>}
                  {list.length > 0 && (
                    <span className="matrix__tip" aria-hidden="true">
                      {list.slice(0, 3).map((f) => (
                        <span key={f.id}>{f.title}</span>
                      ))}
                      {list.length > 3 && <span>and {list.length - 3} more</span>}
                    </span>
                  )}
                </>
              );
              const className = `matrix__cell matrix__cell--${zone(impact, likelihood)}${list.length ? " has-findings" : ""}${isSel ? " is-selected" : ""}`;
              if (decorative) {
                return (
                  <span key={`${impact}-${likelihood}`} className={className}>
                    {body}
                  </span>
                );
              }
              return (
                <button
                  key={`${impact}-${likelihood}`}
                  type="button"
                  className={className}
                  data-cell={`${impact}-${likelihood}`}
                  aria-label={label}
                  aria-pressed={isSel}
                  tabIndex={focusCell.impact === impact && focusCell.likelihood === likelihood ? 0 : -1}
                  onClick={() => onSelect?.(isSel ? null : { impact, likelihood })}
                  onKeyDown={(e) => onKey(e, impact, likelihood)}
                >
                  {body}
                </button>
              );
            }),
          )}
        </div>
        <div className="matrix__x" aria-hidden="true">
          <span>Likelihood</span>
        </div>
      </div>
    </figure>
  );
}
