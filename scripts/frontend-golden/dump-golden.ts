import { writeFileSync } from 'node:fs';
import { MockDatabase } from '../src/app/core/mock/mock-database';
import { assessHazards, hazardHistory } from '../src/app/core/mock/engine/hazards';
import { detectInsights } from '../src/app/core/mock/engine/insights';
import { interpretMetric } from '../src/app/core/mock/engine/interpret';
import { at, distanceAuOnDay } from '../src/app/core/mock/mission-plan';
const db = new MockDatabase();
const out: any = { runs: {} };
for (const hod of [14, 3]) {
  const hour = at(142, hod);
  const ctx = { db, hour, link: { mode: 'nominal' as const, delaySeconds: distanceAuOnDay(142) * 499.005, distanceAu: distanceAuOnDay(142) }, careerLimitMsv: 600 };
  const hz = assessHazards(ctx);
  out.runs[hod] = {
    hour,
    hazards: hz.map((h) => ({ crewId: h.crewId, hazard: h.hazard, score: h.score, status: h.status, headline: h.headline, explanation: h.explanation, drivers: h.drivers.map((d) => [d.label, d.value, d.contribution]) })),
    insights: detectInsights(ctx).map((i) => ({ id: i.id, severity: i.severity, title: i.title, confidence: i.confidence, detectedAt: i.detectedAt, summary: i.summary })),
    interp: ['hr', 'sleepDuration', 'co2', 'mood'].map((m) => { const r = interpretMetric(ctx, 'ahmad', m as any); return { metric: m, summary: r.summary, trend: r.trend, status: r.status, confidence: r.confidence, why: r.whyItMatters }; }),
    history: hazardHistory(ctx, 'isolation', 'hannan', 120, 142).map((s) => [Math.round(s.t * 100) / 100, s.v]),
  };
}
out.baselines = {};
for (const a of db.crew()) for (const m of ['hr', 'hrv', 'sleepDuration', 'mood', 'stress', 'co2', 'boneDensity', 'lymphocytes', 'doseRate', 'reactionTime']) out.baselines[`${a.id}:${m}`] = db.baseline(a.id, m as any);
out.samples = {};
for (const a of db.crew()) for (const m of ['hr', 'sleepDuration', 'radDose', 'co2', 'boneDensity', 'doseRate', 'cabinNoise', 'legStrength']) { const s = db.series(a.id, m as any); out.samples[`${a.id}:${m}`] = { n: s.length, first: s.slice(0, 4), mid: s[Math.floor(s.length / 2)], last: s[s.length - 1] }; }
out.checkIns = {}; for (const a of db.crew()) { const c = db.checkIns(a.id); out.checkIns[a.id] = { n: c.length, first: c[0], last: c[c.length - 1] }; }
out.exercise = {}; for (const a of db.crew()) { const e = db.exercise(a.id); out.exercise[a.id] = { n: e.length, done: e.filter((x) => x.done).length }; }
writeFileSync(process.argv[2], JSON.stringify(out, null, 1));
