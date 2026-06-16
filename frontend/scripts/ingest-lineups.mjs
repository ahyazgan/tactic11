#!/usr/bin/env node
/**
 * Sportmonks LINEUP ingest — maç-öncesi kadro sinyali için.
 *
 * Her maçın gerçek ilk-11'ini (player_id listesi) çeker → sm-lineups.json.
 * Amaç: "beklenen 11 vs gerçek 11" güç düzeltmesini GERÇEK out-of-sample test
 * etmek. Tek istekte sezon başına fixtures.lineups geliyor (verimli).
 *
 * Çıktı: { fixtureKey: { home:[pid...], away:[pid...] } }  (key=date|home|away)
 * Kullanım: node scripts/ingest-lineups.mjs [sezonSayısı=12]
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV = path.join(__dirname, "..", "..", ".env");
const OUT = path.join(__dirname, "..", "src", "lib", "sm-lineups.json");
const OUT_NAMES = path.join(__dirname, "..", "src", "lib", "sm-player-names.json");
const B = "https://api.sportmonks.com/v3/football";
const LEAGUES = [{ id: 271, comp: "dk.1" }, { id: 501, comp: "sco.1" }];

const tok = fs.readFileSync(ENV, "utf8").match(/^SPORTMONKS_API_KEY=(.+)$/m)[1].trim().replace(/\r$/, "");
const g = (u) => fetch(u + (u.includes("?") ? "&" : "?") + "api_token=" + tok).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const nSeasons = Number(process.argv[2] || 12);
  const out = {};
  const names = {};                 // player_id → en son görülen ad (güncel)
  const teamOf = {};                // player_id → comp|team (son görülen kulüp)
  const posCount = {};              // player_id → {position_id: sayı} (en sık = ana mevki)
  const POS_MAP = { 24: "GK", 25: "DEF", 26: "MID", 27: "ATT" };
  let total = 0, withLu = 0;

  for (const L of LEAGUES) {
    const lg = await g(`${B}/leagues/${L.id}?include=seasons`);
    const finished = (lg.data?.seasons || []).filter((s) => s.finished)
      .sort((a, b) => (a.name < b.name ? 1 : -1)).slice(0, nSeasons);
    console.log(`\n${L.comp} · ${finished.length} sezon`);

    for (const se of finished) {
      const s = await g(`${B}/seasons/${se.id}?include=fixtures.lineups;fixtures.participants`);
      const fx = s.data?.fixtures || [];
      let n = 0;
      for (const f of fx) {
        const ps = f.participants || [];
        const home = ps.find((p) => p.meta?.location === "home")?.name;
        const away = ps.find((p) => p.meta?.location === "away")?.name;
        if (!home || !away) continue;
        const homeId = ps.find((p) => p.meta?.location === "home")?.id;
        const lu = f.lineups || [];
        total++;
        const starters = lu.filter((x) => x.type_id === 11);
        if (starters.length < 18) continue;        // iki takım 11'i yoksa atla
        const hs = starters.filter((x) => x.team_id === homeId);
        const as = starters.filter((x) => x.team_id !== homeId);
        const hp = hs.map((x) => x.player_id), ap = as.map((x) => x.player_id);
        if (hp.length < 9 || ap.length < 9) continue;
        const date = (f.starting_at || "").slice(0, 10);
        out[`${date}|${home}|${away}`] = { h: hp, a: ap };
        // İsim + kulüp + mevki sayımı (en son görülen ad/kulüp = güncel) — null player_id atla.
        const tally = (x) => { if (x.position_id != null) { (posCount[x.player_id] ??= {})[x.position_id] = ((posCount[x.player_id] ??= {})[x.position_id] || 0) + 1; } };
        for (const x of hs) if (x.player_id != null && x.player_name) { names[x.player_id] = x.player_name; teamOf[x.player_id] = `${L.comp}|${home}`; tally(x); }
        for (const x of as) if (x.player_id != null && x.player_name) { names[x.player_id] = x.player_name; teamOf[x.player_id] = `${L.comp}|${away}`; tally(x); }
        withLu++; n++;
      }
      console.log(`  ${se.name}: ${n} maç lineup`);
      await sleep(150);
    }
  }
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`\n✓ ${withLu}/${total} maç lineup → sm-lineups.json (${Math.round(fs.statSync(OUT).size / 1024)}KB)`);

  // player_id → {ad, kulüp, mevki} sözlüğü (canlı kadro-etkisi UI'sı için).
  const dict = {};
  for (const id in names) {
    const pc = posCount[id] || {};
    const top = Object.keys(pc).sort((a, b) => pc[b] - pc[a])[0];
    dict[id] = { n: names[id], t: teamOf[id] || "", p: POS_MAP[top] || "" };
  }
  fs.writeFileSync(OUT_NAMES, JSON.stringify(dict));
  console.log(`✓ ${Object.keys(dict).length} oyuncu adı → sm-player-names.json (${Math.round(fs.statSync(OUT_NAMES).size / 1024)}KB)`);
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
