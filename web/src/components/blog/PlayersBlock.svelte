<script lang="ts" module>
  // ---- IN-1 (Wave I-N): a post's live table — a fenced ```players block (one gsis id or one column id per line; a
  // "cols: a, b" line works too) → those players' Stats rows on Half PPR, season to date, in the Stats screen's own
  // table (components/stats/StatsTable.svelte). One block per post (docs/BLOG.md). Bounded: 12 players, 8 columns.
  export const MAX_PLAYERS = 12;
  export const MAX_COLS = 8;
  export const DEFAULT_COLS = ["games", "points", "targets", "target_share", "receiving_yards"];
  export function parseBlock(body: string): { ids: string[]; cols: string[] } {
    const ids: string[] = [];
    const cols: string[] = [];
    for (const raw of body.split("\n")) {
      const line = raw.trim().replace(/^cols?\s*:\s*/i, "");
      for (const tok of line.split(/[\s,]+/).filter(Boolean)) {
        if (/^00-\d{7}$/.test(tok)) {
          if (!ids.includes(tok) && ids.length < MAX_PLAYERS) ids.push(tok);
        } else if (/^[a-z0-9_]{1,40}$/.test(tok) && !cols.includes(tok) && cols.length < MAX_COLS) cols.push(tok);
      }
    }
    return { ids, cols };
  }
</script>

<script lang="ts">
  import { get, statsPath, type StatsColumn, type StatsFrame, type StatsRow } from "../../lib/api";
  import { REF_DEFAULT, refLabel } from "../../lib/refleague";
  import StatsTable from "../stats/StatsTable.svelte";

  let { body }: { body: string } = $props();
  const L = REF_DEFAULT;
  const want = $derived(parseBlock(body));

  let frame = $state<StatsFrame | null>(null);
  let failed = $state(false);
  $effect(() => {
    get<StatsFrame>(statsPath(L, { position: "ALL", window: "season" }))
      .then((f) => (frame = f))
      .catch(() => (failed = true));
  });
  let sortId = $state<string | null>(null);
  let dir = $state<"asc" | "desc">("desc");

  const cols = $derived.by<StatsColumn[]>(() => {
    if (!frame) return [];
    const ask = want.cols.length ? want.cols : DEFAULT_COLS;
    return ask.map((id) => frame!.catalogue.find((c) => c.id === id)).filter((c): c is StatsColumn => !!c && c.status !== "unavailable");
  });
  const rows = $derived.by<StatsRow[]>(() => {
    if (!frame) return [];
    const byId = new Map(frame.players.map((p) => [p.gsis_id, p]));
    const picked = want.ids.map((id) => byId.get(id)).filter((p): p is StatsRow => !!p);
    if (!sortId) return picked;
    const k = (p: StatsRow) => (typeof p[sortId!] === "number" ? (p[sortId!] as number) : -Infinity);
    return [...picked].sort((a, b) => (dir === "desc" ? k(b) - k(a) : k(a) - k(b)));
  });
  const missing = $derived(frame ? want.ids.filter((id) => !frame!.players.some((p) => p.gsis_id === id)) : []);
  function onsort(c: StatsColumn) {
    if (sortId === c.id) dir = dir === "desc" ? "asc" : "desc";
    else [sortId, dir] = [c.id, "desc"];
  }
</script>

<figure class="my-5 space-y-2" data-testid="post-players">
  {#if failed}
    <p class="rounded-md bg-raised px-3 py-2 text-sm text-ink-2" data-testid="post-players-failed">The live table did not load. Open the players on Stats instead.</p>
  {:else if !frame}
    <div class="ll-skel h-32" aria-label="Loading"></div>
  {:else if rows.length && cols.length}
    <StatsTable
      {rows}
      {cols}
      mode="game"
      limit={Infinity}
      {sortId}
      {dir}
      {onsort}
      href={(p) => `/player/${p.gsis_id}?league=${encodeURIComponent(L)}`}
      mine={() => false}
      caption={`${rows.length} players, ${frame.window?.label ?? "this season"}, per game`}
    />
  {:else}
    <p class="rounded-md bg-raised px-3 py-2 text-sm text-ink-2" data-testid="post-players-none">None of these players has a game this season yet.</p>
  {/if}
  {#if frame}
    <figcaption class="text-sm leading-snug text-ink-3" data-testid="post-players-note">
      Live: this season to date, per game, in {refLabel(L)} scoring — the numbers move with every nightly update.
      {#if missing.length}Not in this season's table yet: {missing.length} player{missing.length === 1 ? "" : "s"}.{/if}
    </figcaption>
  {/if}
</figure>
