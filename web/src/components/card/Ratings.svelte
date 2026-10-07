<script lang="ts">
  // IP-4 (Wave I-P): the card's ratings — his percentile among his position's players this season, on a 0–99 scale,
  // for six to eight things that matter at his position (GET /api/player/{gsis}/ratings). Each row: the name, a bar,
  // the rating, the raw number; under the minimum sample, a dash and the reason (never a low number). The overall is
  // the plain average of the ratings shown and says so. A tap on a row opens its definition and sample; "What these
  // are" holds how they are made. They describe the season so far: they are not a forecast, and say it.
  import { ApiError, cardPaths, get, peek, Unauthorized, type Rating, type Ratings } from "../../lib/api";

  let { gsis, league, position, compact = false, onauth, testid = "card-ratings" }: {
    gsis: string;
    league: string | null;
    position: string;
    compact?: boolean;
    onauth?: () => void;
    testid?: string;
  } = $props();

  const RATED = ["QB", "RB", "WR", "TE"];
  let data = $state<Ratings | null>(null);
  let failed = $state<string | null>(null);
  let open = $state<string | null>(null);

  $effect(() => {
    const id = gsis;
    failed = null;
    open = null;
    if (!RATED.includes(position)) {
      data = null;
      return;
    }
    const path = cardPaths.ratings(id, league);
    const hit = peek<Ratings>(path);
    data = hit ?? null;
    if (hit) return;
    get<Ratings>(path)
      .then((d) => {
        if (gsis === id) data = d;
      })
      .catch((e) => {
        if (gsis !== id) return;
        if (e instanceof Unauthorized) onauth?.();
        else failed = e instanceof ApiError && e.status === 404 ? "No ratings for him yet." : "Ratings did not load. Open the page again in a minute.";
      });
  });

  /** tier: the rating's colour (the number is always printed beside it) */
  const tier = (r: number) => (r >= 80 ? "var(--ll-good)" : r >= 60 ? "var(--ll-series-1)" : r >= 40 ? "var(--ll-ink-3)" : "var(--ll-warn)");
  const shown = $derived((data?.ratings ?? []).filter((r) => r.rating !== null).length);
  const plural = (p: string) => ({ QB: "quarterbacks", RB: "running backs", WR: "receivers", TE: "tight ends" })[p] ?? "players";
  const short = (r: Rating) => (r.rating !== null ? r.words : r.words.replace(/^Not rated: /, "").replace(/^No value for him: /, ""));
</script>

{#if RATED.includes(position)}
  <section class="rounded-xl border border-line bg-surface {compact ? 'p-3' : 'p-4'}" style="box-shadow:var(--ll-shadow)" data-testid={testid} aria-labelledby="{testid}-title">
    <div class="flex items-start gap-3">
      <div class="min-w-0 flex-1">
        <h2 id="{testid}-title" class="text-lg leading-tight font-bold">Ratings</h2>
        <p class="mt-0.5 text-xs leading-snug text-ink-3" data-testid="ratings-label">
          Where he ranks this season among {plural(position)}{#if data?.population}&nbsp;with {data.population}{/if}, 0–99. Not a projection.
        </p>
      </div>
      {#if data}
        <div class="shrink-0 text-center" data-testid="ratings-overall" title={data.overall_words ?? ""}>
          <div
            class="grid h-14 w-14 place-items-center rounded-lg text-2xl font-black tracking-tight tabular-nums"
            style={data.overall === null ? "" : `color:${tier(data.overall)};background:color-mix(in oklab, ${tier(data.overall)} 14%, transparent);box-shadow:inset 0 0 0 1.5px color-mix(in oklab, ${tier(data.overall)} 55%, transparent)`}
            class:bg-raised={data.overall === null}
            class:text-ink-3={data.overall === null}
          >
            {data.overall ?? "—"}
          </div>
          <div class="mt-1 text-[11px] leading-tight text-ink-3">average of {shown}</div>
        </div>
      {/if}
    </div>

    {#if failed}
      <p class="mt-3 text-sm text-ink-3" data-testid="ratings-error">{failed}</p>
    {:else if !data}
      <div class="mt-3 space-y-2" aria-label="Loading">{#each [0, 1, 2, 3, 4, 5] as i (i)}<div class="ll-skel h-5"></div>{/each}</div>
    {:else}
      {#if data.words}<p class="mt-2 text-sm text-ink-2" data-testid="ratings-words">{data.words}</p>{/if}
      <ul class="mt-3 divide-y divide-line" data-testid="ratings-list">
        {#each data.ratings as r (r.key)}
          <li data-testid="rating" data-key={r.key}>
            <button
              type="button"
              class="grid w-full grid-cols-[minmax(0,1fr)_3.5rem_2.25rem_3.25rem] sm:grid-cols-[minmax(0,1fr)_5.5rem_2.25rem_3.5rem] items-center gap-x-2.5 py-1.5 text-left {compact ? 'min-h-9' : 'min-h-10'}"
              aria-expanded={open === r.key}
              onclick={() => (open = open === r.key ? null : r.key)}
            >
              <span class="min-w-0 text-sm leading-tight text-ink-2">{r.label}</span>
              <span class="relative h-2 rounded-sm bg-sunken" aria-hidden="true">
                {#if r.rating !== null}<span class="absolute inset-y-0 left-0 rounded-sm" style="width:{Math.max(3, r.rating)}%;background:{tier(r.rating)}"></span>{/if}
              </span>
              <span class="text-right text-lg leading-none font-extrabold tabular-nums" style={r.rating !== null ? `color:${tier(r.rating)}` : ""} class:text-ink-3={r.rating === null} data-testid="rating-value"
                >{r.rating ?? "—"}</span
              >
              <span class="truncate text-right text-xs text-ink-3 tabular-nums" data-testid="rating-raw">{r.display}</span>
            </button>
            {#if r.rating === null && open !== r.key}
              <p class="-mt-1 pb-1.5 text-xs leading-snug text-ink-3" data-testid="rating-reason">{short(r)}</p>
            {/if}
            {#if open === r.key}
              <div class="space-y-1 pb-2 text-xs leading-snug text-ink-2" data-testid="rating-detail">
                <p>{r.words}{r.lower_is_better && r.rating !== null ? "" : ""}</p>
                {#if r.definition}<p class="text-ink-3">{r.definition}</p>{/if}
                {#if r.percentile !== null}<p class="text-ink-3">Percentile {r.percentile.toFixed(0)}: ahead of {r.percentile.toFixed(0)}% of the {r.n} {plural(position)} ranked{r.lower_is_better ? " (fewer is better, so the order is turned round)" : ""}.</p>{/if}
              </div>
            {/if}
          </li>
        {/each}
      </ul>
      <details class="mt-2 text-sm" data-testid="ratings-how">
        <summary class="inline-flex min-h-9 items-center gap-1 text-ink-2"><span class="chev" aria-hidden="true">›</span>What these are</summary>
        <div class="mt-1 space-y-1.5 text-xs leading-snug text-ink-2">
          {#if data.how}<p>{data.how}</p>{/if}
          {#if data.overall_words}<p>Overall: {data.overall_words}</p>{/if}
          <p class="text-ink-3">Season {data.season}{data.through_week ? `, through week ${data.through_week}` : ""}. The same in every league and scoring: these are his usage and efficiency, not points.</p>
        </div>
      </details>
    {/if}
  </section>
{/if}
