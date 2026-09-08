/**
 * Saha kalibrasyonu geometrisi (istemci tarafı) — backend `app/tracking/calibration.py`
 * ile aynı DLT; kullanıcı noktaları tıklarken saha çizgilerini anında geri-izdüşürmek için.
 *
 * Saha koordinatı: metre, orijin sol-üst köşe, x boyuna 0..L, y enine 0..W.
 */

export type Pt = [number, number];
export type Mat3 = number[][];

export const PITCH_L = 105;
export const PITCH_W = 68;

export interface Landmark {
  id: string;
  label: string;
  pitch: (L: number, W: number) => Pt;
}

/** Tıklanabilir saha işaretleri — kullanıcı görüntüde gördüğü noktayı seçer. */
export const LANDMARKS: Landmark[] = [
  { id: "c_tl", label: "Köşe — sol üst", pitch: () => [0, 0] },
  { id: "c_tr", label: "Köşe — sağ üst", pitch: (L) => [L, 0] },
  { id: "c_br", label: "Köşe — sağ alt", pitch: (L, W) => [L, W] },
  { id: "c_bl", label: "Köşe — sol alt", pitch: (_L, W) => [0, W] },
  { id: "half_t", label: "Orta çizgi — üst taç", pitch: (L) => [L / 2, 0] },
  { id: "half_b", label: "Orta çizgi — alt taç", pitch: (L, W) => [L / 2, W] },
  { id: "center", label: "Orta nokta", pitch: (L, W) => [L / 2, W / 2] },
  { id: "cc_t", label: "Orta yuvarlak — üst", pitch: (L, W) => [L / 2, W / 2 - 9.15] },
  { id: "cc_b", label: "Orta yuvarlak — alt", pitch: (L, W) => [L / 2, W / 2 + 9.15] },
  { id: "pen_l", label: "Penaltı noktası — sol", pitch: (_L, W) => [11, W / 2] },
  { id: "pen_r", label: "Penaltı noktası — sağ", pitch: (L, W) => [L - 11, W / 2] },
  { id: "pb_l_tt", label: "Ceza sahası sol — üst köşe (kale çizgisi)", pitch: (_L, W) => [0, W / 2 - 20.16] },
  { id: "pb_l_ti", label: "Ceza sahası sol — üst iç köşe", pitch: (_L, W) => [16.5, W / 2 - 20.16] },
  { id: "pb_l_bi", label: "Ceza sahası sol — alt iç köşe", pitch: (_L, W) => [16.5, W / 2 + 20.16] },
  { id: "pb_l_bt", label: "Ceza sahası sol — alt köşe (kale çizgisi)", pitch: (_L, W) => [0, W / 2 + 20.16] },
  { id: "pb_r_tt", label: "Ceza sahası sağ — üst köşe (kale çizgisi)", pitch: (L, W) => [L, W / 2 - 20.16] },
  { id: "pb_r_ti", label: "Ceza sahası sağ — üst iç köşe", pitch: (L, W) => [L - 16.5, W / 2 - 20.16] },
  { id: "pb_r_bi", label: "Ceza sahası sağ — alt iç köşe", pitch: (L, W) => [L - 16.5, W / 2 + 20.16] },
  { id: "pb_r_bt", label: "Ceza sahası sağ — alt köşe (kale çizgisi)", pitch: (L, W) => [L, W / 2 + 20.16] },
  { id: "ga_l_ti", label: "Kale sahası sol — üst iç köşe", pitch: (_L, W) => [5.5, W / 2 - 9.16] },
  { id: "ga_l_bi", label: "Kale sahası sol — alt iç köşe", pitch: (_L, W) => [5.5, W / 2 + 9.16] },
  { id: "ga_r_ti", label: "Kale sahası sağ — üst iç köşe", pitch: (L, W) => [L - 5.5, W / 2 - 9.16] },
  { id: "ga_r_bi", label: "Kale sahası sağ — alt iç köşe", pitch: (L, W) => [L - 5.5, W / 2 + 9.16] },
  { id: "post_l_t", label: "Kale direği sol — üst", pitch: (_L, W) => [0, W / 2 - 3.66] },
  { id: "post_l_b", label: "Kale direği sol — alt", pitch: (_L, W) => [0, W / 2 + 3.66] },
  { id: "post_r_t", label: "Kale direği sağ — üst", pitch: (L, W) => [L, W / 2 - 3.66] },
  { id: "post_r_b", label: "Kale direği sağ — alt", pitch: (L, W) => [L, W / 2 + 3.66] },
];

function normalize(pts: Pt[]): { n: Pt[]; T: Mat3 } {
  const mx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const my = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const meanDist = pts.reduce((s, p) => s + Math.hypot(p[0] - mx, p[1] - my), 0) / pts.length || 1;
  const s = Math.SQRT2 / meanDist;
  const T: Mat3 = [[s, 0, -s * mx], [0, s, -s * my], [0, 0, 1]];
  return { n: pts.map(([x, y]) => [s * (x - mx), s * (y - my)] as Pt), T };
}

/** Jacobi eigen-decomposition (simetrik 9×9) → en küçük özdeğerin vektörü. */
function smallestEigenvector(A: number[][]): number[] {
  const n = A.length;
  const a = A.map((r) => r.slice());
  const V: number[][] = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => (i === j ? 1 : 0)));
  for (let sweep = 0; sweep < 100; sweep++) {
    let off = 0;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) off += a[i][j] * a[i][j];
    if (off < 1e-22) break;
    for (let p = 0; p < n; p++) {
      for (let q = p + 1; q < n; q++) {
        if (Math.abs(a[p][q]) < 1e-30) continue;
        const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
        const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1), s = t * c;
        for (let k = 0; k < n; k++) {
          const akp = a[k][p], akq = a[k][q];
          a[k][p] = c * akp - s * akq; a[k][q] = s * akp + c * akq;
        }
        for (let k = 0; k < n; k++) {
          const apk = a[p][k], aqk = a[q][k];
          a[p][k] = c * apk - s * aqk; a[q][k] = s * apk + c * aqk;
        }
        for (let k = 0; k < n; k++) {
          const vkp = V[k][p], vkq = V[k][q];
          V[k][p] = c * vkp - s * vkq; V[k][q] = s * vkp + c * vkq;
        }
      }
    }
  }
  let best = 0;
  for (let i = 1; i < n; i++) if (a[i][i] < a[best][best]) best = i;
  return V.map((row) => row[best]);
}

function mul(A: Mat3, B: Mat3): Mat3 {
  return A.map((r, i) => B[0].map((_, j) => r[0] * B[0][j] + r[1] * B[1][j] + r[2] * B[2][j]));
}

export function invert3(M: Mat3): Mat3 | null {
  const [[a, b, c], [d, e, f], [g, h, i]] = M;
  const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  if (Math.abs(det) < 1e-12) return null;
  const inv: Mat3 = [
    [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
    [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
    [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
  ];
  return inv;
}

/** src (görüntü px) → dst (saha m) homografisi; n ≥ 4, dejenere ise null. */
export function dltHomography(src: Pt[], dst: Pt[]): Mat3 | null {
  if (src.length < 4 || src.length !== dst.length) return null;
  const { n: s, T: Ts } = normalize(src);
  const { n: d, T: Td } = normalize(dst);
  const rows: number[][] = [];
  for (let k = 0; k < s.length; k++) {
    const [x, y] = s[k], [X, Y] = d[k];
    rows.push([-x, -y, -1, 0, 0, 0, X * x, X * y, X]);
    rows.push([0, 0, 0, -x, -y, -1, Y * x, Y * y, Y]);
  }
  // A^T A (9×9) → en küçük özvektör = h
  const AtA = Array.from({ length: 9 }, () => Array(9).fill(0) as number[]);
  for (const r of rows) for (let i = 0; i < 9; i++) for (let j = 0; j < 9; j++) AtA[i][j] += r[i] * r[j];
  const h = smallestEigenvector(AtA);
  const Hn: Mat3 = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], h[8]]];
  const TdInv = invert3(Td);
  if (!TdInv) return null;
  const H = mul(mul(TdInv, Hn), Ts);
  const w = H[2][2];
  if (!isFinite(w) || Math.abs(w) < 1e-12) return null;
  const Hs = H.map((r) => r.map((v) => v / w));
  // Dejenere kontrol: 4 kaynak noktanın geri-izdüşümü sonlu mu
  for (const p of src) {
    const q = applyH(Hs, p);
    if (!q || !isFinite(q[0]) || !isFinite(q[1])) return null;
  }
  return Hs;
}

export function applyH(H: Mat3, p: Pt): Pt | null {
  const [u, v] = p;
  const w = H[2][0] * u + H[2][1] * v + H[2][2];
  if (Math.abs(w) < 1e-12) return null;
  return [(H[0][0] * u + H[0][1] * v + H[0][2]) / w, (H[1][0] * u + H[1][1] * v + H[1][2]) / w];
}

export function reprojectionErrorM(H: Mat3, src: Pt[], dst: Pt[]): number {
  let s = 0;
  for (let i = 0; i < src.length; i++) {
    const q = applyH(H, src[i]);
    s += q ? Math.hypot(q[0] - dst[i][0], q[1] - dst[i][1]) : 99;
  }
  return s / Math.max(1, src.length);
}

/** Saha çizgileri (metre) — kalibrasyon önizlemesi için çoklu çizgiler. */
export function pitchPolylines(L = PITCH_L, W = PITCH_W): { pts: Pt[]; closed: boolean }[] {
  const circle = (cx: number, cy: number, r: number, n = 48): Pt[] =>
    Array.from({ length: n }, (_, i) => [cx + r * Math.cos((2 * Math.PI * i) / n), cy + r * Math.sin((2 * Math.PI * i) / n)] as Pt);
  return [
    { pts: [[0, 0], [L, 0], [L, W], [0, W]], closed: true },
    { pts: [[L / 2, 0], [L / 2, W]], closed: false },
    { pts: circle(L / 2, W / 2, 9.15), closed: true },
    { pts: [[0, W / 2 - 20.16], [16.5, W / 2 - 20.16], [16.5, W / 2 + 20.16], [0, W / 2 + 20.16]], closed: false },
    { pts: [[L, W / 2 - 20.16], [L - 16.5, W / 2 - 20.16], [L - 16.5, W / 2 + 20.16], [L, W / 2 + 20.16]], closed: false },
    { pts: [[0, W / 2 - 9.16], [5.5, W / 2 - 9.16], [5.5, W / 2 + 9.16], [0, W / 2 + 9.16]], closed: false },
    { pts: [[L, W / 2 - 9.16], [L - 5.5, W / 2 - 9.16], [L - 5.5, W / 2 + 9.16], [L, W / 2 + 9.16]], closed: false },
  ];
}
