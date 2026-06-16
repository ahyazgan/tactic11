#!/usr/bin/env node
/**
 * MAÇ İSTATİSTİĞİ ingest — takım STİLİ için (betimleyici, tahmine sokulmaz).
 *
 * Her maçın topla-oynama % (type_id 45) + korner (34) değerlerini çeker, takım
 * başına ortalar → sm-stats.json. Amaç: "bu takım topa-sahip mi / direkt mi"
 * antrenör bağlamı. Possession sonuç-tahmininde zayıf olduğu için motora GİRMEZ.
 *
 * Çıktı: { "comp|team": { poss, corners, games } }
 * Kullanım: node scripts/ingest-stats.mjs [sezonSayısı=12]
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV = path.join(__dirname, "..", "..", ".env");
const OUT = path.join(__dirname, "..", "src", "lib", "sm-stats.json");
const B = "https://api.sportmonks.com/v3/football";
const LEAGUES = [{ id: 271, comp: "dk.1" }, { id: 501, comp: "sco.1" }];
const POSS = 45, CORNERS = 34;

const tok = fs.readFileSync(ENV, "utf8").match(/^SPORTMONKS_API_KEY=(.+)$/m)[1].trim().replace(/\r$/, "");
const g = (u) => fetch(u + (u.includes("?") ? "&" : "?") + "api_token=" + tok).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const nSeasons = Number(process.argv[2] || 12);
  const agg = {};   // comp|team → {poss, posN, corners, cornN, games}
  let total = 0, withStat = 0;

  for (const L of LEAGUES) {
    const lg = await g(`${B}/leagues/${L.id}?include=seasons`);
    const finished = (lg.data?.seasons || []).filter((s) => s.finished)
      .sort((a, b) => (a.name < b.name ? 1 : -1)).slice(0, nSeasons);
    console.log(`\n${L.comp} · ${finished.length} sezon`);

    for (const se of finished) {
      const s = await g(`${B}/seasons/${se.id}?include=fixtures.statistics;fixtures.participants`);
      const fx = s.data?.fixtures || [];
      let n = 0;
      for (const f of fx) {
        const ps = f.participants || [];
        const home = ps.find((p) => p.meta?.location === "home");
        const away = ps.find((p) => p.meta?.location === "away");
        if (!home || !away) continue;
        const nameOf = (pid) => pid === home.id ? home.name : pid === away.id ? away.name : null;
        const st = f.statistics || [];
        total++;
        let used = false;
        for (const x of st) {
          const team = nameOf(x.participant_id); if (!team) continue;
          const key = `${L.comp}|${team}`;
          const a = (agg[key] ??= { poss: 0, posN: 0, corners: 0, cornN: 0, games: 0 });
          const v = x.data?.value;
          if (x.type_id === POSS && typeof v === "number") { a.poss += v; a.posN++; used = true; }
          else if (x.type_id === CORNERS && typeof v === "number") { a.corners += v; a.cornN++; used = true; }
        }
        if (used) { n++; withStat++; }
      }
      console.log(`  ${se.name}: ${n} maç istatistik`);
      await sleep(150);
    }
  }
  // ortala
  const out = {};
  for (const k in agg) {
    const a = agg[k];
    out[k] = { poss: a.posN ? Math.round((a.poss / a.posN) * 10) / 10 : null, corners: a.cornN ? Math.round((a.corners / a.cornN) * 10) / 10 : null, games: Math.max(a.posN, a.cornN) };
  }
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`\n✓ ${withStat}/${total} maç istatistik · ${Object.keys(out).length} takım → sm-stats.json (${Math.round(fs.statSync(OUT).size / 1024)}KB)`);
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
