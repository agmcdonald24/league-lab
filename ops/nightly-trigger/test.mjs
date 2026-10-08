// The trigger offline (Wave I-H, IH-1): GitHub's API mocked, the KV binding `STATE` faked in memory.
//   node ops/nightly-trigger/test.mjs        (no dependencies; exits 1 on the first failed check)
// Checks: without STATE the page says the dispatch is not recorded and the morning run still dispatches; with STATE a
// 204 is recorded as ok and shown; a 401 is recorded with its status and time, shown as FAILED, and re-thrown (the
// Worker's own log marks the invocation failed); a re-check hour with a success today dispatches nothing and records
// nothing; no token at a trigger hour is recorded as such.
import assert from "node:assert/strict";
import worker, { morningSince } from "./src/index.js";

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

  console.log = quiet.log;
  console.log("nightly-trigger: 7 checks passed");
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

