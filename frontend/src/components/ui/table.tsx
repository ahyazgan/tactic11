/**
 * DataTable — DESIGN.md §4.Table.
 *
 * Dense, zebra'lı, sticky header'lı tablo primitifi. h-7 satır, px-2 hücre,
 * 12px text, tabular-nums sayısal kolonlar.
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  width?: string;
  render?: (row: T) => React.ReactNode;
  /** Sıralama için değer çıkarıcı (render farklı tipte olabilir). */
  sortValue?: (row: T) => string | number;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  selectedKey?: string | number | null;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  className?: string;
}

type SortState = { key: string; dir: "asc" | "desc" } | null;

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  selectedKey,
  onRowClick,
  emptyMessage = "Veri yok",
  className,
}: DataTableProps<T>) {
  const [sort, setSort] = React.useState<SortState>(null);

  const sortedRows = React.useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const getValue = col.sortValue
      ?? ((row: T) => {
        const v = (row as Record<string, unknown>)[sort.key];
        return typeof v === "string" || typeof v === "number" ? v : String(v ?? "");
      });
    const arr = [...rows];
    arr.sort((a, b) => {
      const va = getValue(a);
      const vb = getValue(b);
      if (va === vb) return 0;
      const less = va < vb ? -1 : 1;
      return sort.dir === "asc" ? less : -less;
    });
    return arr;
  }, [rows, columns, sort]);

  const handleSort = (col: Column<T>) => {
    if (!col.sortable) return;
    setSort((prev) => {
      if (!prev || prev.key !== col.key) return { key: col.key, dir: "asc" };
      if (prev.dir === "asc") return { key: col.key, dir: "desc" };
      return null; // 3. tıkla sıfırla
    });
  };

  return (
    <div
      className={cn(
        "overflow-x-auto bg-surface border border-border rounded-md",
        className,
      )}
    >
      <table className="w-full text-[12px] leading-4">
        <thead className="sticky top-0 z-10">
          <tr>
            {columns.map((c) => {
              const isSorted = sort?.key === c.key;
              const align =
                c.align === "right"
                  ? "text-right"
                  : c.align === "center"
                  ? "text-center"
                  : "text-left";
              return (
                <th
                  key={c.key}
                  scope="col"
                  className={cn(
                    "px-2 h-7 bg-surface border-b border-border",
                    "text-[11px] uppercase tracking-wide font-semibold text-textmut",
                    align,
                    c.sortable && "cursor-pointer hover:text-text select-none",
                  )}
                  style={c.width ? { width: c.width } : undefined}
                  onClick={() => handleSort(c)}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.header}
                    {c.sortable && (
                      <span className="text-[9px] text-textdim">
                        {isSorted ? (sort?.dir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    )}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="px-2 h-12 text-center text-textmut"
              >
                {emptyMessage}
              </td>
            </tr>
          )}
          {sortedRows.map((row, idx) => {
            const key = rowKey(row);
            const isSelected = selectedKey !== undefined
              && selectedKey !== null && key === selectedKey;
            return (
              <tr
                key={key}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  "h-7",
                  idx % 2 === 0 ? "bg-surface" : "bg-surface2",
                  isSelected && "bg-accent/15 border-l-2 border-accent",
                  onRowClick && "cursor-pointer hover:bg-elevated",
                )}
              >
                {columns.map((c) => {
                  const align =
                    c.align === "right"
                      ? "text-right tabular-nums"
                      : c.align === "center"
                      ? "text-center"
                      : "text-left";
                  const content = c.render
                    ? c.render(row)
                    : String(
                        (row as Record<string, unknown>)[c.key] ?? "",
                      );
                  return (
                    <td
                      key={c.key}
                      className={cn("px-2 text-text", align)}
                    >
                      {content}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
