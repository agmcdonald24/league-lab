// Wave I-M (IM-5): DFS — before a file (this week's projections, the how-to), the salary file added (the slate, the
// Undervalued / Overpriced lists, the value table, lineups, the upload CSV), Remove file; with no league at all and with
// one in the URL (kept in every link). The DFS answers were recorded from the fixture API on the clone
// (web/fixtures/im5/*.json; the salary file is SYNTHETIC: api/tests/fixtures/dfs/make_synthetic.py). Phone at 375 and
// desktop at 1300, light and dark; screenshots into docs/handbacks/im5/ (SHOTS_IM5) and e2e/.out.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";

const IM5 = join(import.meta.dirname, "..", "..", "fixtures", "im5");
const SALARIES = join(import.meta.dirname, "..", "..", "..", "api", "tests", "fixtures", "dfs", "dk_classic_week5.csv");
const SHOTS = process.env.SHOTS_IM5 ?? join(import.meta.dirname, "..", ".out");
const read = (name: string) => readFileSync(join(IM5, name), "utf8");
const NEVER = /\b(lock|locks|guaranteed|free money|beat)\b/i;

async function dfsApi(context: BrowserContext): Promise<string[]> {
  const calls: string[] = [];
  await context.route(/\/api\/dfs\//, async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    calls.push(`${req.method()} ${url.pathname}${url.search}`);
    const send = (status: number, body: string) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    if (url.pathname === "/api/dfs/projections") return send(200, read(`projections_${url.searchParams.get("site") === "fd" ? "fd" : "dk"}.json`));
    if (url.pathname === "/api/dfs/slate") {
      const text = req.postData() ?? "";
      // ---- IM-5 fix: the server's Guard refuses a body over its upload limit with its own 413 words
      if (text.includes("GUARD_413")) return send(413, JSON.stringify({ error: "That is more than this server takes in one request.", code: "too_large" }));
      return /Name \+ ID/.test(text) && /Salary/.test(text) ? send(200, read("slate_dk_classic.json")) : send(400, read("slate_error.json"));
    }
    if (url.pathname === "/api/dfs/lineups") return send(200, read("lineups_dk_cash3.json"));
    return send(404, JSON.stringify({ error: "no such DFS route" }));
  });
  return calls;
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
  // nothing inside the screen wider than the screen (html's overflow clip would hide it from the page's width)
  const { mw, cw, right } = await page.evaluate(() => {
    const m = document.querySelector("[data-testid=dfs]") as HTMLElement;
    return { mw: m.scrollWidth, cw: m.clientWidth, right: m.getBoundingClientRect().right };
  });
  expect(mw).toBeLessThanOrEqual(cw + 1);
  expect(right).toBeLessThanOrEqual(iw);
}

const narrow = (name: string) => name === "phone";

for (const scheme of ["dark", "light"] as const) {
  test(`DFS with no league: projections, the file, lists, lineups, upload (${scheme})`, async ({ page, context }, info) => {
    await serveFixtures(context);
    const calls = await dfsApi(context);
    if (narrow(info.project.name)) await page.setViewportSize({ width: 375, height: 812 });
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/dfs");
    const main = page.getByTestId("dfs");
    await expect(main).toBeVisible();
    await expect(page.getByTestId("dfs-answer")).toContainText("This week's projections in DraftKings scoring");
    await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
    await expect(page.getByTestId("dfs-howto")).toContainText("Export to CSV");
    await expect(page.getByTestId("dfs-honest")).toContainText("Projections are estimates, not promises");
    await expect(page.getByTestId("dfs-footer")).toHaveText(
      "isuckatfantasy is not affiliated with DraftKings or FanDuel. Daily fantasy contests are not offered or legal everywhere and are for adults: check your state's rules.",
    );
    expect(calls.some((c) => c.startsWith("GET /api/dfs/projections?site=dk"))).toBe(true);
    expect(calls.every((c) => !c.includes("league="))).toBe(true);
    await noSideways(page);
    await page.screenshot({ path: join(SHOTS, `im5-before-${info.project.name}-${scheme}.png`) });

    // FanDuel's projections, then back
    await page.getByTestId("dfs-site-fd").click();
    await expect(page.getByTestId("dfs-howto")).toContainText("Download players list");
    await expect(page).toHaveURL(/site=fd/);
    await page.getByTestId("dfs-site-dk").click();

    // a wrong file: the words, nothing else
    await page.getByTestId("dfs-paste-open").click();
    await page.getByTestId("dfs-paste").fill("Player,Team,Cost\nJosh Allen,BUF,7900");
    await page.getByTestId("dfs-paste-add").click();
    await expect(page.getByTestId("dfs-file-error")).toContainText("does not look like a DraftKings or FanDuel salary file");
    // a 413 from either layer reads one plain sentence
    await page.getByTestId("dfs-paste").fill("GUARD_413");
    await page.getByTestId("dfs-paste-add").click();
    await expect(page.getByTestId("dfs-file-error")).toHaveText("That file is too big: a salary file is under 1 MB. Export the contest's player list again and add that file.");

    // the salary file
    await page.getByTestId("dfs-file").setInputFiles(SALARIES);
    await expect(page.getByTestId("dfs-slate-head")).toContainText("DraftKings classic · week 5 · 15 games");
    await expect(page.getByTestId("dfs-answer")).toContainText("597 of 599 players on your DraftKings file valued");
    await expect(page.getByTestId("dfs-undervalued").getByTestId("dfs-value-row")).toHaveCount(8);
    await expect(page.getByTestId("dfs-overpriced").getByTestId("dfs-value-row")).toHaveCount(8);
    await expect(page.getByTestId("dfs-undervalued").getByTestId("dfs-reason").first()).not.toBeEmpty();
    await expect(page.getByTestId("dfs-undervalued")).toContainText("Against this slate's salaries, not a promise.");
    await page.getByTestId("dfs-slate-head").scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `im5-lists-${info.project.name}-${scheme}.png`) });
    await page.getByTestId("dfs-unmatched").locator("summary").click();
    await expect(page.getByTestId("dfs-unmatched")).toContainText("Zzyzx Notaplayer");
    await expect(page.getByTestId("dfs-unmatched")).toContainText("we have that name as WR on LA");
    // position chips narrow the lists and the table
    await page.getByTestId("dfs-pos-TE").click();
    for (const row of await page.getByTestId("dfs-undervalued").getByTestId("dfs-value-row").allInnerTexts()) expect(row).toMatch(/\bTE\b/);
    await page.getByTestId("dfs-pos-ALL").click();
    await expect(page.getByTestId("dfs-value-table-row")).toHaveCount(60);
    await page.getByTestId("dfs-show-all").click();
    await expect(page.getByTestId("dfs-value-table-row")).toHaveCount(597);
    if (!narrow(info.project.name)) {
      // the salary column shows from 640 px (a phone reads it under the name)
      await page.getByTestId("sort-salary").click();
      const salaries = (await page.getByTestId("dfs-value-table-row").locator("td:nth-child(2)").allInnerTexts()).slice(0, 20).map((t) => Number(t.replace(/[$,]/g, "")));
      expect(salaries).toEqual([...salaries].sort((a, b) => a - b));
    }
    await noSideways(page);
    // lineups: one player always in, build three
    await page.getByTestId("dfs-pick").first().selectOption("in");
    await page.getByTestId("dfs-n").fill("3");
    await page.getByTestId("dfs-build-go").click();
    await expect(page.getByTestId("dfs-lineup")).toHaveCount(3);
    await expect(page.getByTestId("dfs-lineup-range").first()).toContainText("Low-end to high-end outcome");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("dfs-download").click()]);
    expect(download.suggestedFilename()).toBe("isuckatfantasy-dk_classic-3-lineups.csv");
    const csv = readFileSync(await download.path(), "utf8");
    expect(csv.split(/\r?\n/)[0]).toBe("QB,RB,RB,WR,WR,WR,TE,FLEX,DST");
    const lu = calls.filter((c) => c.startsWith("POST /api/dfs/lineups"));
    expect(lu.length).toBe(1);
    // the screen's own words (players' names aside: Drew Lock is a quarterback, not a promise)
    const names = (JSON.parse(read("slate_dk_classic.json")) as { players: { name: string; player_name: string | null }[] }).players.flatMap((p) => [p.name, p.player_name ?? ""]);
    let words = await main.innerText();
    for (const nm of names.filter(Boolean).sort((a, b) => b.length - a.length)) words = words.split(nm).join(" ");
    expect(words.match(NEVER)).toBeNull();
    await noSideways(page);
    await page.screenshot({ path: join(SHOTS, `im5-after-${info.project.name}-${scheme}.png`) });
    await page.getByTestId("dfs-lineups").scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `im5-lineups-${info.project.name}-${scheme}.png`) });

    // kept in this tab (sessionStorage) across a reload; Remove file goes back
    await page.reload();
    await expect(page.getByTestId("dfs-slate-head")).toBeVisible();
    await page.getByTestId("dfs-remove").click();
    await expect(page.getByTestId("dfs-filebox")).toBeVisible();
    expect(await page.evaluate(() => sessionStorage.getItem("ll.dfs.slate.dk"))).toBeNull();
  });
}

test("DFS with a league in the URL: the tab, the frame, links keep the league", async ({ page, context }, info) => {
  await serveFixtures(context);
  await dfsApi(context);
  if (narrow(info.project.name)) await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/dfs?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("dfs")).toBeVisible();
  await expect(page.getByTestId("tab-dfs")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("dfs-honest").locator("a")).toHaveAttribute("href", new RegExp(`/about\\?league=${SCRUBS}&team=2`));
  await page.getByTestId("dfs-file").setInputFiles(SALARIES);
  await expect(page.getByTestId("dfs-undervalued").getByTestId("dfs-value-row").first()).toBeVisible();
  const link = page.getByTestId("dfs-undervalued").locator("a.ll-link").first();
  await expect(link).toHaveAttribute("href", new RegExp(`^/player/00-[0-9]+\\?league=${SCRUBS}&team=2`));
  await expect(page).toHaveURL(new RegExp(`league=${SCRUBS}`));
  await noSideways(page);
});
