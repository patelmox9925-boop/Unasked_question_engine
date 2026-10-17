import { useEffect, useRef } from "react";

export const SHORTCUTS: [string, string][] = [
  ["j / k", "Next / previous finding"],
  ["o or Enter", "Open or close the selected finding"],
  ["a", "Accept: this needs action"],
  ["d", "Dismiss"],
  ["r", "Mark resolved"],
  ["c", "Copy the question"],
  ["/", "Search findings"],
  ["Esc", "Close a panel or clear the matrix filter"],
  ["?", "Show this list"],
];

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title">
        <h2 id="shortcuts-title">Keyboard shortcuts</h2>
        <dl className="shortcuts">
          {SHORTCUTS.map(([keys, what]) => (
            <div key={keys}>
              <dt>
                {keys.split(" ").map((k, i, all) =>
                  all.length > 1 && (k === "or" || k === "/") ? <span key={i}> {k} </span> : <kbd key={i}>{k}</kbd>,
                )}
              </dt>
              <dd>{what}</dd>
            </div>
          ))}
        </dl>
        <button ref={ref} type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </div>
    </>
  );
}
