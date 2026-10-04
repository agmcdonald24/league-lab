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
| ink / ink-2 / ink-3 | `text-ink` … | `#f3f5f9` / `#b8c0cf` / `#8b95a8` | `#0b0e14` / `#454e63` / `#5c6579` | text: primary / secondary / labels, axes. IE-2: ink-3 ≥ 4.5:1 on every surface in both modes (light 4.97–5.85, dark 5.34–6.45; was 4.16–4.89 / 4.82–5.82) |
| accent | `bg-accent text-on-accent`, `text-accent`, `bg-accent-soft` | `#3fd17a` | `#15803d` | the picked tab, links, "yours" |
| good / bad / warn | `text-good` … | `#3fd17a` / `#ff7a7a` / `#fbbf3c` | `#006300` / `#b42318` / `#8a4b00` | deltas and states, always with ▲ ▼ or an icon |
| series-1 | `--ll-series-1` | `#3987e5` | `#2a78d6` | a chart's main series (actual points) |
| hot / due | `--ll-div-hot` / `--ll-div-due` | `#f07a45` / `#3987e5` | `#eb6834` / `#2a78d6` | over- vs under-performing (warm = running hot, cool = due) |
| sequential | `seqFill(t)` | `#151c28` → `#86b6ef` | `#f3f7fd` → `#184f95` | heatmaps (more = stronger; the anchor flips in dark) |
| grid / axis | `--ll-grid` / `--ll-axis` | `#222a38` / `#364052` | `#e3e6ec` / `#c3c8d2` | hairline, solid, never dashed |
| positions | `positionColor(p)` | QB `#d55181` · RB `#199e70` · WR `#3987e5` · TE `#d95926` · K `#9085e9` · DEF `#c98500` | the light steps of the same hues | position chips (wash + dot; the text stays ink) |

The chart hues are the dataviz reference palette's validated slots (blue, orange, aqua, yellow, magenta, violet) in
both modes; nothing is eyeballed.

**Type** (system sans everywhere; no web font, nothing to download before the first screen): `text-label` 12 px (IE-2: was 11 px)
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

- **TopBar** — rendered ONCE by `App.svelte` for every league screen and the player's page (pages do not render it):
  the four tabs by task, the search field, the league / team picker, the overflow menu (⋯) and the second row of the
  tab's screens — see **§ Navigation**. The sections live in `TopBar.svelte`'s module (`SECTIONS`, `sectionOf`). The
  page content sits in `App.svelte`'s container (`max-w-6xl`, `px-4`, room for the bottom bar): a page starts with its
  `<main>`, no side padding of its own.
- **PlayerPane** — the research pane (mounted ONCE by `App.svelte`; a screen calls `openPane` / `paneLink` from
  `lib/pane.svelte.ts`) — see **§ Pane**.
- **ScreenHead** — the top of a screen, the answer first:
  `<ScreenHead eyebrow="Research · Trends" title="Who is due, who is running hot">{#snippet answer()}…{/snippet}</ScreenHead>`
- **Card** — the panel: `<Card title="Usage" accent={team(p.team).accent} testid="usage">…</Card>`; `tone="raised" | "accent"`,
  `pad={false}` for a list inside, an `action` snippet on the title's right.
- **PlayerRow** — one player in a list: `<PlayerRow player={p} href={withContext(`/player/${p.gsis_id}`, ctx)} context="WR4 · yours"
  value={fmt.pts(p.proj)} valueLabel="proj" yours={p.rostered_by_roster_id === team} />`; `rank`, `selected`,
  `onselect` (list + detail: a tap on the row picks him for the detail pane; a tap on the name opens his card), a `trailing`
  snippet (a bar instead of the number). `player` = `{ gsis_id, player_name, position, team, headshot_url }` — the
  contract's player fields.
- **PlayerCard** — the unit: `<PlayerCard player={p} number={fmt.pts(p.proj)} numberLabel="Week 5" line="7.1 targets per game · 26% share"
  context="Shake & Bake" href={…} />`; `compact` for a grid; an `extra` snippet for bars under the line.
- **Headshot** — `<Headshot url={p.headshot_url} team={p.team} size={40} />`: lazy, the team's color behind, a silhouette
  when null or broken. **PosBadge** `<PosBadge pos="WR" />`, **TeamBadge** `<TeamBadge team="DET" />`.
- **StatTile** — `<StatTile label="Points per game" value="14.2" delta={+2.1} caption="vs his expected" />`; `upIsGood={false}`
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
- **Chips** — a row of filter chips: `<Chips label="Position" testid="pos" current={pos} onpick={(p) => setParams({ position: p })} items={…} />`
  (put filters in the URL with `setParams`: shareable, no Back step).
- **Coming** — a screen on its way: `<Coming title="Waivers" what="…" />` (the Decisions tabs until G4's screens land).
- **GameLog** — the player card's chart card (fetches `/api/player/{gsis}/games`, 2026 / 2025, the answer above the chart):
  `<GameLog gsis={id} {league} season={2026} {onauth} leagueName="…" />`.

**Loading a screen's data**: `const r = new Remote<T>(); $effect(() => r.load(path, onauth));` (`lib/remote.svelte.ts`):
the cached answer at once (Back renders synchronously), the error in plain words, `keep` holds the old answer while a
new one loads (no skeleton flash). **For G4's screens**: render inside `App.svelte`'s container (no `TopBar` of your
own); wire a route by replacing its `<Coming …>` line in `App.svelte` with a lazy import like the research screens'
(`LAZY` map); start with `ScreenHead` + the answer; use `PlayerCard` / `PlayerRow` / `Bar` for the free agents and the
trade sides.
- Wave F pieces restyled on the tokens: **Section** (the player card's sections), **Metrics** (now StatTiles),
  **Expander**, **LineupTable**, **Md**, **Picker**, **Login**.

- **Wave I-A (IA-1) patterns.** *Short names*: `shortName(name, position, others)` (`lib/names.svelte.ts`) — "J. Jefferson"
  under 640 px, the first name grown only when two in the same list would read the same ("Jam." / "Jav. Williams"), a
  defense and a first name in initials ("D.J.") never shortened; the whole name stays in the link's `aria-label`.
  *LineupTable*: a 32 px headshot on every row (the table-row size: a 40 px `PlayerRow` headshot leaves no room for the
  name at 375 px); the flag (OUT chip, locked, injury tag) and, in the full list, the margin go under the name on a phone,
  so the name keeps the width. *Section title* (a section that is not a `Card`): `<h2 class="text-lg font-bold
  leading-tight">` with an optional one-line `text-sm text-ink-3` caption under it (My Week's "Your lineup", Matchups'
  "The cornerbacks your receivers face"). *Decision card*: the call (bold) · the reason (body size, `text-ink-2`,
  `data-testid="card-why"`) · the small print (`text-sm text-ink-3`: the odds, the numbers, the ranges, the matchups).
  *A list row's numbers* (Trends): one header row of `ll-label`s over the list and a 5-column strip under each
  `PlayerRow`, indented to the name (`pl-16`), the season value under the last-3 value on a phone.

- **Wave I-B (IB-3) patterns.** *Tone chip* (Matchups): the signal of a matchup is a word — Favorable / Neutral /
  Difficult — in the state color (good / ink-3 / bad) on its 22 % wash, ▲ / ▼ before it (color never alone); the rank
  sits under it in 11 px `text-ink-3` ("#3 toughest vs RB"; a cornerback call's certainty — likely / unclear / no call —
  takes that place). *Tone heatmap*: `Heatmap … tones` fills a cell with its tone's wash (30 %), prints ▲ / ▼ with the
  number, and the legend names the three tones. *View toggle* (Season): `Tabs fill size="sm"` under the screen head
  ("Value to my lineup" · "Who scores the most"), in the URL (`?view=points`; the default left out). *Decision card*
  (My Week): the status chip first (Change needed on `bg-warn-soft`, Already set on `bg-accent-soft`, Close call on
  `bg-raised`; the card's left rule turns warn on a change), the slot label and the strength word on the same row, the
  call in one line (both names whole), the reason (last names), a "Compare these players" button, and the odds, ranges
  and numbers behind a "Why?" `<details>`.

- **Wave I-B (IB-2) patterns.** *Claim card* (`routes/decisions/ClaimCard.svelte`, Waivers): the free agent (48 px
  headshot, name, position + team, "drop X" in the context line), the lineup gain as the number with its span under it
  (`ll-label`: "weeks 4–7", or "week 5" in Bye coverage), then ONE reason (body size: a fact — the role, the bye, the
  slot), then the claim's cost (`text-sm text-ink-3`). A drop who starts for you this week or next adds a `bg-warn-soft`
  box: "X starts for you this week." + the best claim that keeps him, or the line that none does — never one without
  the other. `compact` = a list row (no frame) for a view's list. *Views behind chips*: a screen with several lists
  shows ONE at a time — `Chips` under the lead cards, the view in the URL (`?view=`, rewritten in place; the default
  leaves the URL), one answer carrying every view so a chip switches without a request (Waivers: Help now · Bye
  coverage · Stashes · All available). The chip row must start within two phone screens (≤ 2 × 812 px at 375 px).
  *Verdict bar* (the trade calculator): once the decision (the dial's row) scrolls off screen, a bar is pinned to the
  top (`position: fixed`, `max-w-6xl` like the page, rounded at the bottom, `shadow-lg`): the package in last names,
  the dial's label (state color + word) and score, "You +3.4"; open on desktop (the four tiles and the verdict), a tap
  opens it on a phone (`aria-expanded`). Not `sticky`: `html, body { overflow-x: hidden }` makes `body` the sticky
  container, so `position: sticky` never sticks on these pages (ListDetail's `wide:sticky` detail included) — use
  fixed, or change the clip to `overflow-x: clip` (a design-system decision, not taken here). *Why? / Lineups*: the
  explanation and the before / after lineups behind two `Expander`s, collapsed: a screen leads with the decision.

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
- **Paired bars** (Compare): the first player in series 1 (blue), the second in the diverging warm (orange), a legend
  above, the better number bold. Not team colors: two teams can share a color, or read as good / bad (green vs red).
- **Over / under** (Trends): one diverging bar per player from a middle zero, warm (orange) = running hot, cool (blue) =
  due; the signed number beside it.
- **Dial** (IA-2, `routes/decisions/Dial.svelte`: the trade calculator's "their interest"): a half-circle gauge in four
  equal bands (No deal · Maybe · Likely · Hard to say no) in the state tokens (bad / warn / good) at a 22 % wash, the
  band the needle sits in at full strength; a needle in ink that swings (CSS transition, 450 ms) to the score 0–100 on
  every change, never redrawn; under it the label in words (colored, never color alone), "72 / 100 · by our numbers
  over weeks 4–7", and the second number small: "You · weeks 4–7 +3.4". One dial per screen, for one question (how
  much would the other side want it); a share of a whole stays a Meter, a comparison a Bar.
- **Window control** (IA-2, `routes/decisions/WindowControl.svelte`): which weeks a decision is priced over — This week ·
  Next 4 · Rest of season · Playoffs — four equal cells in one row (a label wraps inside its cell at 375 px; the row
  never scrolls), the picked one in accent, and one line under it that says why those weeks ("Weeks 4–7: the next four
  weeks: far enough to matter, near enough to trust."). In the URL (`?window=`), the default (next 4) left out.

- **Range bar in a table cell** (Rest of season, IA-3): the floor–ceiling span on a 0…list-max track (`bg-sunken`, ≤ 8 px),
  the span in series 1 at 45 %, the projection a 3 px tick in series 1; the numbers printed under it ("150–219"). From
  640 px; a phone reads the range in the expanded row.
- **Tap-to-expand row** (Rest of season, IA-3): a `›` button (32 px, `aria-expanded`) at a row's end opens one full-width
  row under it on `bg-raised`: StatTile-like tiles of the pieces, the facts line, "Why this number" (label in accent, the
  chain sentence bold, one line a piece). The expand row spans exactly the columns showing at this width (a larger
  `colspan` adds phantom columns to a fixed-layout table and squeezes the name). Sortable headers are buttons with
  `aria-sort` and a ▲ / ▼ in accent; the default sort is marked too.
- Never: two y-axes, a number on every point, a 9th color, dashed gridlines, a pie for close values, color as the only
  carrier of a value (each value is printed somewhere: a label, the readout, the table).

## Navigation (Wave I-B, IB-1)

Four tabs by task — what the user came to do, not how we compute it:

| Tab (`tab-<key>`) | Second row (`sub-<route>`) | Paths |
|---|---|---|
| **My Team** (`myteam`) | This week · Season · Team · League | `/` · `/ros` · `/team` · `/league` |
| **Waivers** (`waivers`) | — (one screen; its views are chips inside it) | `/waivers` |
| **Trades** (`trades`) | Partners · Calculator | `/trades` · `/trade-calc` |
| **Players** (`players`) | Trends · Matchups · Receivers · Compare · Players | `/trends` · `/matchups` · `/receivers` · `/compare` · `/players` |

- **Paths never move** (bookmarks, shared links, Wave F's `/record`): only the grouping and the labels change. A tab
  opens its first screen; the second row shows the tab's screens, the one on screen marked (`aria-current="page"`).
- **Phone**: the four tabs are the bottom bar (icon + label, thumb reach); the second row sits under the top bar and
  scrolls inside itself when it does not fit (the page never scrolls sideways). The top row: the league / team picker,
  the magnifier (the search field opens over the row, with Cancel), the overflow menu (⋯). The wordmark shows from
  640 px (on a phone My Team is the way home and the picker needs the width).
- **900 px+**: the tabs sit in the top bar; **1280 px+** the search field is always open (`data-testid="search"`).
- **The search field** (every league screen and the player's page): two letters → `/api/search` → a hit opens the
  research pane (`from: "search"`), Enter picks the first hit.
- **About the numbers** (and the record) is not a tab: the overflow menu's first item (`menu-about`, marked when on
  screen) and a link at the foot of every My Team screen (`foot-about`).
- **The player's page** renders in the same frame (top bar, tabs, search): the tab you came from stays lit, its
  second row is not shown (none of its screens is on screen). "‹ Back" goes where you came from; opened from a link
  (nothing behind it in the app) it says "‹ My week" and goes there.

## Pane (Wave I-B, IB-1)

The research pane is how a player opens from anywhere a name is a means, not the destination: a lineup row, a waiver
candidate, a trade list row, a search hit, a research list. His full page stays one tap away ("Full page").

- **Layout**: from 900 px a panel beside the screen (`25rem`, sticky, the screen narrows and stays usable — another
  name swaps the player in place); on a phone a **sheet** from the bottom (`88dvh` at most, a grab handle, the name +
  × in a sticky head, the screen dimmed behind it; a tap on the dim, ×, Escape or Back closes it). The design
  system's sheet is this one.
- **Contents**: the player card unit (`PlayerCard`, this week's projection), the **actions**, the card's sections in
  the full page's order (`lib/card.ts`: Projection, Value, Availability, Usage, Signals) with the Metrics tiles two to
  a row, his game log. Nothing per-screen inside the pane.
- **Actions by where it was opened from** (`from`): `lineup` → **Compare with my starter** (a bench player: the
  weakest starter he could replace) or **Compare with my best bench option** (a starter: the best bench player who
  fits his slot) → `/compare?a=&b=`; `waiver` → **Evaluate add / drop** → `/waivers?add=<sleeper id>[&drop=]`;
  `trade` → **Add to trade** → `/trade-calc` with him ticked (added to the package when the calculator is open with
  the same partner); always **Full page**. An action whose context is missing is not shown (never a dead button).
- **API** (`lib/pane.svelte.ts`): `openPane(gsis, { from, context })`, `closePane()`, and `paneLink(gsis, opts)` — an
  attachment for a name link (`{@attach paneLink(id, { from: "waiver", context: { add, drop } })}`): a plain tap opens
  the pane, Cmd / Ctrl / middle click still opens the page. `PlayerRow` / `PlayerCard` / `LineupTable` take a `pane`
  prop that does this for their name link.
- **URL and history**: `?pane=<gsis>&from=<from>` on the screen's own path. The first pane is a new history entry
  (Back closes it; the screen does not scroll), a swap replaces it, "Full page" replaces it with the player's page
  (Back from there lands on the screen, not on the pane). The context lives in memory: after a reload only "Full page"
  is offered.
- `html, body` use `overflow-x: clip` (with `hidden` as the fallback): `hidden` on both made `<body>` a scroll box and
  no sticky element (the pane, ListDetail's detail) stuck to the screen.

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
