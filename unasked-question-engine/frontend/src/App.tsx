import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { SettingsView } from "./components/SettingsView";
import { ToastProvider } from "./components/Toasts";
import { applyTheme, initialTheme, type Theme } from "./lib/theme";
import { Header } from "./components/Header";
import { Landing } from "./components/Landing";
import { ProgressView } from "./components/ProgressView";
import { ResultsView } from "./components/ResultsView";
import { Workspace } from "./components/Workspace";
import type { AnalysisStatus, ConfigStatus, ProjectResponse } from "./types";

type View = "landing" | "workspace" | "analyzing" | "results" | "settings";
const POLL_MS = 1200;

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [previous, setPrevious] = useState<View>("landing");
  const [view, setView] = useState<View>("landing");
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runId = useRef(0);

  useEffect(() => applyTheme(theme), [theme]);
  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next, true);
  };

  const openSettings = () => {
    if (view !== "settings") setPrevious(view);
    setView("settings");
  };

  const loadConfig = useCallback(() => {
    setConfigError(null);
    api
      .configStatus()
      .then(setConfig)
      .catch((err: unknown) => setConfigError(err instanceof ApiError ? err.message : "Could not load configuration."));
  }, []);

  useEffect(() => {
    loadConfig();
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [loadConfig]);

  const stopPolling = () => {
    runId.current += 1;
    if (pollTimer.current) clearTimeout(pollTimer.current);
  };

  const poll = useCallback((projectId: string, id: number) => {
    const tick = async () => {
      try {
        const next = await api.getAnalysis(projectId);
        if (id !== runId.current) return;
        setStatus(next);
        if (next.state === "done" && next.result) {
          setView("results");
          return;
        }
        if (next.state === "failed") {
          setError(next.error);
          return;
        }
      } catch (err) {
        if (id !== runId.current) return;
        setError(err instanceof ApiError ? err.message : "Lost contact with the server.");
        return;
      }
      pollTimer.current = setTimeout(tick, POLL_MS);
    };
    void tick();
  }, []);

  const startAnalysis = useCallback(
    async (projectId: string) => {
      stopPolling();
      const id = runId.current;
      setError(null);
      setStatus(null);
      setView("analyzing");
      try {
        const started = await api.startAnalysis(projectId);
        if (id !== runId.current) return;
        setStatus(started);
        poll(projectId, id);
      } catch (err) {
        if (id !== runId.current) return;
        setError(err instanceof ApiError ? err.message : "The analysis could not be started.");
      }
    },
    [poll],
  );

  const submit = async (description: string, files: File[]) => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProject(description, files);
      setProject(created);
      await startAnalysis(created.project_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The project could not be created.");
      setView("workspace");
    } finally {
      setBusy(false);
    }
  };

  const startDemo = async () => {
    stopPolling();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createDemo();
      setProject(created);
      const next = await api.getAnalysis(created.project_id);
      setStatus(next);
      setView("results");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The sample project could not be loaded.");
      setView("workspace");
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    stopPolling();
    setProject(null);
    setStatus(null);
    setError(null);
    setView("workspace");
    loadConfig();
  };

  const goHome = () => {
    stopPolling();
    setError(null);
    setView("landing");
  };

  return (
    <ToastProvider>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Header
        onHome={goHome}
        onNew={view === "landing" ? undefined : reset}
        onSettings={openSettings}
        settingsActive={view === "settings"}
        theme={theme}
        onToggleTheme={toggleTheme}
        modelsReady={config ? config.live_analysis_available : null}
      />
      <main id="main">
        {view === "landing" && <Landing onStart={() => setView("workspace")} onDemo={startDemo} busy={busy} />}
        {view === "workspace" && (
          <Workspace
            config={config}
            configError={configError}
            busy={busy}
            error={error}
            onSubmit={submit}
            onDemo={startDemo}
            onRetryConfig={loadConfig}
            onSettings={openSettings}
          />
        )}
        {view === "analyzing" && (
          <ProgressView
            project={project}
            status={status}
            error={error}
            onRetry={() => project && startAnalysis(project.project_id)}
            onBack={() => {
              stopPolling();
              setView("workspace");
            }}
          />
        )}
        {view === "settings" && (
          <SettingsView
            config={config}
            configError={configError}
            onSaved={setConfig}
            onRetry={loadConfig}
            onDone={() => setView(previous === "settings" ? "workspace" : previous)}
          />
        )}
        {view === "results" && status?.result && project && <ResultsView result={status.result} />}
      </main>
      <footer className="footer">
        Scores and findings are AI-generated judgements. Check the evidence before acting on them.
      </footer>
    </ToastProvider>
  );
}
