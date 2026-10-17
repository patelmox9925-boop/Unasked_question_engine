import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type ToastKind = "ok" | "error" | "info";
interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastApi {
  show: (text: string, kind?: ToastKind) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => undefined });

export function useToast(): ToastApi {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);

  const show = useCallback((text: string, kind: ToastKind = "ok") => {
    const id = next.current++;
    setToasts((prev) => [...prev.slice(-3), { id, kind, text }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), kind === "error" ? 7000 : 3200);
  }, []);

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.kind}`}>
            {t.text}
            <button
              type="button"
              className="toast__close"
              aria-label="Dismiss message"
              onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
