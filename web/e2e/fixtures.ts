// The API on fixtures (web/fixtures/*.json, see web/README.md § "Fixtures"): every /api call of a browser context is
// answered here (Playwright route interception), so the e2e checks and the first-content measurement run with no
// API, no database and no Sleeper. The beta password gate is simulated (password FIXTURE_PASSWORD) when `gate` is on.
import type { BrowserContext, Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const FIXTURES = join(import.meta.dirname, "..", "fixtures");
export const FIXTURE_PASSWORD = "fixture-beta";
export const DYNASTY = "1321941740235550720";
export const SCRUBS = "1389709692405551104";
export const TEST_LEAGUE = "9000000000000000001";

export interface FixtureApi {
  calls: string[]; // every /api path + query asked, in order
  signedIn: boolean;
}

// ---- II-3: the Stats Explorer's answers, recorded from the API (api/tests/test_ii3.py::test_record_e2e_answers) and keyed
// by the request's path + sorted query; a key that was not recorded answers 404 (the spec says which ones it uses)
let ii3: Record<string, { status: number; body: unknown }> | null = null;
function statsFrame(q: URLSearchParams): string | null {
  if (ii3 === null) {
    const f = join(FIXTURES, "ii3", "api_ii3.json");
    ii3 = existsSync(f) ? (JSON.parse(readFileSync(f, "utf8")) as typeof ii3) : {};
  }
  const sorted = [...q.entries()].sort(([a], [b]) => a.localeCompare(b));
  const hit = ii3![`/api/players?${new URLSearchParams(sorted).toString()}`];
  return hit ? JSON.stringify(hit.body) : null;
}
// ---- end II-3

function file(name: string): string | null {
  const p = join(FIXTURES, name);
  return existsSync(p) ? readFileSync(p, "utf8") : null;
}

const json = (route: Route, status: number, body: string) =>
  route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "private, max-age=120" }, body });

const err = (route: Route, status: number, error: string) => json(route, status, JSON.stringify({ error }));

/** Answer /api/* from the fixture files. `gate`: start signed out (the password screen first). */
export async function serveFixtures(context: BrowserContext, opts: { gate?: boolean } = {}): Promise<FixtureApi> {
  const api: FixtureApi = { calls: [], signedIn: !opts.gate };
  // headshots (static.www.nfl.com): never fetched by a test — the app falls back to the silhouette
  await context.route(/^https:\/\/static\.www\.nfl\.com\//, (route) => route.abort());
  await context.route(/\/api\//, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    const q = url.searchParams;
    api.calls.push(p + url.search);
    if (p === "/api/session") return json(route, 200, JSON.stringify({ gate: !!opts.gate, signed_in: api.signedIn }));
    if (p === "/api/login" && req.method() === "POST") {
      const body = req.postDataJSON() as { password?: string };
      if (body?.password !== FIXTURE_PASSWORD) return json(route, 401, JSON.stringify({ detail: "That is not it." }));
      api.signedIn = true;
      return json(route, 200, JSON.stringify({ ok: true, token: "fixture" }));
    }
    if (!api.signedIn) return json(route, 401, JSON.stringify({ detail: "Private beta. Enter the password from your invite." }));
    let m: RegExpMatchArray | null;
    let body: string | null = null;
    if (p === "/api/leagues") {
      const u = q.get("username");
      if (u === null) body = file("leagues.json");
      else if (u.trim().toLowerCase() === "sleeper_down") return err(route, 502, "Sleeper did not answer");
      else {
        body = file(`leagues_user_${u.trim().toLowerCase()}.json`);
        if (!body) return err(route, 404, "no such Sleeper user");
      }
    } else if ((m = p.match(/^\/api\/leagues\/(\d+)\/rosters$/))) body = file(`rosters_${m[1]}.json`);
    else if (p === "/api/my-week") body = file(`my-week_${q.get("league")}_${q.get("team")}.json`);
    else if ((m = p.match(/^\/api\/player\/([^/]+)$/))) body = file(`player/${q.get("league")}_${decodeURIComponent(m[1])}.json`);
    else if (p === "/api/search") body = file(`search_${q.get("league")}.json`) ?? "[]";
    else if (p === "/api/status") body = file("status.json");
    // ---- IB-3: "Value to my lineup" (view=lineup&team=&who=): its own files; a `who` without one filters the saved list
    else if (p === "/api/ros" && q.get("view") === "lineup") {
      const base = `ros-lineup_${q.get("league")}_${q.get("team")}_${(q.get("position") ?? "ALL").toUpperCase()}`;
      const who = q.get("who");
      body = file(`${base}${who && who !== "all" ? `_${who}` : ""}.json`);
      if (body === null && who && who !== "all" && (body = file(`${base}.json`)) !== null) {
        const d = JSON.parse(body) as { players: { lineup_kind?: string }[] };
        body = JSON.stringify({ ...d, who, players: d.players.filter((r) => r.lineup_kind === who) });
      }
    } // ---- end IB-3
    // ---- II-4: My roster outlook / Potential upgrades from IB-3's saved lineup lists (outlook = yours, upgrades = the rest;
    // the same numbers — the API's split moves none); a `_mine` file when there is one
    else if (p === "/api/ros" && (q.get("view") === "outlook" || q.get("view") === "upgrades")) {
      const base = `ros-lineup_${q.get("league")}_${q.get("team")}_${(q.get("position") ?? "ALL").toUpperCase()}`;
      const outlook = q.get("view") === "outlook";
      const all = file(`${base}.json`);
      const src = outlook ? (file(`${base}_mine.json`) ?? all) : all;
      if (src !== null) {
        const d = JSON.parse(src) as { players: { lineup_kind?: string }[] };
        const who = q.get("who");
        const keep = (k?: string) => (outlook ? k === "mine" : k !== "mine" && (!who || who === "all" || k === who));
        body = JSON.stringify({ ...d, view: q.get("view"), players: d.players.filter((r) => keep(r.lineup_kind)) });
      }
    } // ---- end II-4
    else if (p === "/api/ros") body = file(`ros_${q.get("league")}_${(q.get("position") ?? "ALL").toUpperCase()}.json`);
    else if (p === "/api/record") body = file(`record_${q.get("league")}.json`);
    else if (p === "/api/about") body = file(`about_${q.get("league")}.json`); // H1 (Wave H)
    // ---- G3 research routes (Wave G): one file per league (the screens filter and sort on the phone)
    else if (p === "/api/trends") body = file(`trends_${q.get("league")}.json`);
    else if (p === "/api/matchups/defense") body = file(`matchups_defense_${q.get("league")}_${q.get("team")}.json`) ?? file(`matchups_defense_${q.get("league")}.json`);
    else if (p === "/api/matchups/cb") body = file(`matchups_cb_${q.get("league")}_${q.get("team")}.json`);
    else if (p === "/api/players" && q.get("window")) body = statsFrame(q); // ---- II-3: the Stats frame (recorded answers)
    else if (p === "/api/players") body = file(`players_${q.get("league")}.json`);
    else if (p === "/api/receivers") body = file(`receivers_${q.get("league")}.json`);
    else if (p === "/api/compare") {
      const sides = JSON.parse(file(`compare_${q.get("league")}.json`) ?? "{}") as Record<string, unknown>;
      const a = sides[q.get("a") ?? ""];
      const b = sides[q.get("b") ?? ""];
      if (!a || !b) return err(route, 404, "No numbers for that player in this league yet.");
      body = JSON.stringify({ ...(sides._meta as object), a, b }); // saved sides of real answers + the answer's league block
    } else if ((m = p.match(/^\/api\/player\/([^/]+)\/games$/))) {
      const all = JSON.parse(file(`games_${q.get("league")}.json`) ?? "{}") as Record<string, { season: number }[]>;
      const rows = all[decodeURIComponent(m[1])];
      if (!rows) return err(route, 404, "No games for that player.");
      const season = Number(q.get("season"));
      body = JSON.stringify({ games: season ? rows.filter((r) => r.season === season) : rows });
    }
    if (body === null) return err(route, 404, `no fixture for ${p}${url.search}`);
    return json(route, 200, body);
  });
  return api;
}
