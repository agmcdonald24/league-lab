// The trigger offline (Wave I-H, IH-1): GitHub's API mocked, the KV binding `STATE` faked in memory.
//   node ops/nightly-trigger/test.mjs        (no dependencies; exits 1 on the first failed check)
// Checks: without STATE the page says the dispatch is not recorded and the morning run still dispatches; with STATE a
// 204 is recorded as ok and shown; a 401 is recorded with its status and time, shown as FAILED, and re-thrown (the
// Worker's own log marks the invocation failed); a re-check hour with a success today dispatches nothing and records
// nothing; no token at a trigger hour is recorded as such.
import assert from "node:assert/strict";
import worker, { gameSlot, morningSince } from "./src/index.js";

const ENV = { GITHUB_REPO: "owner/league-lab", WORKFLOW_FILE: "nightly.yml", GIT_REF: "main", FIRE_HOUR_ET: "7", CHECK_HOURS_ET: "9,11", GITHUB_TOKEN: "t" };
// 07:37 EDT = 11:37 UTC; 09:37 EDT = 13:37 UTC (2026-10-05, a Monday)
const MORNING = Date.UTC(2026, 9, 5, 11, 37);
const RECHECK = Date.UTC(2026, 9, 5, 13, 37);

function kv() {
  const m = new Map();
  return { m, get: async (k) => (m.has(k) ? m.get(k) : null), put: async (k, v) => void m.set(k, v) };
}

let dispatchStatus = 204;
let runs = [];
const calls = [];
globalThis.fetch = async (url, init = {}) => {
  calls.push(`${init.method || "GET"} ${url}`);
  if (String(url).endsWith("/dispatches")) return new Response(dispatchStatus === 204 ? null : '{"message":"Bad credentials"}', { status: dispatchStatus });
  if (String(url).includes("/runs?")) return Response.json({ workflow_runs: runs });
  return new Response("not mocked", { status: 599 });
};
const quiet = { log: console.log, error: console.error };
console.log = () => {};
console.error = () => {};

async function page(env) {
  const r = await worker.fetch(new Request("https://trigger.example/"), env);
  return r.text();
}

try {
  // 1. no binding: works as before, the page says so
  dispatchStatus = 204;
  await worker.scheduled({ scheduledTime: MORNING }, { ...ENV }, {});
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, 1);
  assert.match(await page({ ...ENV }), /last dispatch: not recorded \(no STATE binding/);

  // 2. with STATE: a success is recorded and shown
  const state = kv();
  await worker.scheduled({ scheduledTime: MORNING }, { ...ENV, STATE: state }, {});
  const ok = JSON.parse(state.m.get("last_dispatch"));
  assert.equal(ok.ok, true);
  assert.equal(ok.status, 204);
  assert.equal(ok.hour_et, 7);
  assert.equal(ok.why, "the morning run");
  assert.match(await page({ ...ENV, STATE: state }), /last dispatch: ok \(HTTP 204\) at Oct 5, 2026, 7:37 AM ET — the morning run/);

  // 3. a 401: recorded with the status and the time, shown as FAILED, re-thrown
  dispatchStatus = 401;
  await assert.rejects(worker.scheduled({ scheduledTime: MORNING }, { ...ENV, STATE: state }, {}), /dispatch: HTTP 401/);
  const bad = JSON.parse(state.m.get("last_dispatch"));
  assert.equal(bad.ok, false);
  assert.equal(bad.status, 401);
  assert.match(bad.error, /Bad credentials/);
  assert.match(await page({ ...ENV, STATE: state }), /last dispatch: FAILED at Oct 5, 2026, 7:37 AM ET — the morning run: HTTP 401 dispatch: HTTP 401/);

  // 4. a re-check with a success today: nothing dispatched, the record untouched
  dispatchStatus = 204;
  runs = [{ run_number: 9, event: "workflow_dispatch", status: "completed", conclusion: "success", created_at: "2026-10-05T11:37:40Z" }];
  const before = state.m.get("last_dispatch");
  const posts = calls.filter((c) => c.startsWith("POST")).length;
  await worker.scheduled({ scheduledTime: RECHECK }, { ...ENV, STATE: state }, {});
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, posts);
  assert.equal(state.m.get("last_dispatch"), before);

  // 5. a re-check with today's run failed: dispatched again and recorded as a re-check
  runs = [{ run_number: 9, event: "workflow_dispatch", status: "completed", conclusion: "failure", created_at: "2026-10-05T11:37:40Z" }];
  await worker.scheduled({ scheduledTime: RECHECK }, { ...ENV, STATE: state }, {});
  const again = JSON.parse(state.m.get("last_dispatch"));
  assert.equal(again.ok, true);
  assert.equal(again.hour_et, 9);
  assert.match(again.why, /re-check/);

  // 6. no token at a trigger hour: nothing dispatched, the reason recorded
  const s2 = kv();
  const n = calls.length;
  await worker.scheduled({ scheduledTime: MORNING }, { ...ENV, GITHUB_TOKEN: "", STATE: s2 }, {});
  assert.equal(calls.length, n);
  assert.equal(JSON.parse(s2.m.get("last_dispatch")).error, "no GITHUB_TOKEN secret");

  // 7. a broken binding never fails the run
  const broken = { get: async () => { throw new Error("kv down"); }, put: async () => { throw new Error("kv down"); } };
  await worker.scheduled({ scheduledTime: MORNING }, { ...ENV, STATE: broken }, {});
  assert.match(await page({ ...ENV, STATE: broken }), /last dispatch: could not read STATE \(kv down\)/);

  // 8. PO (Wave I-W): game-day slots. Sunday 2026-10-11: 11:52 EDT = 15:52 UTC dispatches although the morning run
  // succeeded; the :52 cron at 07:52 is not a second morning run; a run in progress leaves the slot to it; "" = none
  runs = [{ run_number: 12, event: "workflow_dispatch", status: "completed", conclusion: "success", created_at: "2026-10-11T11:37:40Z" }];
  const s3 = kv();
  let p0 = calls.filter((c) => c.startsWith("POST")).length;
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 11, 15, 52) }, { ...ENV, STATE: s3 }, {});
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, p0 + 1);
  assert.match(JSON.parse(s3.m.get("last_dispatch")).why, /a game-day refresh \(Sun 11:52\)/);
  p0 += 1;
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 11, 11, 52) }, { ...ENV, STATE: s3 }, {});   // 07:52: nothing
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 11, 15, 37) }, { ...ENV, STATE: s3 }, {});   // 11:37 re-check: a success today
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 13, 15, 52) }, { ...ENV, STATE: s3 }, {});   // Tuesday 11:52: no slot
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, p0);
  runs = [{ run_number: 13, event: "workflow_dispatch", status: "in_progress", conclusion: null, created_at: "2026-10-11T19:30:00Z" }];
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 11, 19, 37) }, { ...ENV, STATE: s3 }, {});   // Sun 15:37 with a run going
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, p0);
  runs = [];
  await worker.scheduled({ scheduledTime: Date.UTC(2026, 9, 11, 19, 37) }, { ...ENV, GAME_SLOTS_ET: "", STATE: s3 }, {});
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, p0);
  assert.equal(gameSlot(new Date(Date.UTC(2026, 9, 12, 22, 52))), "Mon 18:52");                     // EDT
  assert.equal(gameSlot(new Date(Date.UTC(2026, 11, 3, 23, 52))), "Thu 18:52");                     // EST: 18:52 = 23:52 UTC
  assert.equal(gameSlot(new Date(Date.UTC(2026, 11, 6, 16, 52))), "Sun 11:52");                     // EST Sunday
  assert.equal(gameSlot(new Date(Date.UTC(2026, 11, 6, 15, 52))), null);                            // 10:52 EST: not a slot
  assert.match(await page({ ...ENV }), /game-day refreshes \(always, unless a run is going\): Sun 11:52,Sun 15:37,Sun 18:52,Mon 18:52,Thu 18:52/);

  console.log = quiet.log;
  console.log("nightly-trigger: 8 checks passed");
} catch (e) {
  console.log = quiet.log;
  console.error = quiet.error;
  console.error(e);
  process.exit(1);
}

// ---- IS-4: "today" starts at 07:30 New York (EDT and EST), not 00:00 UTC; a run at 21:00 EDT is not the next morning's
assert.equal(morningSince(new Date(Date.UTC(2026, 9, 5, 13, 37))), "2026-10-05T11:30:00Z");   // 09:37 EDT
assert.equal(morningSince(new Date(Date.UTC(2026, 9, 6, 1, 0))), "2026-10-05T11:30:00Z");     // 21:00 EDT, still Oct 5
assert.equal(morningSince(new Date(Date.UTC(2026, 9, 6, 11, 0))), "2026-10-05T11:30:00Z");    // 07:00 EDT Oct 6: before 07:30
assert.equal(morningSince(new Date(Date.UTC(2026, 11, 1, 14, 37))), "2026-12-01T12:30:00Z");  // 09:37 EST
console.log("nightly-trigger: the New York morning checks passed");

