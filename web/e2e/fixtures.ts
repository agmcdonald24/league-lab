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
    else if (p === "/api/ros") body = file(`ros_${q.get("league")}_${(q.get("position") ?? "ALL").toUpperCase()}.json`);
    else if (p === "/api/record") body = file(`record_${q.get("league")}.json`);
    if (body === null) return err(route, 404, `no fixture for ${p}${url.search}`);
    return json(route, 200, body);
  });
  return api;
}
