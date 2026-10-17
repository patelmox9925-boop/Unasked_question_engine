import { forwardRef } from "react";
import { countBy, toggled, type FindingFilters, type SortKey } from "../lib/filters";
import { CATEGORY_LABELS, LEVEL_LABELS, LEVEL_ORDER, STATUS_LABELS } from "../lib/format";
import type { Category, EpistemicStatus, Finding, TriageEntry, TriageStatus } from "../types";

interface Props {
  findings: Finding[];
  triage: Record<string, TriageEntry>;
  filters: FindingFilters;
  onChange: (next: FindingFilters) => void;
  shown: number;
}

const SORTS: [SortKey, string][] = [
  ["priority", "Priority score"],
  ["impact", "Impact"],
  ["likelihood", "Likelihood"],
  ["urgency", "Urgency"],
];
const DECISIONS: [TriageStatus, string][] = [
  ["open", "Not decided"],
  ["accepted", "Accepted"],
  ["resolved", "Resolved"],
  ["dismissed", "Dismissed"],
];

export const FilterBar = forwardRef<HTMLInputElement, Props>(function FilterBar(
  { findings, triage, filters, onChange, shown },
  searchRef,
) {
  const byLevel = countBy(findings, (f) => f.priority_level);
  const byCategory = countBy<Category>(findings, (f) => f.category);
  const byStatus = countBy<EpistemicStatus>(findings, (f) => f.epistemic_status);
  const byDecision = countBy<TriageStatus>(findings, (f) => triage[f.id]?.status ?? "open");
  const active =
    filters.categories.size + filters.levels.size + filters.statuses.size + filters.decisions.size + (filters.cell ? 1 : 0);

  return (
    <div className="filterbar" role="search" aria-label="Filter findings">
      <div className="filterbar__row">
        <div className="searchbox">
          <label className="visually-hidden" htmlFor="finding-search">
            Search findings
          </label>
          <input
            id="finding-search"
            ref={searchRef}
            className="input"
            type="search"
            placeholder="Search findings (press / to jump here)"
            value={filters.query}
            onChange={(e) => onChange({ ...filters, query: e.target.value })}
          />
        </div>
        <div className="chipgroup" role="group" aria-label="Priority">
          {LEVEL_ORDER.map((level) => (
            <button
              key={level}
              type="button"
              className={`fchip fchip--${level}`}
              aria-pressed={filters.levels.has(level)}
              disabled={!byLevel.get(level) && !filters.levels.has(level)}
              onClick={() => onChange({ ...filters, levels: toggled(filters.levels, level) })}
            >
              {LEVEL_LABELS[level]} <span>{byLevel.get(level) ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="sortbox">
          <label htmlFor="finding-sort">Sort by</label>
          <select
            id="finding-sort"
            className="input"
            value={filters.sort}
            onChange={(e) => onChange({ ...filters, sort: e.target.value as SortKey })}
          >
            {SORTS.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="filterbar__row filterbar__row--secondary">
        <details className="menu">
          <summary>
            Type{filters.categories.size ? ` (${filters.categories.size})` : ""}
          </summary>
          <div className="menu__panel">
            {(Object.keys(CATEGORY_LABELS) as Category[]).map((c) => (
              <label key={c} className="check">
                <input
                  type="checkbox"
                  checked={filters.categories.has(c)}
                  disabled={!byCategory.get(c) && !filters.categories.has(c)}
                  onChange={() => onChange({ ...filters, categories: toggled(filters.categories, c) })}
                />
                <span>{CATEGORY_LABELS[c]}</span>
                <em>{byCategory.get(c) ?? 0}</em>
              </label>
            ))}
          </div>
        </details>
        <details className="menu">
          <summary>
            Support{filters.statuses.size ? ` (${filters.statuses.size})` : ""}
          </summary>
          <div className="menu__panel">
            {(Object.keys(STATUS_LABELS) as EpistemicStatus[]).map((s) => (
              <label key={s} className="check">
                <input
                  type="checkbox"
                  checked={filters.statuses.has(s)}
                  disabled={!byStatus.get(s) && !filters.statuses.has(s)}
                  onChange={() => onChange({ ...filters, statuses: toggled(filters.statuses, s) })}
                />
                <span>{STATUS_LABELS[s]}</span>
                <em>{byStatus.get(s) ?? 0}</em>
              </label>
            ))}
          </div>
        </details>
        <details className="menu">
          <summary>
            Your decision{filters.decisions.size ? ` (${filters.decisions.size})` : ""}
          </summary>
          <div className="menu__panel">
            {DECISIONS.map(([key, label]) => (
              <label key={key} className="check">
                <input
                  type="checkbox"
                  checked={filters.decisions.has(key)}
                  onChange={() => onChange({ ...filters, decisions: toggled(filters.decisions, key) })}
                />
                <span>{label}</span>
                <em>{byDecision.get(key) ?? 0}</em>
              </label>
            ))}
          </div>
        </details>
        <span className="filterbar__count" aria-live="polite">
          Showing {shown} of {findings.length}
        </span>
        {(active > 0 || filters.query.trim() !== "") && (
          <button
            type="button"
            className="link-btn"
            onClick={() =>
              onChange({ ...filters, categories: new Set(), levels: new Set(), statuses: new Set(), decisions: new Set(), cell: null, query: "" })
            }
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
});
