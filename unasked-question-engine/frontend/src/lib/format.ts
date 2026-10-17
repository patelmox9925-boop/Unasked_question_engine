import type { Category, EpistemicStatus, Grounding, PriorityLevel } from "../types";

export const CATEGORY_LABELS: Record<Category, string> = {
  missing_assumption: "Missing assumption",
  overlooked_constraint: "Overlooked constraint",
  risk: "Risk",
  missing_dependency: "Missing dependency",
  contradiction: "Contradiction",
  missing_information: "Missing information",
  unasked_question: "Unasked question",
  opportunity: "Opportunity",
};

export const LEVEL_LABELS: Record<PriorityLevel, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const LEVEL_ORDER: PriorityLevel[] = ["critical", "high", "medium", "low"];

export const STATUS_LABELS: Record<EpistemicStatus, string> = {
  verified_fact: "Stated in your material",
  reasonable_inference: "Inferred from your material",
  unverified_hypothesis: "Unverified hypothesis",
};

export const STATUS_HELP: Record<EpistemicStatus, string> = {
  verified_fact: "Directly supported by a quote found in your documents.",
  reasonable_inference: "Follows from your material, or from what it leaves out.",
  unverified_hypothesis: "Plausible for this kind of project but not supported by your material.",
};

export const GROUNDING_LABELS: Record<Grounding, string> = {
  grounded: "Grounded in your material",
  partly_grounded: "Partly grounded",
  not_in_material: "Not in your material",
};

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".markdown", ".csv"];

export function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index < 0 ? "" : name.slice(index).toLowerCase();
}

export function validateFiles(
  files: File[],
  limits: { max_upload_mb: number; max_files: number },
): { accepted: File[]; problems: string[] } {
  const problems: string[] = [];
  const accepted: File[] = [];
  for (const file of files) {
    if (!SUPPORTED_EXTENSIONS.includes(extensionOf(file.name))) {
      problems.push(`${file.name}: unsupported type. Use ${SUPPORTED_EXTENSIONS.join(", ")}.`);
    } else if (file.size > limits.max_upload_mb * 1024 * 1024) {
      problems.push(`${file.name}: larger than ${limits.max_upload_mb} MB.`);
    } else if (file.size === 0) {
      problems.push(`${file.name}: the file is empty.`);
    } else if (accepted.length >= limits.max_files) {
      problems.push(`${file.name}: only ${limits.max_files} files can be added.`);
    } else {
      accepted.push(file);
    }
  }
  return { accepted, problems };
}
