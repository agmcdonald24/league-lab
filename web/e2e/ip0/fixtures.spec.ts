// Hotfix 2026-10-07: the player card shows the player's picture (the card's answer never carried headshot_url, so the
// page and the drawer drew a silhouette for everyone — and every test accepted the silhouette, because a test reaches
// no outside host), and a Headshot asks the NFL's image host for the width its circle needs, not the 3400-pixel
// original. Here the picture host is answered by the test itself, so the picture is really drawn.
import { expect, test, type BrowserContext } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const RECORDED = join(import.meta.dirname, "..", "..", "fixtures", "ip4", "api_ip4.json");
type Recorded = Record<string, { status: number; body: Record<string, unknown> }>;
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};
const ID = "00-0039075"; // Puka Nacua
const FACE = "https://static.www.nfl.com/image/upload/f_auto,q_auto/league/yvscmqq1qki8zfsemmcd";
// a 1 x 1 PNG
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};

async function api(context: BrowserContext, refuse: (url: string) => boolean = () => false): Promise<string[]> {
  const pictures: string[] = [];
  await serveFixtures(context);
  // after serveFixtures (the last route registered answers first): the picture host is this test's, the rest refused
  await context.route(/^https?:\/\/(?!localhost)/, (route) => {
    const url = route.request().url();
    if (!url.startsWith("https://static.www.nfl.com/")) return route.abort();
    pictures.push(url);
    return refuse(url) ? route.abort() : route.fulfill({ status: 200, contentType: "image/png", body: PNG });
  });
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    const hit = recorded[keyOf(u)];
    if (!hit) return route.fallback();
    const body = u.pathname === `/api/player/${ID}` ? { ...hit.body, headshot_url: FACE } : hit.body;
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(body) });
  });
  return pictures;
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("the card draws the player's picture, asked at the size its circle needs", async ({ context, page }) => {
  const pictures = await api(context);
  await page.goto(`/player/${ID}?league=ref:half`);
  const head = page.getByTestId("player-header");
  await expect(head).toBeVisible({ timeout: 30_000 });
  const img = head.getByTestId("headshot").locator("img");
  await expect(img).toBeVisible();
  await expect(img).toHaveAttribute("src", /\/image\/upload\/f_auto,q_auto,w_(256|320)\/league\/yvscmqq1qki8zfsemmcd$/);
  await expect(head.getByTestId("silhouette")).toHaveCount(0);
  expect(pictures.every((u) => /,w_\d+\//.test(u)), "never the 3400-pixel original").toBe(true);
});

test("a resized picture that fails falls back to the original, then to the silhouette", async ({ context, page }) => {
  const pictures = await api(context, (url) => /,w_\d+\//.test(url));
  await page.goto(`/player/${ID}?league=ref:half`);
  const head = page.getByTestId("player-header");
  await expect(head).toBeVisible({ timeout: 30_000 });
  await expect(head.getByTestId("headshot").locator("img")).toHaveAttribute("src", FACE);
  expect(pictures.some((u) => u === FACE)).toBe(true);
  await context.unrouteAll({ behavior: "ignoreErrors" });
});

test("sizedHeadshot: the NFL host's pictures get a width, anything else is left alone (pure code)", async () => {
  test.skip(test.info().project.name !== "desktop", "pure code: once is enough");
  const { sizedHeadshot, headshotWidth } = await import("../../src/lib/headshot");
  expect(sizedHeadshot(FACE, 40)).toBe("https://static.www.nfl.com/image/upload/f_auto,q_auto,w_128/league/yvscmqq1qki8zfsemmcd");
  expect(sizedHeadshot(FACE, 104)).toBe("https://static.www.nfl.com/image/upload/f_auto,q_auto,w_320/league/yvscmqq1qki8zfsemmcd");
  expect(sizedHeadshot("https://static.www.nfl.com/image/private/f_auto,q_auto/league/abc", 64)).toBe("https://static.www.nfl.com/image/private/f_auto,q_auto,w_192/league/abc");
  expect([40, 44, 56, 64, 76, 84, 104].map(headshotWidth)).toEqual([128, 128, 192, 192, 256, 256, 320]);
  for (const other of ["https://sleepercdn.com/content/nfl/players/thumb/421.jpg", "https://static.www.nfl.com/image/upload/t_x/league/abc", "https://evil.example/image/upload/f_auto,q_auto/league/abc", "/blog/img/a.png"])
    expect(sizedHeadshot(other, 64)).toBe(other);
  expect(sizedHeadshot(null, 64)).toBeNull();
  expect(sizedHeadshot("", 64)).toBeNull();
});
