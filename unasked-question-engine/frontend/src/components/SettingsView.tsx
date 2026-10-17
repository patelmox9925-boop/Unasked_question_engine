import { useEffect, useId, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import type { ConfigStatus, ConnectionTest, ProviderName, RoleKey, RoleSettings } from "../types";
import { useToast } from "./Toasts";

const PROVIDERS: ProviderName[] = ["gemini", "groq", "deepseek"];
const ROLES: RoleKey[] = ["A", "B", "C"];
const ROLE_NAMES: Record<RoleKey, string> = {
  A: "Model A: reads and analyses",
  B: "Model B: critiques independently",
  C: "Model C: validates and writes up",
};
const ROLE_NOTES: Record<RoleKey, string> = {
  A: "Required. It extracts the facts and finds the gaps.",
  B: "Optional. A second opinion that challenges Model A and looks for what it missed.",
  C: "Optional. Checks the evidence, merges duplicates and also answers your follow-up questions.",
};

interface Props {
  config: ConfigStatus | null;
  configError: string | null;
  onSaved: (config: ConfigStatus) => void;
  onRetry: () => void;
  onDone: () => void;
}

type Draft = Record<RoleKey, RoleSettings>;

function draftFrom(config: ConfigStatus | null): Draft {
  const blank: RoleSettings = { provider: "", model: "", fallback_provider: "", fallback_model: "" };
  const out = { A: { ...blank }, B: { ...blank }, C: { ...blank } } as Draft;
  if (!config) return out;
  for (const role of ROLES) {
    const r = config.roles[role];
    out[role] = {
      provider: r.provider ?? "",
      model: r.model ?? "",
      fallback_provider: r.fallback_provider ?? "",
      fallback_model: r.fallback_model ?? "",
    };
  }
  return out;
}

export function SettingsView({ config, configError, onSaved, onRetry, onDone }: Props) {
  const toast = useToast();
  const baseId = useId();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(config));
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [tests, setTests] = useState<Record<string, ConnectionTest | "busy">>({});
  const [modelLists, setModelLists] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [loadedFor, setLoadedFor] = useState<ConfigStatus | null>(config);

  useEffect(() => {
    if (config && config !== loadedFor) {
      setDraft(draftFrom(config));
      setLoadedFor(config);
    }
  }, [config, loadedFor]);

  const hasKey = (p: string): boolean => {
    if (removed.has(p)) return Boolean(keys[p]?.trim());
    return Boolean(keys[p]?.trim()) || Boolean(config?.providers[p]?.api_key_configured);
  };
  const usable = useMemo(() => PROVIDERS.filter(hasKey), [keys, removed, config]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRole = (role: RoleKey, patch: Partial<RoleSettings>) => setDraft((d) => ({ ...d, [role]: { ...d[role], ...patch } }));
  const modelOptions = (provider: string): string[] =>
    modelLists[provider] ?? config?.providers[provider]?.suggested_models ?? [];

  const runTest = async (testKey: string, provider: string, model: string) => {
    setTests((t) => ({ ...t, [testKey]: "busy" }));
    try {
      const typed = keys[provider]?.trim() || null;
      const result = await api.testConnection(provider, model, typed);
      setTests((t) => ({ ...t, [testKey]: result }));
      if (result.models.length) setModelLists((m) => ({ ...m, [provider]: result.models }));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "The test could not be run.";
      setTests((t) => ({ ...t, [testKey]: { ok: false, stage: "key", message, models: [] } }));
    }
  };

  const suggest = () => {
    const next = draftFrom(config);
    for (const role of ROLES) {
      const wanted = PROVIDERS.find((p) => config?.providers[p]?.default_role === role && hasKey(p));
      const pick = wanted ?? (role === "A" ? usable[0] : undefined);
      if (pick) {
        next[role] = { ...next[role], provider: pick, model: draft[role].provider === pick ? draft[role].model : "" };
      }
    }
    setDraft(next);
    toast.show("Suggested split filled in. Choose a model for each role, then save.", "info");
  };

  const save = async () => {
    setSaving(true);
    try {
      const keyUpdate: Record<string, string | null> = {};
      for (const p of PROVIDERS) {
        const typed = keys[p]?.trim();
        if (typed) keyUpdate[p] = typed;
        else if (removed.has(p)) keyUpdate[p] = "";
      }
      const saved = await api.saveSettings({ roles: draft, keys: keyUpdate });
      setKeys({});
      setRemoved(new Set());
      onSaved(saved);
      toast.show(saved.live_analysis_available ? "Saved. Your models are ready." : "Saved. Model A still needs a key and a model.", saved.live_analysis_available ? "ok" : "info");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "The settings could not be saved.", "error");
    } finally {
      setSaving(false);
    }
  };

  if (configError && !config) {
    return (
      <div className="page page--narrow">
        <h1 className="page__title">Models</h1>
        <div className="notice notice--error" role="alert">
          <strong>Server unavailable</strong>
          {configError}{" "}
          <button type="button" className="link-btn" onClick={onRetry}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h1 className="page__title">Models</h1>
      <p className="page__lead">
        Add a key for each provider you want to use, then choose which one plays each role. Everything here is saved on
        this computer, and keys are never shown again after saving.
      </p>

      <section className="settings-block" aria-labelledby={`${baseId}-keys`}>
        <h2 id={`${baseId}-keys`} className="section-title">
          1. Provider keys
        </h2>
        <div className="providers">
          {PROVIDERS.map((p) => {
            const info = config?.providers[p];
            const saved = Boolean(info?.api_key_configured) && !removed.has(p);
            const test = tests[`key:${p}`];
            return (
              <div key={p} className="provider">
                <div className="provider__head">
                  <h3>{info?.label ?? p}</h3>
                  {saved && !keys[p] && <span className="chip chip--ok">Key saved {info?.key_hint}</span>}
                </div>
                <p className="hint">{info?.strengths}</p>
                <label className="field-label" htmlFor={`${baseId}-key-${p}`}>
                  {saved ? "Replace key (leave empty to keep the saved one)" : "API key"}
                </label>
                <input
                  id={`${baseId}-key-${p}`}
                  className="input"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={saved ? "Saved key stays unless you type a new one" : "Paste your key"}
                  value={keys[p] ?? ""}
                  onChange={(e) => setKeys((k) => ({ ...k, [p]: e.target.value }))}
                />
                <div className="provider__actions">
                  <button
                    type="button"
                    className="btn btn--quiet btn--small"
                    disabled={!hasKey(p) || test === "busy"}
                    onClick={() => runTest(`key:${p}`, p, "")}
                  >
                    {test === "busy" ? "Testing…" : "Test key and load models"}
                  </button>
                  {saved && (
                    <button
                      type="button"
                      className="link-btn"
                      onClick={() => {
                        setRemoved((r) => new Set(r).add(p));
                        setKeys((k) => ({ ...k, [p]: "" }));
                      }}
                    >
                      Remove saved key
                    </button>
                  )}
                  {info?.key_url && (
                    <a className="link-btn" href={info.key_url} target="_blank" rel="noopener noreferrer">
                      Get a key
                    </a>
                  )}
                </div>
                {test && test !== "busy" && (
                  <p className={`test-result ${test.ok ? "test-result--ok" : "test-result--bad"}`} role="status">
                    {test.message}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="settings-block" aria-labelledby={`${baseId}-roles`}>
        <div className="settings-block__head">
          <h2 id={`${baseId}-roles`} className="section-title">
            2. Who does what
          </h2>
          <button type="button" className="btn btn--quiet btn--small" onClick={suggest} disabled={usable.length === 0}>
            Suggest a split
          </button>
        </div>
        <div className="roles-grid">
          {ROLES.map((role) => {
            const cfg = draft[role];
            const options = modelOptions(cfg.provider);
            const test = tests[`role:${role}`];
            const listId = `${baseId}-models-${role}`;
            return (
              <div key={role} className="role-card">
                <h3>{ROLE_NAMES[role]}</h3>
                <p className="hint">{ROLE_NOTES[role]}</p>
                <div className="role-card__fields">
                  <div>
                    <label className="field-label" htmlFor={`${baseId}-prov-${role}`}>
                      Provider for model {role}
                    </label>
                    <select
                      id={`${baseId}-prov-${role}`}
                      className="input"
                      value={cfg.provider}
                      onChange={(e) => setRole(role, { provider: e.target.value, model: "" })}
                    >
                      <option value="">{role === "A" ? "Choose a provider" : "Not used"}</option>
                      {PROVIDERS.map((p) => (
                        <option key={p} value={p} disabled={!hasKey(p) && cfg.provider !== p}>
                          {config?.providers[p]?.label ?? p}
                          {!hasKey(p) ? " (add a key first)" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="field-label" htmlFor={`${baseId}-model-${role}`}>
                      Model name for model {role}
                    </label>
                    <input
                      id={`${baseId}-model-${role}`}
                      className="input"
                      list={listId}
                      value={cfg.model}
                      disabled={!cfg.provider}
                      placeholder={cfg.provider ? "Pick one or type a model id" : "Choose a provider first"}
                      spellCheck={false}
                      onChange={(e) => setRole(role, { model: e.target.value.trim() })}
                    />
                    <datalist id={listId}>
                      {options.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                  </div>
                </div>
                <div className="provider__actions">
                  <button
                    type="button"
                    className="btn btn--quiet btn--small"
                    disabled={!cfg.provider || !cfg.model || test === "busy"}
                    onClick={() => runTest(`role:${role}`, cfg.provider, cfg.model)}
                  >
                    {test === "busy" ? "Testing…" : "Test this model"}
                  </button>
                </div>
                {test && test !== "busy" && (
                  <p className={`test-result ${test.ok ? "test-result--ok" : "test-result--bad"}`} role="status">
                    {test.message}
                  </p>
                )}
                <details className="disclosure">
                  <summary>Backup if the main one fails</summary>
                  <div className="role-card__fields">
                    <div>
                      <label className="field-label" htmlFor={`${baseId}-fprov-${role}`}>
                        Backup provider for model {role}
                      </label>
                      <select
                        id={`${baseId}-fprov-${role}`}
                        className="input"
                        value={cfg.fallback_provider}
                        onChange={(e) => setRole(role, { fallback_provider: e.target.value, fallback_model: "" })}
                      >
                        <option value="">None</option>
                        {PROVIDERS.filter(hasKey).map((p) => (
                          <option key={p} value={p}>
                            {config?.providers[p]?.label ?? p}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="field-label" htmlFor={`${baseId}-fmodel-${role}`}>
                        Backup model name for model {role}
                      </label>
                      <input
                        id={`${baseId}-fmodel-${role}`}
                        className="input"
                        list={`${listId}-f`}
                        value={cfg.fallback_model}
                        disabled={!cfg.fallback_provider}
                        spellCheck={false}
                        onChange={(e) => setRole(role, { fallback_model: e.target.value.trim() })}
                      />
                      <datalist id={`${listId}-f`}>
                        {modelOptions(cfg.fallback_provider).map((m) => (
                          <option key={m} value={m} />
                        ))}
                      </datalist>
                    </div>
                  </div>
                </details>
              </div>
            );
          })}
        </div>
      </section>

      <div className="settings-save">
        <button type="button" className="btn" onClick={save} disabled={saving || !config}>
          {saving ? "Saving…" : "Save settings"}
        </button>
        <button type="button" className="btn btn--quiet" onClick={onDone}>
          Back
        </button>
        <p className="hint">
          {config?.live_analysis_available
            ? "Model A is ready, so you can analyse a project."
            : "Model A needs a key and a model before you can analyse a project."}
        </p>
      </div>
    </div>
  );
}
