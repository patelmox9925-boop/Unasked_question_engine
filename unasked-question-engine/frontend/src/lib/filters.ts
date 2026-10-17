import type { Category, EpistemicStatus, Finding, PriorityLevel, TriageEntry, TriageStatus } from "../types";

export type SortKey = "priority" | "impact" | "likelihood" | "urgency";

export interface MatrixCell {
  impact: number; // 1..5 (buckets of two points on the 1-10 scale)
  likelihood: number; // 1..5
}

export const bucket = (score: number): number => Math.min(5, Math.max(1, Math.ceil(score / 2)));

export interface FindingFilters {
  categories: Set<Category>;
  levels: Set<PriorityLevel>;
  statuses: Set<EpistemicStatus>;
  decisions: Set<TriageStatus>;
  cell: MatrixCell | null;
  query: string;
  sort: SortKey;
}

export const emptyFilters = (): FindingFilters => ({
  categories: new Set(),
  levels: new Set(),
  statuses: new Set(),
  decisions: new Set(),
  cell: null,
  query: "",
  sort: "priority",
});

export function isFiltering(f: FindingFilters): boolean {
  return (
    f.categories.size > 0 || f.levels.size > 0 || f.statuses.size > 0 || f.decisions.size > 0 || f.cell !== null ||
    f.query.trim() !== ""
  );
}

export function applyFilters(
  findings: Finding[],
  f: FindingFilters,
  triage: Record<string, TriageEntry> = {},
): Finding[] {
  const q = f.query.trim().toLowerCase();
  const matches = findings.filter((x) => {
    if (f.categories.size && !f.categories.has(x.category)) return false;
    if (f.levels.size && !(x.priority_level && f.levels.has(x.priority_level))) return false;
    if (f.statuses.size && !f.statuses.has(x.epistemic_status)) return false;
    if (f.decisions.size && !f.decisions.has(triage[x.id]?.status ?? "open")) return false;
    if (f.cell && (bucket(x.impact) !== f.cell.impact || bucket(x.likelihood) !== f.cell.likelihood)) return false;
    if (q) {
      const haystack = `${x.title} ${x.explanation} ${x.critical_question} ${x.recommended_action}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
  const value = (x: Finding): number =>
    f.sort === "priority" ? (x.priority_score ?? 0) : x[f.sort];
  return [...matches].sort((a, b) => value(b) - value(a) || a.id.localeCompare(b.id, undefined, { numeric: true }));
}

export function toggled<T>(set: Set<T>, item: T): Set<T> {
  const next = new Set(set);
  if (next.has(item)) next.delete(item);
  else next.add(item);
  return next;
}

export function countBy<T extends string>(findings: Finding[], pick: (f: Finding) => T | null): Map<T, number> {
  const counts = new Map<T, number>();
  for (const f of findings) {
    const key = pick(f);
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}
