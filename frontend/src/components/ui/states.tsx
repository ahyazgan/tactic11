/**
 * Tutarlı sayfa durumları — loading / empty / error / skeleton.
 *
 * Tüm sayfalar veri beklerken, boşken veya hata alınca aynı dili konuşsun diye
 * paylaşılan primitifler. FM teması (Tailwind token: text/muted/border/accent/bad)
 * ile uyumlu; hem ConsoleShell (.ovroot) içinde hem dışında doğru görünür.
 *
 * Kullanım:
 *   import { LoadingState, EmptyState, ErrorState, Skeleton } from "@/components/ui";
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

/** Yükleniyor görünümünü taklit eden nabız atan blok. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded bg-surface2", className)}
      aria-hidden="true"
    />
  );
}

/** Dönen spinner + etiket. role=status → erişilebilir. */
export function LoadingState({
  label = "Yükleniyor…",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-center gap-2 py-10 text-sm text-muted",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <span
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent"
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  );
}

/** Veri yokken gösterilecek boş durum — başlık + ipucu + opsiyonel aksiyon. */
export function EmptyState({
  title,
  hint,
  icon,
  action,
  className,
}: {
  title: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-10 text-center",
        className,
      )}
    >
      {icon != null && (
        <div className="text-3xl text-textdim" aria-hidden="true">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-text">{title}</p>
      {hint != null && <p className="max-w-sm text-xs text-muted">{hint}</p>}
      {action != null && <div className="mt-1">{action}</div>}
    </div>
  );
}

/** Hata durumu — başlık + (varsa) detay + opsiyonel "tekrar dene". */
export function ErrorState({
  title = "Bir şeyler ters gitti",
  error,
  onRetry,
  className,
}: {
  title?: React.ReactNode;
  error?: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const detail =
    error instanceof Error
      ? error.message
      : error != null
        ? String(error)
        : null;
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-10 text-center",
        className,
      )}
      role="alert"
    >
      <div className="text-3xl text-bad" aria-hidden="true">
        ⚠
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      {detail && (
        <p className="max-w-md break-words text-xs text-muted">{detail}</p>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded border border-border px-3 py-1.5 text-xs hover:bg-surface2"
        >
          Tekrar dene
        </button>
      )}
    </div>
  );
}
