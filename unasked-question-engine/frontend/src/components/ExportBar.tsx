import { useState } from "react";
import { ApiError, api } from "../api";

export function ExportBar({ projectId }: { projectId: string }) {
  const [busy, setBusy] = useState<"md" | "pdf" | null>(null);
  const [message, setMessage] = useState<{ kind: "error" | "ok"; text: string } | null>(null);

  const download = async (format: "md" | "pdf") => {
    setBusy(format);
    setMessage(null);
    try {
      await api.downloadReport(projectId, format);
      setMessage({ kind: "ok", text: `Downloaded the ${format === "md" ? "Markdown" : "PDF"} report.` });
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "The report could not be downloaded." });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="export" role="group" aria-label="Export report">
      <button type="button" className="btn btn--quiet btn--small" disabled={busy !== null} onClick={() => download("md")}>
        {busy === "md" ? "Preparing…" : "Download Markdown"}
      </button>
      <button type="button" className="btn btn--quiet btn--small" disabled={busy !== null} onClick={() => download("pdf")}>
        {busy === "pdf" ? "Preparing…" : "Download PDF"}
      </button>
      <p className="export-note" role="status" style={message?.kind === "error" ? { color: "var(--critical)" } : undefined}>
        {message?.text}
      </p>
    </div>
  );
}
