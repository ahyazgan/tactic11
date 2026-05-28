/**
 * ExplainPanel + ExplainButton — DESIGN.md §4.ExplainPanel.
 *
 * `?explain=true` Claude yorumu lazy fetch + sağdan slide-in panel.
 * Aynı paramda tekrar çağırmaz (state cache).
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

export interface ExplainButtonProps {
  onClick: () => void;
  loading?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export function ExplainButton({
  onClick,
  loading,
  className,
  children = "Açıkla",
}: ExplainButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className={cn(
        "text-[11px] uppercase tracking-wide px-2 py-1 rounded",
        "border border-borderlt text-textmut hover:text-text hover:border-accent",
        "transition-colors disabled:opacity-50",
        className,
      )}
    >
      {loading ? "..." : children}
    </button>
  );
}

interface ExplainData {
  /** Claude yorumu (markdown ya da plain text). */
  commentary?: string;
  /** Audit gerekçesi (engine.audit.formula + inputs). */
  audit?: Record<string, unknown> | null;
  /** Raw response (debug için). */
  raw?: unknown;
}

export interface ExplainPanelProps<T = ExplainData> {
  open: boolean;
  onClose: () => void;
  /** Lazy fetch — sadece open=true olunca çağrılır, sonuç cache'lenir. */
  fetchExplain: () => Promise<T>;
  /** Custom render override (default: commentary + audit). */
  renderContent?: (data: T) => React.ReactNode;
  title?: string;
}

export function ExplainPanel<T extends ExplainData = ExplainData>({
  open,
  onClose,
  fetchExplain,
  renderContent,
  title = "Açıklama",
}: ExplainPanelProps<T>) {
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [auditOpen, setAuditOpen] = React.useState(false);
  const fetchedRef = React.useRef(false);

  React.useEffect(() => {
    if (!open || fetchedRef.current) return;
    fetchedRef.current = true;
    setLoading(true);
    setError(null);
    fetchExplain()
      .then((d) => setData(d))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [open, fetchExplain]);

  const retry = () => {
    fetchedRef.current = false;
    setData(null);
    setError(null);
    if (open) {
      fetchedRef.current = true;
      setLoading(true);
      fetchExplain()
        .then((d) => setData(d))
        .catch((e) => setError(String(e)))
        .finally(() => setLoading(false));
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop — click to close */}
      <div
        className="fixed inset-0 z-40 bg-bg/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={cn(
          "fixed right-0 top-12 w-80 h-[calc(100vh-3rem)] z-50",
          "bg-elevated border-l border-border",
          "flex flex-col",
        )}
        role="dialog"
        aria-label={title}
      >
        <header className="h-9 px-3 border-b border-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-textmut hover:text-text text-sm"
            aria-label="Kapat"
          >
            ✕
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-3">
          {loading && (
            <div className="space-y-2">
              <div className="h-3 bg-surface2 rounded animate-pulse" />
              <div className="h-3 bg-surface2 rounded animate-pulse w-5/6" />
              <div className="h-3 bg-surface2 rounded animate-pulse w-4/6" />
            </div>
          )}
          {error && (
            <div className="text-danger text-[13px]">
              {error}
              <button
                onClick={retry}
                className="block mt-2 text-[11px] underline hover:text-accent"
              >
                Tekrar dene
              </button>
            </div>
          )}
          {data && !loading && !error && (
            <>
              {renderContent ? (
                renderContent(data)
              ) : (
                <DefaultExplainContent data={data} />
              )}
              {data.audit && (
                <details
                  open={auditOpen}
                  onToggle={(e) =>
                    setAuditOpen((e.target as HTMLDetailsElement).open)
                  }
                  className="mt-4 pt-3 border-t border-border"
                >
                  <summary className="text-[11px] uppercase tracking-wider text-textmut cursor-pointer hover:text-text">
                    Audit gerekçesi
                  </summary>
                  <pre className="mt-2 text-[11px] text-textmut overflow-x-auto whitespace-pre-wrap break-all">
                    {JSON.stringify(data.audit, null, 2)}
                  </pre>
                </details>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}

function DefaultExplainContent({ data }: { data: ExplainData }) {
  if (!data.commentary) {
    return (
      <p className="text-textmut text-[13px]">
        Yorum yok (API key set'li değil olabilir).
      </p>
    );
  }
  return (
    <div className="text-[13px] text-text leading-[18px] whitespace-pre-wrap">
      {data.commentary}
    </div>
  );
}
