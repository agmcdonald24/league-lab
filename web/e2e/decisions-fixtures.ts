// G2's decision routes on fixtures (plan G4): /api/waivers, /api/team, /api/league, /api/trades/partners and
// POST /api/trades/evaluate answered from web/fixtures/{waivers,team,league,trades_partners,trades_evaluate}_*.json.
// Registered AFTER serveFixtures (Playwright runs the latest matching route first), everything else falls through to it.
// Headshots (nfl.com / Sleeper CDN) are not reachable from a test: they are answered 404 at once, so the silhouette shows.
// The fixtures are G2's saved answers (fixtures/save_decision_fixtures.py).
import type { BrowserContext, Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES } from "./fixtures";

export interface DecisionCalls {
  evaluate: { league: string; team: number; partner: number; give: string[]; get: string[]; window?: string }[];
  paths: string[];
}

function file(name: string): string | null {
  const p = join(FIXTURES, name);
  return existsSync(p) ? readFileSync(p, "utf8") : null;
}

const json = (route: Route, status: number, body: string) =>
  route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "private, max-age=120" }, body });

/** The fixture name of a trade: league_team_partner_give_get, ids sorted (make_decision_fixtures.py). */
export const evalKey = (league: string, team: number, partner: number, give: string[], get: string[], window?: string) =>
  // ---- IA-2: another window than the next four weeks is its own saved answer (save_ia2_fixtures.py)
  `trades_evaluate_${window && window !== "next4" ? `${window}_` : ""}${league}_${team}_${partner}_${[...give].sort().join("-")}_${[...get].sort().join("-")}.json`;

export async function serveDecisions(context: BrowserContext): Promise<DecisionCalls> {
  const calls: DecisionCalls = { evaluate: [], paths: [] };
  await context.route(/^https:\/\/(static\.www\.nfl\.com|sleepercdn\.com)\//, (route) => route.fulfill({ status: 404, body: "" }));
  await context.route(/\/api\/(waivers|team|league|trades\/partners|trades\/evaluate|trades\/lists)(\?|$)/, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    const q = url.searchParams;
    calls.paths.push(p + url.search);
    let body: string | null = null;
    if (p === "/api/waivers") body = file(`waivers_${q.get("league")}_${q.get("team")}_${(q.get("position") ?? "ALL").toUpperCase()}.json`);
    else if (p === "/api/team") body = file(`team_${q.get("league")}_${q.get("team")}.json`);
    else if (p === "/api/league") body = file(`league_${q.get("league")}${q.get("team") ? `_${q.get("team")}` : ""}.json`);
    else if (p === "/api/trades/partners") {
      const w = q.get("window"); // ---- IA-2: the window (next4, the default, is not sent)
      body = file(`trades_partners_${q.get("league")}_${q.get("team")}_${(q.get("want") ?? "ALL").toUpperCase()}${w && w !== "next4" ? `_${w}` : ""}.json`);
    } else if (p === "/api/trades/lists") body = file(`trades_lists_${q.get("league")}_${q.get("team")}.json`); // ---- IA-2
    else if (p === "/api/trades/evaluate" && req.method() === "POST") {
      const b = req.postDataJSON() as DecisionCalls["evaluate"][number];
      calls.evaluate.push(b);
      body = file(evalKey(b.league, b.team, b.partner, b.give, b.get, b.window));
      if (body === null) return json(route, 404, JSON.stringify({ error: "no fixture for this trade" }));
    }
    if (body === null) return route.fallback();
    return json(route, 200, body);
  });
  return calls;
}
