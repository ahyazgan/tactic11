/**
 * Demo modu bayrağı — kulüp sunumu için backend'siz, dolu mock veriyle çalışma.
 *
 * `true`: sayfalar canlı API'ye hiç dokunmaz, `demo-data.ts`'ten dolu veri gösterir
 *         (spinner / boş tablo / "veri yok" olmaz), sidebar maç ritmine göre sadeleşir.
 * `false`: tüm sayfalar canlı-API (SWR/WebSocket) davranışına döner.
 *
 * Kontrol env'den: `.env.local` içinde NEXT_PUBLIC_DEMO_MODE=false → canlı mod.
 * Dosya yoksa / değişken yoksa VARSAYILAN DEMO (Beşiktaş sunumu bozulmaz).
 */
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";
