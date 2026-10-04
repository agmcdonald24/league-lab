// Wave I-G (M4): the record says how its weeks were priced — one sentence under the record's answer on About
// (GET /api/record `pricing.sentence`), none when every week is flat and so is now. The dynasty's recorded answer with
// a `pricing` block added here (weeks 1–4 flat, the newest build EV); phone 375 and desktop 1300.
import { expect, test, type BrowserContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const SENTENCE = "Weeks 1–4 were priced flat; from week 5 the bonuses are priced at their odds.";

async function record(context: BrowserContext, league: string, sentence: string | null) {
  const body = JSON.parse(readFileSync(join(FIXTURES, `record_${league}.json`), "utf8"));
  body.pricing = { now: sentence ? "ev" : "flat", by_week: { "1": "flat", "2": "flat", "3": "flat", "4": "flat" }, sentence };
  await context.route(/\/api\/record\?/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }),
  );
}

test("the dynasty's record says weeks 1–4 were flat and week 5 on is at the odds", async ({ context, page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await serveFixtures(context);
  await record(context, DYNASTY, SENTENCE);
  await page.goto(`/about?league=${DYNASTY}`);
  await expect(page.getByTestId("record")).toBeVisible();
  await expect(page.getByTestId("record-pricing")).toHaveText(SENTENCE);
  const box = await page.getByTestId("record-pricing").boundingBox();
  const width = page.viewportSize()?.width ?? 0;
  expect(box && box.x >= 0 && box.x + box.width <= width).toBeTruthy(); // no horizontal overflow
  await page.getByTestId("record-pricing").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `m4-record-${info.project.name}.png`) });
});

test("a league without a bonus (Scrubs) says nothing about pricing", async ({ context, page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await serveFixtures(context);
  await record(context, SCRUBS, null);
  await page.goto(`/about?league=${SCRUBS}`);
  await expect(page.getByTestId("record")).toBeVisible();
  await expect(page.getByTestId("record-answer").or(page.getByTestId("record-empty"))).toBeVisible();
  await expect(page.getByTestId("record-pricing")).toHaveCount(0);
});
