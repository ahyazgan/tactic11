/**
 * Panel — DESIGN.md §4.Card.
 *
 * Mevcut generic `.card` CSS class'ının yerine geçer.
 * <Panel title? actions?> {children} </Panel>
 */
import * as React from "react";
import { cn } from "@/lib/cn";

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: React.ReactNode;
  actions?: React.ReactNode;
}

export const Panel = React.forwardRef<HTMLDivElement, PanelProps>(
  ({ className, title, actions, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "bg-surface border border-border rounded-md",
          className,
        )}
        {...props}
      >
        {(title || actions) && (
          <div className="h-9 px-3 border-b border-border flex items-center justify-between">
            <div className="text-sm font-semibold text-text">{title}</div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </div>
        )}
        <div className="p-3">{children}</div>
      </div>
    );
  },
);
Panel.displayName = "Panel";
