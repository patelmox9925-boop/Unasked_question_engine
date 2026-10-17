import type { Theme } from "../lib/theme";

interface Props {
  onHome: () => void;
  onNew?: () => void;
  onSettings: () => void;
  settingsActive: boolean;
  theme: Theme;
  onToggleTheme: () => void;
  modelsReady: boolean | null;
}

export function Header({ onHome, onNew, onSettings, settingsActive, theme, onToggleTheme, modelsReady }: Props) {
  return (
    <header className="header">
      <div className="header__inner">
        <button type="button" className="brand" onClick={onHome} aria-label="The Unasked Question Engine, home">
          <span className="brand__mark" aria-hidden="true">
            ?
          </span>
          <span className="brand__name">The Unasked Question Engine</span>
        </button>
        <nav className="header__actions" aria-label="Main">
          {onNew && (
            <button type="button" className="btn btn--quiet btn--small" onClick={onNew}>
              New analysis
            </button>
          )}
          <button
            type="button"
            className={`btn btn--quiet btn--small${settingsActive ? " is-active" : ""}`}
            onClick={onSettings}
            aria-current={settingsActive ? "page" : undefined}
          >
            <span className={`dot${modelsReady ? " dot--ok" : ""}`} aria-hidden="true" />
            Models
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={onToggleTheme}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            title={theme === "dark" ? "Light theme" : "Dark theme"}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              {theme === "dark" ? (
                <>
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" strokeLinecap="round" />
                </>
              ) : (
                <path d="M21 13A9 9 0 1111 3a7 7 0 0010 10z" strokeLinecap="round" strokeLinejoin="round" />
              )}
            </svg>
          </button>
        </nav>
      </div>
    </header>
  );
}
