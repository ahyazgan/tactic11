#!/usr/bin/env node
/**
 * DİZİLİŞ (formation) ingest — gerçek taktik diziliş analizi için.
 *
 * Her maçın resmi dizilişini (formations include: "4-3-3","3-4-2-1"...) takım
 * başına toplar → sm-formations.json. Amaç: "bu takım en sık X dizilişiyle oynar,
 * evde/deplasmanda değişir mi" gerçek taktik bağlam. (Daha önce veri yok sanılıyordu;
 * token formations veriyor.)
 *
 * Çıktı: { "comp|team": { top, topPct, games, dist:[[diziliş,sayı]...], home, away } }
 * Kullanım: node scripts/ingest-formations.mjs [sezonSayısı=12]
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV = path.join(__dirname, "..", "..", ".env");
const OUT = path.join(__dirname, "..", "src", "lib", "sm-formations.json");
const B = "https://api.sportmonks.com/v3/football";
const LEAGUES = [{ id: 271, comp: "dk.1" }, { id: 501, comp: "sco.1" }];

const tok = fs.readFileSync(ENV, "utf8").match(/^SPORTMONKS_API_KEY=(.+)$/m)[1].trim().replace(/\r$/, "");
const g = (u) => fetch(u + (u.includes("?") ? "&" : "?") + "api_token=" + tok).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const nSeasons = Number(process.argv[2] || 12);
  const agg = {};   // comp|team → {dist:{f:n}, home:{f:n}, away:{f:n}, games}
  let total = 0, withForm = 0;

  for (const L of LEAGUES) {
    const lg = await g(`${B}/leagues/${L.id}?include=seasons`);
    const finished = (lg.data?.seasons || []).filter((s) => s.finished)
      .sort((a, b) => (a.name < b.name ? 1 : -1)).slice(0, nSeasons);
    console.log(`\n${L.comp} · ${finished.length} sezon`);

    for (const se of finished) {
      const s = await g(`${B}/seasons/${se.id}?include=fixtures.formations;fixtures.participants`);
      const fx = s.data?.fixtures || [];
      let n = 0;
      for (const f of fx) {
        const ps = f.participants || [];
        const home = ps.find((p) => p.meta?.location === "home");
        const away = ps.find((p) => p.meta?.location === "away");
        if (!home || !away) continue;
        const nameOf = (pid) => pid === home.id ? home.name : pid === away.id ? away.name : null;
        const forms = f.formations || [];
        total++;
        let used = false;
        for (const fm of forms) {
          const team = nameOf(fm.participant_id); if (!team || !fm.formation) continue;
          const key = `${L.comp}|${team}`;
          const a = (agg[key] ??= { dist: {}, home: {}, away: {}, games: 0 });
          a.dist[fm.formation] = (a.dist[fm.formation] || 0) + 1;
          const side = fm.location === "home" ? a.home : a.away;
          side[fm.formation] = (side[fm.formation] || 0) + 1;
          a.games++; used = true;
        }
        if (used) { n++; withForm++; }
      }
      console.log(`  ${se.name}: ${n} maç diziliş`);
      await sleep(150);
    }
  }
  const topOf = (d) => Object.entries(d).sort((a, b) => b[1] - a[1])[0];
  const out = {};
  for (const k in agg) {
    const a = agg[k];
    const dist = Object.entries(a.dist).sort((x, y) => y[1] - x[1]);
    const tot = dist.reduce((s, [, n]) => s + n, 0) || 1;
    const top = dist[0];
    const hTop = Object.keys(a.home).length ? topOf(a.home) : null;
    const aTop = Object.keys(a.away).length ? topOf(a.away) : null;
    out[k] = {
      top: top?.[0] ?? null, topPct: top ? Math.round((top[1] / tot) * 100) : 0,
      games: tot, dist: dist.slice(0, 4),
      home: hTop?.[0] ?? null, away: aTop?.[0] ?? null,
    };
  }
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`\n✓ ${withForm}/${total} maç diziliş · ${Object.keys(out).length} takım → sm-formations.json (${Math.round(fs.statSync(OUT).size / 1024)}KB)`);
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
