#!/usr/bin/env node
/**
 * StatsBomb maç ingest — HERHANGİ bir StatsBomb Open Data maçını taktik analiz
 * kütüphanesine ekler. Ham event dosyasını (GitHub) çeker, parse eder (ortalama
 * pozisyon, pas ağı, şut haritası, savunma bloğu, PPDA/blok/koridor/build-up),
 * src/lib/statsbomb-matches.json'a ekler. Frontend bunu /tactical-real'de okur.
 *
 * Kullanım:
 *   node scripts/ingest-statsbomb.mjs <match_id> [match_id...]   # maç(lar) ekle
 *   node scripts/ingest-statsbomb.mjs --list <comp_id>/<season>  # mevcut maçları listele
 *   node scripts/ingest-statsbomb.mjs --comp "Etiket" <match_id> # komp. etiketiyle ekle
 *
 * Örnek: node scripts/ingest-statsbomb.mjs --list 43/106   (2022 Dünya Kupası)
 *        node scripts/ingest-statsbomb.mjs 3869685
 *
 * Not: StatsBomb Open Data Süper Lig içermez. Bilinen kompetisyonlar: Dünya Kupası
 * (43), Euro (55), La Liga (11), Bundesliga (9), Ligue 1 (7), Şampiyonlar Ligi (16).
 */

import fs from "fs";
import { fileURLToPath } from "url";
import path from "path";

const BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LIB_PATH = path.join(__dirname, "..", "src", "lib", "statsbomb-matches.json");

const nx = (l) => Math.round((l[0] / 120) * 1000) / 10;
const ny = (l) => Math.round((l[1] / 80) * 1000) / 10;
const DEF = new Set(["Pressure", "Duel", "Interception", "Block", "Ball Recovery", "Clearance", "Foul Committed"]);

// xT (Expected Threat) yüzeyi — 12 sütun (x) × 8 satır (y). Kaleye doğru ve merkeze
// doğru artan tehdit (Karun Singh xT mantığı). Pas/taşıma ilerlemesi bu yüzeyden ölçülür.
const XT = Array.from({ length: 12 }, (_, c) =>
  Array.from({ length: 8 }, (_, r) => {
    const central = 1 - (Math.abs(r - 3.5) / 3.5) * 0.35;
    return Math.round(Math.pow(c / 11, 2.7) * 0.26 * central * 10000) / 10000;
  }));
const bc = (xv) => Math.max(0, Math.min(11, Math.floor((xv / 100) * 12)));
const br = (yv) => Math.max(0, Math.min(7, Math.floor((yv / 100) * 8)));

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function parseTeam(ev, tn, nick = {}) {
  const te = ev.filter((e) => e.team?.name === tn);
  const opp = ev.filter((e) => e.team && e.team.name !== tn);
  const sx = ev.find((e) => e.type.name === "Starting XI" && e.team.name === tn);
  // Görünen ad = StatsBomb takma adı (Messi/Mbappé/Rodri), yoksa tam yasal ad.
  const disp = (full) => nick[full] || full;
  const xi = sx.tactics.lineup.map((p) => ({ num: p.jersey_number, name: p.player.name, disp: disp(p.player.name), pos: p.position.name }));
  const xiN = new Set(xi.map((p) => p.name));
  const byName = Object.fromEntries(xi.map((p) => [p.name, p]));
  const gen = {}, def = {}, pc = {}, edge = {};
  for (const e of te) {
    if (e.player && xiN.has(e.player.name) && e.location) {
      const n = [nx(e.location), ny(e.location)];
      (gen[e.player.name] ??= [0, 0, 0]); gen[e.player.name][0] += n[0]; gen[e.player.name][1] += n[1]; gen[e.player.name][2]++;
      if (DEF.has(e.type.name)) { (def[e.player.name] ??= [0, 0, 0]); def[e.player.name][0] += n[0]; def[e.player.name][1] += n[1]; def[e.player.name][2]++; }
    }
    if (e.type.name === "Pass" && !e.pass.outcome && e.pass.recipient && xiN.has(e.player.name) && xiN.has(e.pass.recipient.name)) {
      pc[e.player.name] = (pc[e.player.name] || 0) + 1;
      const k = [e.player.name, e.pass.recipient.name].sort().join("|");
      edge[k] = (edge[k] || 0) + 1;
    }
  }
  const nodes = xi.map((p) => { const a = gen[p.name]; return a ? { num: p.num, name: p.disp, pos: p.pos, x: Math.round(a[0] / a[2] * 10) / 10, y: Math.round(a[1] / a[2] * 10) / 10, passes: pc[p.name] || 0 } : null; }).filter(Boolean);
  const edges = Object.entries(edge).map(([k, c]) => { const [a, b] = k.split("|"); return { from: byName[a].num, to: byName[b].num, count: c }; }).filter((e) => e.count >= 4).sort((x, y) => y.count - x.count);
  const defShape = xi.map((p) => { const d = def[p.name], g = gen[p.name], a = (d && d[2] >= 3) ? d : g; return a ? { num: p.num, pos: p.pos, x: Math.round(a[0] / a[2] * 10) / 10, y: Math.round(a[1] / a[2] * 10) / 10 } : null; }).filter(Boolean);
  // Şutlar: penaltı atışlarını (period 5 = shootout) HARİÇ tut (xG/skoru şişirir).
  const shots = te.filter((e) => e.type.name === "Shot" && e.period <= 4).map((e) => ({ x: nx(e.location), y: ny(e.location), xg: Math.round((e.shot.statsbomb_xg || 0) * 1000) / 1000, goal: e.shot.outcome.name === "Goal", minute: e.minute }));
  const ownGoalsFor = te.filter((e) => e.type.name === "Own Goal For").length;   // kendi kalesine goller (lehimize)
  let dx = 0, dn = 0; for (const e of te) if (DEF.has(e.type.name) && e.location) { dx += nx(e.location); dn++; }
  const blockHeightM = dn ? Math.round(dx / dn / 100 * 105 * 10) / 10 : 40;
  const ourHigh = te.filter((e) => DEF.has(e.type.name) && e.location && nx(e.location) > 40).length;
  const ppda = ourHigh ? Math.round(opp.filter((e) => e.type.name === "Pass").length / ourHigh * 10) / 10 : 0;
  let L = 0, C = 0, R = 0; for (const e of te) if (e.type.name === "Pass" && e.pass?.end_location && nx(e.pass.end_location) > 67) { const y = ny(e.pass.end_location); if (y < 33) L++; else if (y > 67) R++; else C++; }
  const ct = L + C + R || 1;
  const backP = te.filter((e) => e.type.name === "Pass" && e.location && nx(e.location) < 40);
  const longP = backP.filter((e) => (e.pass.length || 0) > 30).length;
  // Isı haritası (dokunuş yoğunluğu), pres bölgeleri (savunma aksiyon ısısı), xT,
  // progresyon pasları (topu kaleye taşıyan en tehditli paslar).
  const heat = Array.from({ length: 12 }, () => Array(8).fill(0));
  const defHeat = Array.from({ length: 12 }, () => Array(8).fill(0));
  const progAll = [];
  let xt = 0;
  for (const e of te) {
    if (e.location) {
      heat[bc(nx(e.location))][br(ny(e.location))]++;
      if (DEF.has(e.type.name)) defHeat[bc(nx(e.location))][br(ny(e.location))]++;
    }
    const end = e.type.name === "Pass" ? (!e.pass.outcome && e.pass.end_location) : e.type.name === "Carry" ? e.carry?.end_location : null;
    if (end && e.location) {
      const sx2 = nx(e.location), sy2 = ny(e.location), ex2 = nx(end), ey2 = ny(end);
      const d = XT[bc(ex2)][br(ey2)] - XT[bc(sx2)][br(sy2)];
      if (d > 0) xt += d;
      // progresyon pası: ileriye ≥15 (0-100) + hücum yarısına + pozitif xT
      if (e.type.name === "Pass" && ex2 - sx2 >= 15 && ex2 > 50 && d > 0) {
        progAll.push({ x1: sx2, y1: sy2, x2: ex2, y2: ey2, xt: Math.round(d * 1000) / 1000 });
      }
    }
  }
  const progPasses = progAll.sort((a, b) => b.xt - a.xt).slice(0, 14);

  // Oyuncu-seviyesi teknik metrikler (gerçek event'lerden, başlangıç 11).
  const ps = {};
  for (const e of te) {
    if (!e.player || !xiN.has(e.player.name)) continue;
    const p = (ps[e.player.name] ??= { touches: 0, passC: 0, passA: 0, prog: 0, xt: 0, shots: 0, xg: 0, keyP: 0, def: 0, carries: 0, heat: Array.from({ length: 12 }, () => Array(8).fill(0)), passes: [] });
    if (e.location) { p.touches++; p.heat[bc(nx(e.location))][br(ny(e.location))]++; }
    if (DEF.has(e.type.name)) p.def++;
    if (e.type.name === "Shot" && e.period <= 4) { p.shots++; p.xg += e.shot.statsbomb_xg || 0; }
    if (e.type.name === "Pass") {
      p.passA++;
      if (!e.pass.outcome) p.passC++;
      if (e.pass.shot_assist || e.pass.goal_assist) p.keyP++;
      if (!e.pass.outcome && e.pass.end_location && e.location) {
        const sx2 = nx(e.location), sy2 = ny(e.location), ex2 = nx(e.pass.end_location), ey2 = ny(e.pass.end_location);
        const d = XT[bc(ex2)][br(ey2)] - XT[bc(sx2)][br(sy2)];
        if (d > 0) p.xt += d;
        if (ex2 - sx2 >= 15 && ex2 > 50 && d > 0) p.prog++;
        p.passes.push([Math.round(sx2), Math.round(sy2), Math.round(ex2), Math.round(ey2)]);
      }
    }
    if (e.type.name === "Carry" && e.carry?.end_location && e.location) {
      const sx2 = nx(e.location), ex2 = nx(e.carry.end_location);
      const d = XT[bc(ex2)][br(ny(e.carry.end_location))] - XT[bc(sx2)][br(ny(e.location))];
      if (d > 0) p.xt += d;
      if (ex2 - sx2 >= 15) p.carries++;
    }
  }
  const players = xi.map((pl) => { const s = ps[pl.name] || {}; return { num: pl.num, name: pl.disp, pos: pl.pos, touches: s.touches || 0, passC: s.passC || 0, passAcc: s.passA ? Math.round(s.passC / s.passA * 100) : 0, prog: s.prog || 0, xt: Math.round((s.xt || 0) * 100) / 100, shots: s.shots || 0, xg: Math.round((s.xg || 0) * 100) / 100, keyP: s.keyP || 0, def: s.def || 0, carries: s.carries || 0, heat: s.heat || [], passes: (s.passes || []).sort((a, b) => (b[2] - b[0]) - (a[2] - a[0])).slice(0, 18) }; });
  return {
    team: tn, formation: sx.tactics.formation, lineup: xi, nodes, edges, shots,
    metrics: { passes: te.filter((e) => e.type.name === "Pass").length, shots: shots.length, xg: Math.round(shots.reduce((s, x) => s + x.xg, 0) * 100) / 100, goals: shots.filter((s) => s.goal).length + ownGoalsFor, possession: 0 },
    defShape, blockHeightM, ppda, channels: { left: Math.round(L / ct * 100), center: Math.round(C / ct * 100), right: Math.round(R / ct * 100) }, directPct: backP.length ? Math.round(longP / backP.length * 100) : 0,
    heat, xt: Math.round(xt * 100) / 100, defHeat, progPasses, players,
  };
}

async function ingestMatch(id, comp) {
  process.stdout.write(`  ↓ ${id} indiriliyor… `);
  const ev = await fetchJson(`${BASE}/events/${id}.json`);
  // Takma adlar (Messi/Mbappé/Rodri) ayrı lineups endpoint'inde; tam yasal ad yerine onları kullan.
  const nick = {};
  try {
    const lus = await fetchJson(`${BASE}/lineups/${id}.json`);
    for (const tm of lus) for (const p of tm.lineup) if (p.player_nickname) nick[p.player_name] = p.player_nickname;
  } catch { /* lineup yoksa tam ada düş */ }
  const tns = [...new Set(ev.filter((e) => e.team).map((e) => e.team.name))];
  const teams = tns.map((t) => parseTeam(ev, t, nick));
  const tot = teams.reduce((s, t) => s + t.metrics.passes, 0);
  teams.forEach((t) => (t.metrics.possession = Math.round(t.metrics.passes / tot * 100)));
  const title = `${teams[0].team} ${teams[0].metrics.goals}-${teams[1].metrics.goals} ${teams[1].team}`;
  console.log(`✓ ${title} (${ev.length} event)`);
  return { match: title, comp: comp || "StatsBomb Open Data", matchId: id, teams };
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] === "--list") {
    const [comp, season] = args[1].split("/");
    const matches = await fetchJson(`${BASE}/matches/${comp}/${season}.json`);
    matches.sort((a, b) => (a.match_date > b.match_date ? 1 : -1)).forEach((m) =>
      console.log(`${m.match_id}\t${m.home_team.home_team_name} ${m.home_score}-${m.away_score} ${m.away_team.away_team_name}\t(${m.competition_stage?.name})`));
    console.log(`\n${matches.length} maç. Eklemek için: node scripts/ingest-statsbomb.mjs <match_id>`);
    return;
  }
  let comp = "";
  if (args[0] === "--comp") { comp = args[1]; args.splice(0, 2); }
  if (!args.length) { console.error("Kullanım: node scripts/ingest-statsbomb.mjs <match_id> | --list <comp>/<season>"); process.exit(1); }

  const lib = fs.existsSync(LIB_PATH) ? JSON.parse(fs.readFileSync(LIB_PATH, "utf8")) : [];
  const existing = new Set(lib.map((m) => m.matchId));
  console.log(`Mevcut kütüphane: ${lib.length} maç. Ekleniyor:`);
  for (const arg of args) {
    const id = Number(arg);
    if (existing.has(id)) { console.log(`  • ${id} zaten var, atlandı.`); continue; }
    try { lib.push(await ingestMatch(id, comp)); existing.add(id); }
    catch (e) { console.error(`  ✗ ${id} başarısız: ${e.message}`); }
  }
  fs.writeFileSync(LIB_PATH, JSON.stringify(lib));
  console.log(`\n✓ Kütüphane güncellendi: ${lib.length} maç · ${Math.round(fs.statSync(LIB_PATH).size / 1024)}KB`);
  console.log("  → /tactical-real'de dropdown'dan seçilebilir (dev sunucu otomatik yeniler).");
}

main().catch((e) => { console.error("Hata:", e.message); process.exit(1); });
