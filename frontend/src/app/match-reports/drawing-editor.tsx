"use client";

import { useEffect, useRef, useState } from "react";
import { Arrow, Image as CanvasImage, Layer, Rect, Stage } from "react-konva";
import type Konva from "konva";
import { apiFetchResponse } from "@/lib/api";
import styles from "./reports.module.css";

export interface Mark { kind: "arrow" | "box"; color: "yellow" | "red" | "blue"; x1: number; y1: number; x2: number; y2: number }
export interface Drawing { time: number; marks: Mark[] }
const colors = { yellow: "#ffdf32", red: "#ff4b4b", blue: "#37bfff" };

export default function DrawingEditor({ videoId, drawing, disabled, onChange }: {
  videoId: string; drawing: Drawing; disabled: boolean; onChange?: (next: Drawing) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const stage = useRef<Konva.Stage>(null);
  const [width, setWidth] = useState(600);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<Mark["kind"]>("arrow");
  const [color, setColor] = useState<Mark["color"]>("yellow");
  const [draft, setDraft] = useState<Mark | null>(null);
  const height = image ? width * image.height / image.width : width * 9 / 16;
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(1, entries[0].contentRect.width)));
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let disposed = false, url = "";
    setImage(null); setError(""); setDraft(null);
    void apiFetchResponse(`/match-reports/videos/${videoId}/frame?at=${drawing.time}`)
      .then(response => response.blob()).then(blob => {
        if (disposed) return;
        url = URL.createObjectURL(blob);
        const img = new window.Image();
        img.onload = () => { if (!disposed) setImage(img); };
        img.onerror = () => { if (!disposed) setError("Kare görüntülenemedi. Çizimi kaldırıp yeniden deneyin."); };
        img.src = url;
      }).catch(() => { if (!disposed) setError("Kaynak karesi alınamadı. Çizimi kaldırıp yeniden deneyin."); });
    return () => { disposed = true; if (url) URL.revokeObjectURL(url); };
  }, [videoId, drawing.time]);
  const point = () => {
    const p = stage.current?.getPointerPosition();
    return p ? { x: Math.min(1, Math.max(0, p.x / width)), y: Math.min(1, Math.max(0, p.y / height)) } : null;
  };
  const begin = () => {
    if (disabled || !onChange || !image || drawing.marks.length >= 20) return;
    const p = point(); if (p) setDraft({ kind, color, x1: p.x, y1: p.y, x2: p.x, y2: p.y });
  };
  const move = () => { const p = point(); if (p && draft) setDraft({ ...draft, x2: p.x, y2: p.y }); };
  const finish = () => {
    const p = point();
    if (draft && p && onChange && !disabled && Math.hypot(p.x - draft.x1, p.y - draft.y1) > .01)
      onChange({ ...drawing, marks: [...drawing.marks, { ...draft, x2: p.x, y2: p.y }] });
    setDraft(null);
  };
  return <div className={styles.stack}>
    <small>Kaynak karesi: {drawing.time.toFixed(1)} sn · Analistin çizimi · {drawing.marks.length}/20 işaret</small>
    {!!onChange && <div className={styles.toolbar}>
      <label>Çizim aracı<select value={kind} disabled={disabled} onChange={e => setKind(e.target.value as Mark["kind"])}><option value="arrow">Ok</option><option value="box">Alan</option></select></label>
      <label>Çizim rengi<select value={color} disabled={disabled} onChange={e => setColor(e.target.value as Mark["color"])}><option value="yellow">Sarı</option><option value="red">Kırmızı</option><option value="blue">Mavi</option></select></label>
      <button type="button" disabled={disabled || !drawing.marks.length} onClick={() => onChange({ ...drawing, marks: drawing.marks.slice(0, -1) })}>Son çizimi geri al</button>
    </div>}
    {error && <p role="alert">{error}</p>}
    <div ref={host} className={styles.drawing} aria-label="Pozisyon çizim alanı" data-testid="drawing-canvas">
      {!image ? <p>Kare hazırlanıyor…</p> : <Stage ref={stage} width={width} height={height}
        onMouseDown={begin} onTouchStart={begin} onMouseMove={move} onTouchMove={move}
        onMouseUp={finish} onTouchEnd={finish} onMouseLeave={() => setDraft(null)}>
        <Layer listening={false}><CanvasImage image={image} width={width} height={height} />
          {[...drawing.marks, ...(draft ? [draft] : [])].map((m, index) => m.kind === "arrow"
            ? <Arrow key={index} points={[m.x1 * width, m.y1 * height, m.x2 * width, m.y2 * height]} stroke={colors[m.color]} fill={colors[m.color]} strokeWidth={Math.max(2, width * .004)} pointerLength={width * .019} pointerWidth={width * .018} />
            : <Rect key={index} x={Math.min(m.x1, m.x2) * width} y={Math.min(m.y1, m.y2) * height} width={Math.abs(m.x2 - m.x1) * width} height={Math.abs(m.y2 - m.y1) * height} stroke={colors[m.color]} strokeWidth={Math.max(2, width * .004)} />)}
        </Layer>
      </Stage>}
    </div>
    {!!onChange && <small>Ok veya alan için görüntü üzerinde sürükleyin. Çizim rapor kaydedilip onaylandığında PDF ve teslim paketine eklenir.</small>}
  </div>;
}
