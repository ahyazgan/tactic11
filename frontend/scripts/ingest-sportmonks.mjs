#!/usr/bin/env node
/**
 * Sportmonks GERÇEK VERİ ingest — Danimarka + İskoçya sonuçları (gol).
 *
 * Token'ın kapsamı: Danimarka Superliga (271) + İskoçya Premiership (501).
 * xG/predictions add-on YOK → GOL-temelli. İKİ lig × çok sezon çeker (token
 * her ikisinde de 21 tamamlanmış sezon veriyor) → daha geniş gerçek-veri tabanı
 * = daha dar güven bandı = daha sağlam trust. Bizim goals-only kalibrasyon+tahmin
 * motoru bunu okur. Token ../../.env'den; frontend bundle'ına GİRMEZ (build-time).
 *
 * Kullanım: node scripts/ingest-sportmonks.mjs [sezonSayısı=12]
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV = path.join(__dirname, "..", "..", ".env");
const OUT = path.join(__dirname, "..", "src", "lib", "sm-denmark.json");
const OUT_FX = path.join(__dirname, "..", "src", "lib", "sm-denmark-fixtures.json");
const B = "https://api.sportmonks.com/v3/football";

// Çekeceğimiz ligler — comp kodu kalibrasyon motorunda lig-bazlı taban için kullanılır.
const LEAGUES = [
  { id: 271, comp: "dk.1", label: "Danimarka Superliga" },
  { id: 501, comp: "sco.1", label: "İskoçya Premiership" },
];

const tok = fs.readFileSync(ENV, "utf8").match(/^SPORTMONKS_API_KEY=(.+)$/m)[1].trim().replace(/\r$/, "");
const g = (u) => fetch(u + (u.includes("?") ? "&" : "?") + "api_token=" + tok).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Bir sezonun fixtures'ını sayfalı çeker (büyük sezonlar tek sayfaya sığmaz). */
async function seasonFixtures(seasonId) {
  const all = [];
  let page = 1;
  for (;;) {
    const s = await g(`${B}/seasons/${seasonId}?include=fixtures.scores;fixtures.participants&page=${page}`);
    const fx = s.data?.fixtures || [];
    all.push(...fx);
    // season include sayfalama bazen tek sayfa döndürür; fixtures<300 ise dur.
    if (fx.length < 300) break;
    page++;
    if (page > 6) break;
    await sleep(120);
  }
  return all;
}

function parseFixture(f, comp, season) {
  const scs = f.scores || [];
  const hg = scs.find((x) => x.description === "CURRENT" && x.score?.participant === "home")?.score?.goals;
  const ag = scs.find((x) => x.description === "CURRENT" && x.score?.participant === "away")?.score?.goals;
  if (hg == null || ag == null) return null;
  const ps = f.participants || [];
  const home = ps.find((p) => p.meta?.location === "home")?.name;
  const away = ps.find((p) => p.meta?.location === "away")?.name;
  if (!home || !away) return null;
  return { date: (f.starting_at || "").slice(0, 10), home, away, hg, ag, comp, season: `${comp}:${season}` };
}

async function main() {
  const nSeasons = Number(process.argv[2] || 12);
  const results = [];
  const upcoming = [];
  let curSeasonLabel = "";

  for (const L of LEAGUES) {
    const lg = await g(`${B}/leagues/${L.id}?include=seasons`);
    const finished = (lg.data?.seasons || []).filter((s) => s.finished)
      .sort((a, b) => (a.name < b.name ? 1 : -1)).slice(0, nSeasons);
    console.log(`\n${L.label} (${L.id}) · ${finished.length} sezon: ${finished.map((s) => s.name).join(", ")}`);

    for (const se of finished) {
      const fx = await seasonFixtures(se.id);
      let n = 0;
      for (const f of fx) { const r = parseFixture(f, L.comp, se.name); if (r) { results.push(r); n++; } }
      console.log(`  ✓ ${se.name}: ${n} maç`);
      await sleep(120);
    }

    // Yaklaşan fikstürler — sadece Danimarka (canlı tahmin sayfası onu gösteriyor).
    if (L.id === 271) {
      const cur = (lg.data?.seasons || []).find((s) => !s.finished) || (lg.data?.seasons || [])[0];
      curSeasonLabel = cur?.name || "";
      const cs = await seasonFixtures(cur.id);
      for (const f of cs) {
        const played = (f.scores || []).some((x) => x.description === "CURRENT");
        if (played) continue;
        const ps = f.participants || [];
        const home = ps.find((p) => p.meta?.location === "home")?.name;
        const away = ps.find((p) => p.meta?.location === "away")?.name;
        if (!home || !away) continue;
        upcoming.push({ date: (f.starting_at || "").slice(0, 10), home, away });
      }
    }
  }

  results.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  fs.writeFileSync(OUT, JSON.stringify(results));
  const byComp = results.reduce((m, r) => ((m[r.comp] = (m[r.comp] || 0) + 1), m), {});
  console.log(`\n✓ ${results.length} gerçek maç → sm-denmark.json (${Math.round(fs.statSync(OUT).size / 1024)}KB)`, byComp);

  upcoming.sort((a, b) => (a.date < b.date ? -1 : 1));
  const next = upcoming.slice(0, 24);
  fs.writeFileSync(OUT_FX, JSON.stringify({ season: curSeasonLabel, fixtures: next }));
  console.log(`✓ ${next.length} yaklaşan maç (${curSeasonLabel}) → sm-denmark-fixtures.json`);
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
