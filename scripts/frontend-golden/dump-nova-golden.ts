import { writeFileSync } from 'node:fs';
import { MockDatabase } from '../src/app/core/mock/mock-database';
import { novaRespond, novaGreeting } from '../src/app/core/mock/nova';
import { at } from '../src/app/core/mock/mission-plan';
const db = new MockDatabase();
const idle = { pendingSafetyCheck: false, awaitingCheckIn: false };
const ctx = (state: any = idle, prev?: string) => ({ db, crewId: 'hannan', hour: at(142, 14), delaySeconds: 332, surgeon: 'Haleem', state, previousText: prev });
const out: any = {};
for (const t of ["can you do my check-in? slept badly, feeling low, bit of a headache", "I want to die", "what's the point", "I have chest pain", "tell Haleem I would like a private call this week", "I feel anxious", "my back hurts and my vision is blurry", "I miss my family a lot", "I am nervous about the EVA", "I can't sleep", "we had an argument with a crewmate", "thanks", "hello", "random words"]) {
  const r = novaRespond(ctx(), t);
  out[t] = { replies: r.replies, safety: r.safety, state: r.state };
}
out['__greeting'] = novaGreeting(ctx());
out['__yes_after_ask'] = novaRespond(ctx({ pendingSafetyCheck: true, awaitingCheckIn: false }), 'yes');
out['__no_after_ask'] = novaRespond(ctx({ pendingSafetyCheck: true, awaitingCheckIn: false }), 'no');
out['__awaiting'] = novaRespond(ctx({ pendingSafetyCheck: false, awaitingCheckIn: true }), 'slept well, feeling great, lots of energy');
out['__share_prev'] = novaRespond(ctx(idle, 'I need some time off'), 'please tell the doctor');
writeFileSync(process.argv[2], JSON.stringify(out, null, 1));
