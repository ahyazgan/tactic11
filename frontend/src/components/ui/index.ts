/**
 * DESIGN.md §4 reusable komponent re-export.
 *
 * Kullanım:
 *   import { Panel, Pill, RatingBar, FormStrip, DataTable,
 *            Sparkline, StatTile, ExplainPanel, ExplainButton }
 *     from "@/components/ui";
 */
export { Panel } from "./panel";
export { Pill, ResultDot, FormStrip } from "./pill-badge";
export { RatingBar } from "./rating-bar";
export { DataTable } from "./table";
export type { Column, DataTableProps } from "./table";
export { Sparkline } from "./sparkline";
export { StatTile } from "./stat-tile";
export { ExplainPanel, ExplainButton } from "./explain-panel";
export { ConfidenceBadge } from "./ConfidenceBadge";
export type { ConfidenceBadgeProps } from "./ConfidenceBadge";
// FM tasarım primitifleri (futbol-zekâsı ekranları için ortak)
export { EndpointTag } from "./endpoint-tag";
export { RiskPill } from "./risk-pill";
export { ConditionBar } from "./condition-bar";
export { ProbBar } from "./prob-bar";
// Tutarlı sayfa durumları (loading / empty / error / skeleton)
export { LoadingState, EmptyState, ErrorState, Skeleton } from "./states";
