/**
 * Demo modu bayrağı — kulüp sunumu için backend'siz, dolu mock veriyle çalışma.
 *
 * `true`: sayfalar canlı API'ye hiç dokunmaz, `demo-data.ts`'ten dolu veri gösterir
 *         (spinner / boş tablo / "veri yok" olmaz), sidebar maç ritmine göre sadeleşir.
 * `false`: tüm sayfalar eski canlı-API (SWR/WebSocket) davranışına döner.
 *
 * Demo bittiğinde tek satırı `false` yapmak yeterli — sayfa kodu kırılmaz.
 */
export const DEMO_MODE = true;
