import { chromium } from "@playwright/test";
const OUT = "/home/claude/waveIM/shots/";
const b = await chromium.launch();
const errs = [];
const pages = [
  ["door", "/"],
  ["stats-ref", "/players?league=ref:half"],
  ["stats-ref-full", "/players?league=ref:half&view=full"],
  ["stats-house", "/players?league=1389709692405551104&team=2&view=full"],
  ["trades-ref", "/trades?league=ref:half"],
  ["dfs", "/dfs"],
  ["account", "/account"],
  ["myweek-house", "/?league=1389709692405551104&team=2"],
  ["player-ref", "/players?league=ref:half&view=key"],
];
for (const [w, h] of [[375, 812], [1300, 900]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, serviceWorkers: "block" });
  const p = await ctx.newPage();
  p.on("console", m => { if (m.type() === "error" && !/ERR_TUNNEL|Failed to load resource/.test(m.text())) errs.push(w + " " + m.text().slice(0, 200)); });
  p.on("pageerror", e => errs.push(w + " pageerror " + String(e).slice(0, 240)));
  for (const [name, url] of pages) {
    await p.goto("http://localhost:8744" + url, { waitUntil: "networkidle", timeout: 90000 }).catch(e => errs.push(w + " goto " + name + " " + String(e).slice(0, 120)));
    await p.waitForTimeout(1200);
    const sw = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    await p.screenshot({ path: OUT + name + "_" + w + ".png" });
    const txt = (await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 260);
    console.log(`[${w}] ${name} url=${p.url().replace("http://localhost:8744", "")} sideways=${sw} :: ${txt}`);
    if (name === "dfs") {
      const input = p.locator('input[type="file"]').first();
      if (await input.count()) {
        await input.setInputFiles("/home/claude/league-lab/api/tests/fixtures/dfs/dk_classic_week5.csv");
        await p.waitForTimeout(6000);
        await p.screenshot({ path: OUT + "dfs-file_" + w + ".png" });
        await p.screenshot({ path: OUT + "dfs-file-full_" + w + ".png", fullPage: true });
        console.log(`[${w}] dfs-file :: ` + (await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 700));
      } else console.log(`[${w}] dfs: NO FILE INPUT`);
    }
  }
  await ctx.close();
}
console.log("errors:", JSON.stringify(errs, null, 1));
await b.close();
