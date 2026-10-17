import { CATEGORY_LABELS, LEVEL_LABELS, STATUS_LABELS } from "./format";
import type { Finding } from "../types";

/** Plain-text version of a finding, for pasting into an email or ticket. */
export function findingAsText(f: Finding): string {
  const level = f.priority_level ? `${LEVEL_LABELS[f.priority_level]}${f.priority_score !== null ? ` ${Math.round(f.priority_score)}` : ""}` : "Unranked";
  const lines = [
    `${f.title} [${level}, ${CATEGORY_LABELS[f.category]}, ${STATUS_LABELS[f.epistemic_status]}]`,
    "",
    f.explanation,
    "",
    `Why it matters: ${f.why_it_matters}`,
    ...(f.why_overlooked ? [`Why it is easy to miss: ${f.why_overlooked}`] : []),
    `Recommended action: ${f.recommended_action}`,
    `Question to answer: ${f.critical_question}`,
  ];
  const cited = f.evidence.filter((e) => e.kind === "cited");
  if (cited.length) {
    lines.push("", "Evidence:", ...cited.map((e) => `- "${e.excerpt}" (${e.source_label})`));
  }
  return lines.join("\n");
}

export function shouldAnimate(): boolean {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}
