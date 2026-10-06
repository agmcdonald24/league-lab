// ---- IO-3 (Wave I-O): "New post from…" — three starters that fill a DRAFT from the live routes on Half PPR, as plain
// markdown with the numbers written in (a published post must not change under its readers) and an "as of" line.
// Each leaves obvious places for the writer's own words ("Your take: …") and never publishes by itself.
//   matchups     the matchup board's favorable and difficult receivers (WR, TE), with the defense's and the corner's words
//   projections  this week's top projections and their ranges, by position (the board's projection, 10th–90th)
//   roles        players whose role is changing (the DFS board's role trend: his last two games against the ones before)
import { boardPath, get, type BoardRow, type MatchupBoard } from "../../lib/api";
import { REF_DEFAULT } from "../../lib/refleague";
import { projectionsPath, type Projections } from "../dfs/dfs";
import type { Draft } from "./editor.svelte";

export type StarterKind = "matchups" | "projections" | "roles";
export const STARTERS: { kind: StarterKind; label: string; hint: string }[] = [
  { kind: "matchups", label: "Matchups to target and avoid", hint: "The board's favorable and difficult receivers" },
  { kind: "projections", label: "This week's top projections and their ranges", hint: "By position, Half PPR" },
  { kind: "roles", label: "Players whose role is changing", hint: "Targets, carries and snaps lately" },
];

const L = REF_DEFAULT; // Half PPR
const TAKE = "*Your take: …*";

function fmt(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toFixed(1) : "–";
}
/** Plain inline text for a post: the characters mdDoc reads as markup (it has no backslash escapes) are swapped for
 * look-alikes or dropped — a provider's name or a sentence never becomes a link, a table cell or bold. */
export function mdText(s: string | null | undefined): string {
  return String(s ?? "")
    .replace(/[\r\n]+/g, " ")
    .replace(/[`*]/g, "")
    .replace(/\[/g, "(")
    .replace(/\]/g, ")")
    .replace(/\|/g, "/")
    .replace(/^(#+|>|-|\d+\.)\s/, "")
    .trim();
}
function link(r: { player_name: string; gsis_id: string | null }): string {
  const name = mdText(r.player_name);
  return r.gsis_id && /^00-\d{7}$/.test(r.gsis_id) ? `[${name}](/player/${r.gsis_id})` : name;
}
export function asOf(today: Date, week: number | null): string {
  const d = today.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "America/New_York" });
  return `*As of ${d}${week ? `, week ${week}` : ""}. The numbers are written in: they will not change after this is published.*`;
}

function vs(r: BoardRow): string {
  return `${r.team ?? "–"} ${r.is_home === false ? "at" : "vs"} ${r.opponent}`;
}

async function board(position: string, tone: string, limit: number, sort = "projection"): Promise<MatchupBoard> {
  return get<MatchupBoard>(boardPath(L, { position, q: "", game: "", tone, sort, offset: 0, limit }));
}

async function matchups(today: Date): Promise<Draft> {
  const [wrUp, wrDown, teUp, teDown] = await Promise.all([
    board("WR", "favorable", 6),
    board("WR", "difficult", 6),
    board("TE", "favorable", 4),
    board("TE", "difficult", 4),
  ]);
  const week = wrUp.week ?? null;
  const line = (r: BoardRow) => {
    const words = [r.context?.defense?.words, r.context?.cb?.words].filter((w): w is string => !!w).map((w) => mdText(w));
    return `- **${link(r)}** (${vs(r)}): projected ${fmt(r.proj_points)} (${fmt(r.p10)} to ${fmt(r.p90)})${words.length ? ` — ${words.join(" ")}` : ""}`;
  };
  const section = (title: string, rows: BoardRow[]) => [`### ${title}`, "", ...(rows.length ? rows.map(line) : ["- Nobody this week."]), ""];
  const body = [
    asOf(today, week),
    "",
    TAKE,
    "",
    "## Receivers to target",
    "",
    ...section("Wide receivers", wrUp.rows),
    ...section("Tight ends", teUp.rows),
    TAKE,
    "",
    "## Receivers to be careful with",
    "",
    ...section("Wide receivers", wrDown.rows),
    ...section("Tight ends", teDown.rows),
    TAKE,
    "",
    "## What these words assume",
    "",
    mdText(wrUp.tone_words),
    "",
    mdText(wrUp.projection_words),
  ].join("\n");
  return {
    title: `Matchups to target and avoid${week ? `, week ${week}` : ""}`,
    summary: "The receivers with the friendliest and toughest matchups this week, and what the numbers say about them.",
    tags: ["matchups"],
    author: "",
    body,
    slug: null,
  };
}

async function projections(today: Date): Promise<Draft> {
  const positions = ["QB", "RB", "WR", "TE"] as const;
  const boards = await Promise.all(positions.map((p) => board(p, "", 8)));
  const week = boards[0]?.week ?? null;
  const parts: string[] = [asOf(today, week), "", TAKE, ""];
  positions.forEach((p, i) => {
    const rows = boards[i]?.rows ?? [];
    parts.push(`## ${{ QB: "Quarterbacks", RB: "Running backs", WR: "Wide receivers", TE: "Tight ends" }[p]}`, "");
    if (!rows.length) parts.push("Nobody projected yet.", "");
    else {
      parts.push("| Player | Game | Projection | Range (10th to 90th) |", "|---|---|--:|--:|");
      for (const r of rows) parts.push(`| ${link(r)} | ${mdText(vs(r))} | ${fmt(r.proj_points)} | ${fmt(r.p10)} to ${fmt(r.p90)} |`);
      parts.push("", TAKE, "");
    }
  });
  parts.push("## How to read the range", "", "Half PPR points. The range is the projection's 10th to 90th percentile: eight weeks in ten land inside it.", "", mdText(boards[0]?.projection_words));
  return {
    title: `This week's top projections and their ranges${week ? `, week ${week}` : ""}`,
    summary: "The top projected players at each position this week in Half PPR, with how wide each projection's range is.",
    tags: ["projections"],
    author: "",
    body: parts.join("\n"),
    slug: null,
  };
}

async function roles(today: Date): Promise<Draft> {
  const p = await get<Projections>(projectionsPath("dk"));
  const up: string[] = [];
  const down: string[] = [];
  for (const r of p.players) {
    const s = r.context?.find((c) => c.signal === "role");
    if (!s || !s.trend) continue;
    const line = `- **${link(r)}** (${mdText(r.position)}, ${mdText(r.team)}): ${mdText(s.words)}`;
    if (s.trend === "up" && up.length < 10) up.push(line);
    if (s.trend === "down" && down.length < 10) down.push(line);
  }
  const body = [
    asOf(today, p.week),
    "",
    TAKE,
    "",
    "## A bigger role lately",
    "",
    ...(up.length ? up : ["- Nobody this week."]),
    "",
    TAKE,
    "",
    "## A smaller role lately",
    "",
    ...(down.length ? down : ["- Nobody this week."]),
    "",
    TAKE,
    "",
    "## What this measures",
    "",
    "His share of his team's targets, carries and snaps in his last two games, against his games before them. It is context: the projection does not lean on these two games alone.",
  ].join("\n");
  return {
    title: `Players whose role is changing${p.week ? `, week ${p.week}` : ""}`,
    summary: "Who is getting more of his team's targets, carries and snaps lately, and who is getting less.",
    tags: ["roles"],
    author: "",
    body,
    slug: null,
  };
}

export function starter(kind: StarterKind, today = new Date()): Promise<Draft> {
  return kind === "matchups" ? matchups(today) : kind === "projections" ? projections(today) : roles(today);
}
// ---- end IO-3
