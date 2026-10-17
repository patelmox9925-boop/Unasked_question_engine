import { readStored, writeStored } from "./storage";

export type Theme = "light" | "dark";
const KEY = "uqe-theme";

export function initialTheme(): Theme {
  const stored = readStored(KEY);
  if (stored === "light" || stored === "dark") return stored;
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme, remember = false): void {
  document.documentElement.dataset.theme = theme;
  if (remember) writeStored(KEY, theme);
}
