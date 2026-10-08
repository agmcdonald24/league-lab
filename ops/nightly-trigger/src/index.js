// The nightly's trigger (2026-10-04): a Cloudflare Worker on a Cron Trigger that starts the GitHub Actions
// workflow `nightly.yml` at 07:37 America/New_York every day, and re-checks at 09:37 and 11:37 — dispatching again
// only when no run has succeeded or started today (UTC, the same day the workflow's `gate` job uses).
//
// Why: GitHub's own `schedule` is best-effort. Every scheduled nightly from 2026-09-30 to 2026-10-03 started 3.5-6
// hours late (12:59, 13:29, 12:48, 11:13 ET) and the 09:07 backup never ran as its own run; on 2026-10-04 nothing had
// started by 09:45 ET. A `workflow_dispatch` run starts within seconds and the gate never skips it. GitHub's schedule
// stays in the workflow as the last resort.
//
// Configuration (wrangler.jsonc `vars`, or the dashboard's Variables): GITHUB_REPO (owner/name), WORKFLOW_FILE,
// GIT_REF, FIRE_HOUR_ET (the hour that always dispatches), CHECK_HOURS_ET (the hours that dispatch only when today
// has no success / nothing running). Secret: GITHUB_TOKEN — a fine-grained personal access token for that one
// repository with "Actions: Read and write" (never in this file, never in git; docs/HOSTING.md § "The trigger").
//
// HTTP: GET / answers a status line (what it does, the last dispatch, today's runs); nothing dispatches over HTTP.
//
// ---- IH-1 (Wave I-H): the last dispatch's result on the status page. A Worker keeps nothing between invocations
// without a binding, so the result is written to an OPTIONAL Workers KV namespace bound as `STATE` (free plan: 100,000
// reads and 1,000 writes a day; this writes at most 3 a day): key `last_dispatch` = {at, hour_et, why, ok, status,
// error}. Without the binding everything works as before and the page says "last dispatch: not recorded (no STATE
// binding)". To add it: Cloudflare → Workers & Pages → KV → Create namespace `isuckatfantasy-nightly-state`; the
// Worker → Settings → Bindings → Add → KV namespace, variable name `STATE`. docs/HOSTING.md § 5 "When the nightly is
// late or fails".

const API = "https://api.github.com";

function etHour(d) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", hour12: false }).formatToParts(d);
  return Number(parts.find((p) => p.type === "hour").value) % 24;
}

function etStamp(d) {
  return new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short" }).format(d) + " ET";
}

function headers(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "isuckatfantasy-nightly-trigger",
  };
}

// ---- IS-4 (Wave I-S): "today" is New York's morning, not UTC's day: the runs created since 07:30 America/New_York
// (before 07:30, since yesterday's). Counting from 00:00 UTC made a run that succeeded after 20:00 EDT (a manual run, a
// merge's) the next morning's, so a failed 07:37 run was never re-dispatched.
export function morningSince(now) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric",
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(now).map((x) => [x.type, x.value]));
  const local = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
  const offset = Math.round((local - now.getTime()) / 60000) * 60000;    // New York minus UTC (-4 h in EDT)
  let since = Date.UTC(+p.year, +p.month - 1, +p.day, 7, 30) - offset;
  if (since > now.getTime()) since -= 86400000;
  return new Date(since).toISOString().replace(/\.\d{3}Z$/, "Z");
}

async function todaysRuns(env, now) {
  const url = `${API}/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/runs?created=>=${morningSince(now)}&per_page=20`;  // ---- IS-4
  const r = await fetch(url, { headers: headers(env) });
  if (!r.ok) throw new Error(`runs: HTTP ${r.status}`);
  const j = await r.json();
  return (j.workflow_runs || []).map((x) => ({
    number: x.run_number, event: x.event, status: x.status, conclusion: x.conclusion, created: x.created_at,
  }));
}

async function dispatch(env) {
  const url = `${API}/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...headers(env), "Content-Type": "application/json" },
    body: JSON.stringify({ ref: env.GIT_REF || "main" }),
  });
  if (r.status !== 204) {
    const e = new Error(`dispatch: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    e.status = r.status;
    throw e;
  }
}

// ---- IH-1: the last dispatch, kept in the optional KV binding `STATE` (see the header); never fails the run
const LAST_KEY = "last_dispatch";

async function remember(env, rec) {
  if (!env.STATE || typeof env.STATE.put !== "function") return false;
  try {
    await env.STATE.put(LAST_KEY, JSON.stringify(rec));
    return true;
  } catch (e) {
    console.error(`could not record the dispatch in STATE: ${e.message}`);
    return false;
  }
}

async function lastDispatch(env) {
  if (!env.STATE || typeof env.STATE.get !== "function") return { line: "last dispatch: not recorded (no STATE binding: a KV namespace, free — docs/HOSTING.md § 5)" };
  try {
    const raw = await env.STATE.get(LAST_KEY);
    if (!raw) return { line: "last dispatch: none recorded yet" };
    const r = JSON.parse(raw);
    const when = etStamp(new Date(r.at));
    return {
      record: r,
      line: r.ok
        ? `last dispatch: ok (HTTP 204) at ${when} — ${r.why}`
        : `last dispatch: FAILED at ${when} — ${r.why}: ${r.status ? `HTTP ${r.status}` : "no answer"} ${r.error || ""}`.trim(),
    };
  } catch (e) {
    return { line: `last dispatch: could not read STATE (${e.message})` };
  }
}

/** Dispatch and record the result (success, or the HTTP error and when); a failure is re-thrown so the Worker's
 * own log marks the invocation as failed too. */
async function dispatchAndRecord(env, now, why) {
  const rec = { at: now.toISOString(), hour_et: etHour(now), why, ok: false, status: null, error: null };
  try {
    await dispatch(env);
    rec.ok = true;
    rec.status = 204;
  } catch (e) {
    rec.status = e.status ?? null;
    rec.error = String(e.message || e).slice(0, 300);
    await remember(env, rec);
    throw e;
  }
  await remember(env, rec);
  return rec;
}
// ---- end IH-1

function hours(s, fallback) {
  const v = String(s || "").split(",").map((x) => Number(x.trim())).filter((x) => Number.isInteger(x));
  return v.length ? v : fallback;
}

export default {
  async scheduled(event, env, ctx) {
    const now = new Date(event.scheduledTime);
    const h = etHour(now);
    const fire = hours(env.FIRE_HOUR_ET, [7]);
    const check = hours(env.CHECK_HOURS_ET, [9, 11]);
    if (!env.GITHUB_TOKEN) {
      console.error("no GITHUB_TOKEN secret: nothing dispatched");
      if (fire.includes(h) || check.includes(h)) await remember(env, { at: now.toISOString(), hour_et: h, why: "a trigger hour", ok: false, status: null, error: "no GITHUB_TOKEN secret" }); // ---- IH-1
      return;
    }
    if (fire.includes(h)) {
      await dispatchAndRecord(env, now, "the morning run"); // ---- IH-1: recorded in STATE when bound
      console.log(`${etStamp(now)}: dispatched ${env.WORKFLOW_FILE} (the morning run)`);
      return;
    }
    if (check.includes(h)) {
      const runs = await todaysRuns(env, now);
      const fine = runs.some((r) => r.conclusion === "success" || r.status === "in_progress" || r.status === "queued");
      if (fine) { console.log(`${etStamp(now)}: a nightly succeeded or is running today; nothing to do`); return; }
      await dispatchAndRecord(env, now, "a re-check: nothing succeeded or running today"); // ---- IH-1
      console.log(`${etStamp(now)}: no successful nightly today; dispatched ${env.WORKFLOW_FILE}`);
      return;
    }
    console.log(`${etStamp(now)}: not a trigger hour`);
  },

  async fetch(request, env) {
    const now = new Date();
    const lines = [
      `isuckatfantasy nightly trigger: dispatches ${env.GITHUB_REPO} / ${env.WORKFLOW_FILE} at ` +
        `${hours(env.FIRE_HOUR_ET, [7]).map((x) => `${x}:37`).join(", ")} America/New_York; re-checks at ` +
        `${hours(env.CHECK_HOURS_ET, [9, 11]).map((x) => `${x}:37`).join(", ")} (dispatches only when nothing succeeded or is running since 07:30 New York).`,
      `now: ${etStamp(now)}; token: ${env.GITHUB_TOKEN ? "set" : "MISSING"}`,
      (await lastDispatch(env)).line, // ---- IH-1
    ];
    if (env.GITHUB_TOKEN) {
      try {
        const runs = await todaysRuns(env, now);
        lines.push(runs.length ? `runs since ${morningSince(now)}:` : `runs since ${morningSince(now)}: none yet`);
        for (const r of runs) lines.push(`  #${r.number} ${r.event} ${r.status} ${r.conclusion || ""} ${r.created}`);
      } catch (e) { lines.push(`could not list today's runs: ${e.message}`); }
    }
    return new Response(lines.join("\n") + "\n", { headers: { "content-type": "text/plain; charset=utf-8" } });
  },
};
