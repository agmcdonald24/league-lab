// The trigger offline (Wave I-H, IH-1): GitHub's API mocked, the KV binding `STATE` faked in memory.
//   node ops/nightly-trigger/test.mjs        (no dependencies; exits 1 on the first failed check)
// Checks: without STATE the page says the dispatch is not recorded and the morning run still dispatches; with STATE a
// 204 is recorded as ok and shown; a 401 is recorded with its status and time, shown as FAILED, and re-thrown (the
// Worker's own log marks the invocation failed); a re-check hour with a success today dispatches nothing and records
// nothing; no token at a trigger hour is recorded as such.
import assert from "node:assert/strict";
import worker, { _resetProbe, dueLines, dueToday, gameSlot, morningSince, probeWords, statusText } from "./src/index.js";

const ENV = { GITHUB_REPO: "owner/league-lab", WORKFLOW_FILE: "nightly.yml", GIT_REF: "main", FIRE_HOUR_ET: "7", CHECK_HOURS_ET: "9,11", GITHUB_TOKEN: "t" };
// 07:37 EDT = 11:37 UTC; 09:37 EDT = 13:37 UTC (2026-10-05, a Monday)
const MORNING = Date.UTC(2026, 9, 5, 11, 37);
const RECHECK = Date.UTC(2026, 9, 5, 13, 37);

function kv() {
  const m = new Map();
  return { m, get: async (k) => (m.has(k) ? m.get(k) : null), put: async (k, v) => void m.set(k, v) };
}

let dispatchStatus = 204;
let probeStatus = 422;                                     // PO (2026-10-12): the status page's permission probe
let probeBody = '{"message":"No ref found for: refs/heads/trigger-permission-probe--no-such-branch"}';
let runs = [];
const calls = [];
globalThis.fetch = async (url, init = {}) => {
  const probe = String(url).endsWith("/dispatches") && /no-such-branch/.test(String(init.body || ""));
  calls.push(`${probe ? "PROBE" : init.method || "GET"} ${url}`);
  if (probe) return new Response(probeBody, { status: probeStatus });
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

  // 9. PO (2026-10-12): "token: set" is not "can start a run". The page asks GitHub for a dispatch on a branch that does
  // not exist: 422 = the token may dispatch (nothing starts); 403 = it may read but not write — said in words, with the
  // permission's name; never a real dispatch; the answer is kept five minutes.
  runs = [];
  _resetProbe();
  probeStatus = 422;
  let posts9 = calls.filter((c) => c.startsWith("POST")).length;
  let text = await page({ ...ENV });
  assert.match(text, /token: set\ncan start a run: yes\n/);
  const probes = calls.filter((c) => c.startsWith("PROBE")).length;
  await page({ ...ENV });                                                                // within five minutes: not asked again
  assert.equal(calls.filter((c) => c.startsWith("PROBE")).length, probes);
  _resetProbe();
  probeStatus = 403;
  probeBody = '{"message":"Resource not accessible by personal access token"}';
  text = await page({ ...ENV });
  assert.match(text, /can start a run: NO — HTTP 403: the token may read Actions but not write: set its repository permission Actions to "Read and write"/);
  assert.match(text, /\[GitHub: \{"message":"Resource not accessible by personal access token"/);
  assert.equal(calls.filter((c) => c.startsWith("POST")).length, posts9);                 // the probe never dispatches
  assert.doesNotMatch(await page({ ...ENV, GITHUB_TOKEN: "" }), /can start a run/);       // no token: the MISSING line says it
  assert.equal(probeWords(401, "").ok, false);
  assert.match(probeWords(404, "").line, /does not reach this repository/);
  _resetProbe();
  probeStatus = 422;

  // 10. PO (2026-10-12): what was due today and whether it started — from the run list, no binding. Monday 12 October
  // 2026 as it happened: nothing at 07:37, a run by hand at 08:39.
  const NOW12 = new Date(Date.UTC(2026, 9, 12, 13, 51));                                 // 09:51 EDT
  const hand = [{ number: 41, event: "workflow_dispatch", status: "completed", conclusion: "success", created: "2026-10-12T12:39:02Z", updated: "2026-10-12T13:14:14Z" }];
  assert.deepEqual(dueToday(NOW12, ENV).map((d) => d.label), ["7:37 the morning run"]);
  assert.deepEqual(dueLines(NOW12, ENV, hand), ["  7:37 the morning run: NO RUN STARTED"]);
  assert.deepEqual(dueLines(NOW12, ENV, [{ number: 42, event: "workflow_dispatch", status: "completed", conclusion: "success", created: "2026-10-12T11:37:21Z", updated: "2026-10-12T11:55:00Z" }]),
    ["  7:37 the morning run: started (#42)"]);
  const EVENING = new Date(Date.UTC(2026, 9, 12, 23, 0));                                // Monday 19:00 EDT: the 18:52 slot is past
  assert.deepEqual(dueToday(EVENING, ENV).map((d) => d.label), ["7:37 the morning run", "18:52 a game-day refresh"]);
  assert.equal(dueLines(EVENING, ENV, hand)[1], "  18:52 a game-day refresh: NO RUN STARTED");
  assert.equal(dueLines(EVENING, ENV, [...hand, { number: 43, event: "workflow_dispatch", status: "in_progress", conclusion: null, created: "2026-10-12T22:52:20Z", updated: "2026-10-12T22:53:00Z" }])[1],
    "  18:52 a game-day refresh: started (#43)");
  assert.equal(dueLines(EVENING, ENV, [...hand, { number: 43, event: "workflow_dispatch", status: "in_progress", conclusion: null, created: "2026-10-12T22:40:00Z", updated: "2026-10-12T22:41:00Z" }])[1],
    "  18:52 a game-day refresh: no new run (#43 was still going; a slot is left to it)");
  assert.deepEqual(dueToday(new Date(Date.UTC(2026, 9, 12, 11, 38)), ENV), []);          // 07:38: inside the three minutes' grace
  assert.deepEqual(dueToday(new Date(Date.UTC(2026, 9, 13, 11, 0)), ENV).map((d) => d.label), ["7:37 the morning run", "18:52 a game-day refresh"]);  // Tue 07:00: still Monday's day
  assert.deepEqual(dueToday(EVENING, { ...ENV, GAME_SLOTS_ET: "" }).map((d) => d.label), ["7:37 the morning run"]);
  runs = [{ run_number: 41, event: "workflow_dispatch", status: "completed", conclusion: "success", created_at: "2026-10-12T12:39:02Z", updated_at: "2026-10-12T13:14:14Z" }];
  assert.match(await statusText({ ...ENV }, NOW12), /token: set\ncan start a run: yes\n[^]*#41 workflow_dispatch completed success[^]*due today:\n {2}7:37 the morning run: NO RUN STARTED\n$/);
  runs = [];

  console.log = quiet.log;
  console.log("nightly-trigger: 10 checks passed");
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

