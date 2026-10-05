import { chromium } from "playwright";
const Q = "league=1389709692405551104&team=2";
const M = "league=mfl%3A70587&team=1";
const base = "http://localhost:8744";
const out = process.argv[2];
const pages = [
  ["week", `/?${Q}`], ["trades", `/trades?${Q}`], ["players-qb", `/players?${Q}&position=QB`], ["players", `/players?${Q}`],
  ["waivers", `/waivers?${Q}&view=all&position=WR`], ["league", `/league?${Q}`], ["watchlist", `/watchlist?${Q}`], ["account", `/account?${Q}`],
  ["mfl-week", `/?${M}`], ["mfl-league", `/league?${M}`], ["mfl-waivers", `/waivers?${M}&view=all&position=WR`], ["mfl-matchups", `/matchups?${M}`],
  ["leagues", `/leagues`],
];
const browser = await chromium.launch();
for (const [name, w, h] of [["desktop", 1300, 900], ["phone", 375, 812]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: name === "phone", hasTouch: name === "phone" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  for (const [id, path] of pages) {
    try {
      await page.goto(base + path, { waitUntil: "networkidle", timeout: 120000 });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${out}/${name}-${id}.png`, fullPage: true });
      console.log(name, id, "ok", await page.title());
    } catch (e) { console.log(name, id, "FAIL", String(e).slice(0, 200)); }
  }
  for (const [id, path] of [["drawer", `/waivers?${Q}&view=all&position=WR`], ["mfl-drawer", `/?${M}`]]) {
    try {
      await page.goto(base + path, { waitUntil: "networkidle", timeout: 120000 });
      const link = page.locator('a[href*="/player/"]').first();
      await link.scrollIntoViewIfNeeded();
      if (name === "phone") await link.tap(); else await link.click();
      await page.waitForTimeout(3000);
      await page.screenshot({ path: `${out}/${name}-${id}.png`, fullPage: false });
      const txt = await page.locator('body').innerText();
      const i = txt.indexOf("Role");
      console.log(name, id, "ok", page.url(), "| role:", txt.slice(Math.max(0, i - 10), i + 260).replace(/\s+/g, " "));
      // the whole drawer, scrolled
      await page.screenshot({ path: `${out}/${name}-${id}-full.png`, fullPage: true });
    } catch (e) { console.log(name, id, "FAIL", String(e).slice(0, 200)); }
  }
  console.log(name, "console errors:", errors.length, errors.slice(0, 5));
  await ctx.close();
}
await browser.close();
