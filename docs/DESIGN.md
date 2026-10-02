# Design — the web app's system (Wave G, G3)

The look Andrew asked for (2026-10-02, five Madden screenshots): **the player card is the unit** (headshot, a big
headline number, position and team as badges, one line of context); **dark first** with a light mode from the
system; **dense panels with a strong type hierarchy** (small uppercase labels, big numbers); **list on the left, detail
on the right** at desktop width, stacked on a phone; **bars and meters** for comparisons; **team colors as accents**.
What we do not copy: game chrome ("Press X", currencies, OVR ratings we do not have, fake badges, background art,
condensed display fonts that must be downloaded). The words stay plain (`docs/WORDS.md`).

Files: `web/src/app.css` (tokens), `web/src/lib/theme.ts` (team accents, position colors, chart roles, number
formats), `web/src/lib/chart.ts` (the chart kit's arithmetic), `web/src/components/*` (the pieces below).

## Tokens (`app.css`)

Every color is a CSS variable `--ll-*` set for light (`:root`) and dark (`@media (prefers-color-scheme: dark)`), exposed
to Tailwind through `@theme inline`, so components write `bg-surface text-ink-2 border-line` and never a raw color.

| Role | Tailwind | Dark | Light | Use |
|---|---|---|---|---|
| page | `bg-page` | `#0a0d13` | `#f2f4f7` | behind everything |
| surface | `bg-surface` | `#121721` | `#ffffff` | a card / panel |
| raised | `bg-raised` | `#1a2130` | `#f5f7fa` | a tile inside a card, a table header, hover |
| sunken | `bg-sunken` | `#0d1118` | `#e9edf2` | a bar's track, an input |
| line / line-strong | `border-line` | 8 % / 16 % white | 10 % / 20 % ink | hairlines |
| ink / ink-2 / ink-3 | `text-ink` … | `#f3f5f9` / `#b8c0cf` / `#838da0` | `#0b0e14` / `#454e63` / `#687186` | text: primary / secondary / labels, axes |
| accent | `bg-accent text-on-accent`, `text-accent`, `bg-accent-soft` | `#3fd17a` | `#15803d` | the picked tab, links, "yours" |
| good / bad / warn | `text-good` … | `#3fd17a` / `#ff7a7a` / `#fbbf3c` | `#006300` / `#b42318` / `#8a4b00` | deltas and states, always with ▲ ▼ or an icon |
| series-1 | `--ll-series-1` | `#3987e5` | `#2a78d6` | a chart's main series (actual points) |
| hot / due | `--ll-div-hot` / `--ll-div-due` | `#f07a45` / `#3987e5` | `#eb6834` / `#2a78d6` | over- vs under-performing (warm = running hot, cool = due) |
| sequential | `seqFill(t)` | `#151c28` → `#86b6ef` | `#f3f7fd` → `#184f95` | heatmaps (more = stronger; the anchor flips in dark) |
| grid / axis | `--ll-grid` / `--ll-axis` | `#222a38` / `#364052` | `#e3e6ec` / `#c3c8d2` | hairline, solid, never dashed |
| positions | `positionColor(p)` | QB `#d55181` · RB `#199e70` · WR `#3987e5` · TE `#d95926` · K `#9085e9` · DEF `#c98500` | the light steps of the same hues | position chips (wash + dot; the text stays ink) |

The chart hues are the dataviz reference palette's validated slots (blue, orange, aqua, yellow, magenta, violet) in
both modes; nothing is eyeballed.

**Type** (system sans everywhere; no web font, nothing to download before the first screen): `text-label` 11 px
uppercase, tracked 0.08 em, semibold (`.ll-label`) · `text-xs` 12 · `text-sm` 13 · `text-base` 15 (body) · `text-lg` 17
· `text-xl` 20 · `text-2xl` 24 (a screen's title) · `text-3xl` 30 · `text-num` 36 (a card's headline number) ·
`text-hero` 48 (the one number a screen leads with, at most one). Big numbers use proportional figures; columns of
numbers use `.tabnum`.

**Spacing**: Tailwind's 4 px steps; a card pads 16 px (`p-4`), a tile 12 × 10; lists are 56 px rows (a thumb).
**Radii**: `rounded-sm` 6 (chips, tiles, tabs), `rounded-md` 10 (inputs, tables), `rounded-lg` 14 (cards).
**Breakpoints**: phone first at 390 px; `sm` 640 px (more table columns); `wide` 900 px (list + detail, the tabs move
into the top bar). Nothing scrolls sideways at 390.

**Team accents** (`theme.ts`): `TEAMS[abbr] = { name, primary, accent }` for all 32 teams in nflverse codes (`LA` = the
Rams; `LAR`, `JAC`, `WSH`, `OAK`, `SD`, `STL` map over). `primary` fills the team badge (`onColor(primary)` picks white
or ink); `accent` is the team color that reads on both surfaces (the card's top stripe and glow, the headshot's halo, a
team bar). A free agent is neutral gray. `teamLabel("LA")` → `LAR`.

## Components (`web/src/components/`)

```svelte
<script lang="ts">
  import Card from "../components/Card.svelte";
  import PlayerCard from "../components/PlayerCard.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import StatTile from "../components/StatTile.svelte";
  import Bar from "../components/Bar.svelte";
  import Meter from "../components/Meter.svelte";
  import Table from "../components/Table.svelte";
  import ListDetail from "../components/ListDetail.svelte";
  import Tabs from "../components/Tabs.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import { fmt, team } from "../lib/theme";
</script>
```

- **TopBar** — rendered ONCE by `App.svelte` for every league screen (pages do not render it): the wordmark, the league /
  team picker, the five top-level tabs (My week · Rest of season · Research · Decisions · About) and, inside Research
  or Decisions, a second row with their screens. On a phone the five tabs are a bottom bar (icons + short labels, one
  tap each); from 900 px they sit in the top bar. Route names and the sections live in `TopBar.svelte`'s module
  (`RESEARCH`, `DECISIONS`, `sectionOf`). The page content sits in `App.svelte`'s container (`max-w-6xl`, `px-4`,
  room for the bottom bar): a page starts with its `<main>`, no side padding of its own.
- **ScreenHead** — the top of a screen, the answer first:
  `<ScreenHead eyebrow="Research · Trends" title="Who is due, who is running hot">{#snippet answer()}…{/snippet}</ScreenHead>`
- **Card** — the panel: `<Card title="Usage" accent={team(p.team).accent} testid="usage">…</Card>`; `tone="raised" | "accent"`,
  `pad={false}` for a list inside, an `action` snippet on the title's right.
- **PlayerRow** — one player in a list: `<PlayerRow player={p} href={withContext(`/player/${p.gsis_id}`, ctx)} context="WR4 · yours"
  value={fmt.pts(p.proj)} valueLabel="proj" yours={p.rostered_by_roster_id === team} />`; `rank`, `selected`,
  `onselect` (desktop list + detail: a click picks him for the right pane; a phone follows the link), a `trailing`
  snippet (a bar instead of the number). `player` = `{ gsis_id, player_name, position, team, headshot_url }` — the
  contract's player fields.
- **PlayerCard** — the unit: `<PlayerCard player={p} number={fmt.pts(p.proj)} numberLabel="Week 5" line="7.1 targets a game · 26% share"
  context="Shake & Bake" href={…} />`; `compact` for a grid; an `extra` snippet for bars under the line.
- **Headshot** — `<Headshot url={p.headshot_url} team={p.team} size={40} />`: lazy, the team's color behind, a silhouette
  when null or broken. **PosBadge** `<PosBadge pos="WR" />`, **TeamBadge** `<TeamBadge team="DET" />`.
- **StatTile** — `<StatTile label="Points a game" value="14.2" delta={+2.1} caption="vs his expected" />`; `upIsGood={false}`
  flips the delta's color; `size="sm" | "md" | "lg"`; a grid of them: `grid grid-cols-2 gap-2 sm:grid-cols-4`.
- **Bar** — a comparison bar (label · value · bar): `<Bar label="Target share" value={0.26} max={0.35} display="26%" mark={0.2}
  markLabel="top-12 average" />`; with `min < 0` the bar grows either way from a middle zero (over / under):
  `<Bar value={gap} min={-6} max={6} color="var(--ll-div-hot)" negColor="var(--ll-div-due)" />`.
- **Meter** — a share of a whole, same-hue track: `<Meter label="Snaps" value={0.82} />`.
- **Table** — sortable, never sideways on a phone: `columns: { key, label, align?, sortable?, phone?: false, width? }[]`
  (`phone: false` → shown from 640 px), rows through a `cell(row, key, i)` snippet, `sort` / `dir` / `onsort`,
  `highlight(row)` (yours).
- **ListDetail** — `<ListDetail>{#snippet list()}…{/snippet}{#snippet detail()}…{/snippet}</ListDetail>`: two columns from
  900 px (the detail sticky), stacked on a phone (`detailFirst` puts the detail on top).
- **Tabs** — a segmented row: links (`href`, shareable, one history entry) or buttons (`onpick`); `fill` shares the row.
- **Coming** — a screen on its way: `<Coming title="Waivers" what="…" />` (the Decisions tabs until G4's screens land).
- Wave F pieces restyled on the tokens: **Section** (the player card's sections), **Metrics** (now StatTiles),
  **Expander**, **LineupTable**, **Md**, **Picker**, **Login**.

## Charts (one kit: `lib/chart.ts` + inline SVG)

Hand-rolled (`linear`, `niceTicks`, `linePath`, `areaPath`; ~1 KB, no library, nothing to load before the first screen),
drawn at the container's measured width, so a chart is sharp at 390 px and at 1300 px, and every color is a token so
light and dark come for free. The rules (the dataviz references):

- **The form follows the job**: a single number is a StatTile, not a chart; a comparison is a Bar; a trend is a line;
  over / under a baseline is a diverging bar; a team × position grid is a heatmap.
- **LineChart** (`points: { week, label?, actual, expected? }[]`): points by week in series 1 (2 px line, a 10 % wash, 8 px
  dots with a 2 px surface ring), expected points in the muted ink, dashed (a model's line, not a score); a legend for
  the two, the last value labelled, hairline solid grid, tap / hover a week to read it, "Show as a table" under it.
  A bye or a missed game breaks the line (unknown is not zero).
- **Heatmap** (`rows`, `cols`, `cell(row, col) → { v, display?, title? }`, `marked["row|col"] = "who"`): one hue, more =
  stronger, each column on its own scale; the number printed in the cell (ink chosen by the fill); your starters'
  cells carry an accent ring and a dot; a scale legend under it.
- **Bar** / **Meter** as above (≤ 8 px thick, square at the baseline, rounded at the data end); **Sparkline** for a
  tile's last games (muted ink, the last point in series 1).
- Never: two y-axes, a number on every point, a 9th color, dashed gridlines, a pie for close values, color as the only
  carrier of a value (each value is printed somewhere: a label, the readout, the table).

## Rules (what the references mean for us)

1. **The answer first**: a screen opens with `ScreenHead` and its answer sentence, then the player cards / list, then
   the digging (tables, expanders, "How to read this").
2. **The player card is the unit**: wherever one player is the subject, use `PlayerCard`; in a list, `PlayerRow`. A
   picture, his position and team as badges, one number that matters on this screen, one line of context.
3. **Dense, not cramped**: small uppercase labels over big numbers; hairlines, not boxes in boxes; 56 px rows.
4. **Dark first**: designed on the dark surfaces; the light mode is the same tokens' light values (the system decides).
5. **Team color is an accent, never a fill behind text** (except the team badge, with `onColor`).
6. **No horizontal tables on a phone**: `Table` hides `phone: false` columns under 640 px; otherwise rows or cards.
7. **No decoration that slows the first screen**: no web fonts, no background images, headshots lazy below the fold.
8. **Same numbers everywhere**: format with `fmt` (`pts`, `signed`, `pct`, `whole`), "—" for unknown.
