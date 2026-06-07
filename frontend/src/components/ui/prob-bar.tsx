/**
 * ProbBar — maç tahmini: tek bar, 3 segment (galibiyet / berabere / mağlubiyet)
 * + altında monospace yüzdeler. Değerler olasılık ya da sayı olabilir; normalize
 * edilir.
 */
export function ProbBar({
  home,
  draw,
  away,
  className,
}: {
  home: number;
  draw: number;
  away: number;
  className?: string;
}) {
  const total = home + draw + away || 1;
  const h = (home / total) * 100;
  const d = (draw / total) * 100;
  const a = (away / total) * 100;
  return (
    <div className={className}>
      <div className="flex h-2 rounded overflow-hidden bg-elevated">
        <div className="bg-ok" style={{ width: `${h}%` }} />
        <div className="bg-textdim" style={{ width: `${d}%` }} />
        <div className="bg-high" style={{ width: `${a}%` }} />
      </div>
      <div className="flex justify-between mt-1 font-mono text-[10px] text-textmut">
        <span>{Math.round(h)}%</span>
        <span>{Math.round(d)}%</span>
        <span>{Math.round(a)}%</span>
      </div>
    </div>
  );
}
