import { cn } from "@/lib/cn";

/**
 * EndpointTag — panel köşesindeki monospace API endpoint etiketi (FM kalıbı).
 * Kullanım: <EndpointTag method="GET" path="/physical-tests/{id}/risk" />
 */
export function EndpointTag({
  method = "GET",
  path,
  className,
}: {
  method?: string;
  path: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-[10px] text-textdim",
        "bg-surface2 border border-border rounded px-2 py-0.5 whitespace-nowrap",
        className,
      )}
    >
      <span className="text-textmut font-semibold">{method}</span>
      <span>{path}</span>
    </span>
  );
}
