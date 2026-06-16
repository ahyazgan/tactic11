#!/usr/bin/env node
/**
 * GOL ZAMANLAMASI + DEVRE SKORU ingest — gol-zamanlaması modeli için.
 *
 * Her maçın GOL DAKİKALARINI (events type_id 14) ve DEVRE skorunu (1ST_HALF)
 * çeker → sm-timing.json. Amaç: maç-içi motorda "goller 90 dk'ya eşit dağılır"
 * naif varsayımını GERÇEK gol-zamanlaması eğrisiyle değiştirip out-of-sample test.
 *
 * Çıktı: { "date|home|away": { h1, a1, mins:[gol dakikaları] } }  (h1/a1 = devre skoru)
 * Kullanım: node scripts/ingest-timing.mjs [sezonSayısı=12]
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV = path.join(__dirname, "..", "..", ".env");
const OUT = path.join(__dirname, "..", "src", "lib", "sm-timing.json");
const B = "https://api.sportmonks.com/v3/football";
const LEAGUES = [{ id: 271, comp: "dk.1" }, { id: 501, comp: "sco.1" }];

const tok = fs.readFileSync(ENV, "utf8").match(/^SPORTMONKS_API_KEY=(.+)$/m)[1].trim().replace(/\r$/, "");
const g = (u) => fetch(u + (u.includes("?") ? "&" : "?") + "api_token=" + tok).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const nSeasons = Number(process.argv[2] || 12);
  const out = {};
  let total = 0, withGoals = 0, withHT = 0;

  for (const L of LEAGUES) {
    const lg = await g(`${B}/leagues/${L.id}?include=seasons`);
    const finished = (lg.data?.seasons || []).filter((s) => s.finished)
      .sort((a, b) => (a.name < b.name ? 1 : -1)).slice(0, nSeasons);
    console.log(`\n${L.comp} · ${finished.length} sezon`);

    for (const se of finished) {
      const s = await g(`${B}/seasons/${se.id}?include=fixtures.events;fixtures.scores;fixtures.participants`);
      const fx = s.data?.fixtures || [];
      let n = 0;
      for (const f of fx) {
        const ps = f.participants || [];
        const home = ps.find((p) => p.meta?.location === "home")?.name;
        const away = ps.find((p) => p.meta?.location === "away")?.name;
        const homeId = ps.find((p) => p.meta?.location === "home")?.id;
        if (!home || !away) continue;
        const date = (f.starting_at || "").slice(0, 10);
        total++;
        // Goller: type_id 14, [dakika, taraf] (0=ev, 1=dep). Dakikada skor yeniden kurmak için.
        const goals = (f.events || []).filter((e) => e.type_id === 14);
        const mins = goals.map((e) => [(e.minute ?? 0) + (e.extra_minute ?? 0), e.participant_id === homeId ? 0 : 1])
          .filter((x) => x[0] > 0).sort((a, b) => a[0] - b[0]);
        // Devre skoru (1ST_HALF, cumulative): home/away.
        const sc = f.scores || [];
        const h1 = sc.find((x) => x.description === "1ST_HALF" && x.score?.participant === "home")?.score?.goals;
        const a1 = sc.find((x) => x.description === "1ST_HALF" && x.score?.participant === "away")?.score?.goals;
        const rec = {};
        if (mins.length) { rec.mins = mins; withGoals++; }
        if (h1 != null && a1 != null) { rec.h1 = h1; rec.a1 = a1; withHT++; }
        if (rec.mins || rec.h1 != null) { out[`${date}|${home}|${away}`] = rec; n++; }
      }
      console.log(`  ${se.name}: ${n} maç (gol/devre verisi)`);
      await sleep(150);
    }
  }
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`\n✓ ${total} maç tarandı · ${withGoals} gol-dakikalı · ${withHT} devre-skorlu → sm-timing.json (${Math.round(fs.statSync(OUT).size / 1024)}KB)`);
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
