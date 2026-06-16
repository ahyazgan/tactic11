#!/usr/bin/env node
/**
 * Lig maç SONUÇLARI + ŞUT verisi ingest — kalibrasyon/backtest için.
 *
 * Kaynak: datasets/football-datasets (GitHub raw — Node'dan erişilir). Tam lig
 * sezonları, her maçta skor + ŞUT + isabetli şut. Tek kaynak → isim eşleştirme
 * derdi yok. Şut, golden daha az gürültülü bir güç sinyali (xG-proxy) verir.
 *   kolonlar: Date,HomeTeam,AwayTeam,FTHG,FTAG,...,HS,AS,HST,AST,...
 *
 * Kullanım: node scripts/ingest-results.mjs            # varsayılan: top-5 × 6 sezon
 */

import fs from "fs";
import { fileURLToPath } from "url";
import path from "path";

const BASE = "https://raw.githubusercontent.com/datasets/football-datasets/master/datasets";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "src", "lib", "match-results.json");

const LEAGUES = [
  { slug: "premier-league", code: "en.1" },
  { slug: "la-liga", code: "es.1" },
  { slug: "bundesliga", code: "de.1" },
  { slug: "serie-a", code: "it.1" },
  { slug: "ligue-1", code: "fr.1" },
];
const SEASONS = ["1718", "1819", "1920", "2021", "2122", "2223"];

async function fetchText(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.text();
}

// Basit CSV satır ayrıştırıcı (alanlarda virgül yok bu veri setinde).
function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  const head = lines[0].split(",");
  const idx = (name) => head.indexOf(name);
  const c = { d: idx("Date"), h: idx("HomeTeam"), a: idx("AwayTeam"), hg: idx("FTHG"), ag: idx("FTAG"), hs: idx("HS"), as: idx("AS"), hst: idx("HST"), ast: idx("AST") };
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const f = lines[i].split(",");
    const hg = +f[c.hg], ag = +f[c.ag];
    if (!f[c.h] || !f[c.a] || Number.isNaN(hg) || Number.isNaN(ag)) continue;
    let date = f[c.d];
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(date)) { const [d, m, y] = date.split("/"); date = `${y}-${m}-${d}`; }
    rows.push({ date, home: f[c.h], away: f[c.a], hg, ag, hs: +f[c.hs] || 0, as: +f[c.as] || 0, hst: +f[c.hst] || 0, ast: +f[c.ast] || 0 });
  }
  return rows;
}

async function main() {
  const results = [];
  for (const season of SEASONS) {
    for (const lg of LEAGUES) {
      try {
        const txt = await fetchText(`${BASE}/${lg.slug}/season-${season}.csv`);
        const rows = parseCsv(txt);
        for (const r of rows) results.push({ ...r, comp: lg.code, season });
        console.log(`  ✓ ${lg.code} ${season}: ${rows.length} maç`);
      } catch (e) {
        console.log(`  ✗ ${lg.code} ${season}: ${e.message}`);
      }
    }
  }
  results.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  fs.writeFileSync(OUT, JSON.stringify(results));
  console.log(`\n✓ ${results.length} maç (skor + şut) → match-results.json (${Math.round(fs.statSync(OUT).size / 1024)}KB)`);
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
