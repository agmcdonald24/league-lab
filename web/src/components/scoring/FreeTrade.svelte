<script lang="ts">
  // ---- IN-2 (Wave I-N): the trade calculator without a league (/trade-calc?league=ref:…&give=&get=). Two sides, any
  // player added by search (six a side; picks are not in scope), priced in the scoring the picker holds. The answer
  // first: the gap in words with its uncertainty and how much of it is one player; then each side's value and the range
  // of its season points; per player his value, position rank and weekly outlook; the roster-spot effect of an uneven
  // trade (stated, not added in); what a league would add. The package is the URL (a copied link opens the same trade).
  // GET /api/trade-calc/free (api/league_lab_api/freetrade.py).
  import { ApiError, freeTradePath, get, paths, Unauthorized, type FreeTrade, type FreeTradePlayer, type FreeTradeSide, type Hit } from "../../lib/api";
  import { openPane } from "../../lib/pane.svelte";
  import { route, setParams } from "../../lib/router.svelte";
  import { CALC_FOOT, refAssumes, refLabel } from "../../lib/refleague";
  import { fmt } from "../../lib/theme";
  import Card from "../Card.svelte";
  import Expander from "../Expander.svelte";
  import PosBadge from "../PosBadge.svelte";
  import ScreenHead from "../ScreenHead.svelte";
  import TeamBadge from "../TeamBadge.svelte";

  let { league, onauth }: { league: string; onauth: () => void } = $props();

  const MAX = 6;
  const ID = /^00-\d{7}$/;
  const params = $derived(route.current.params);
  const sideIds = (v: string | null) => [...new Set((v ?? "").split(",").map((x) => x.trim()).filter((x) => ID.test(x)))].slice(0, MAX);
  const give = $derived(sideIds(params.get("give")));
  const getIds = $derived(sideIds(params.get("get")));

  let answer = $state<FreeTrade | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);
  // names of players added in this visit, before the answer names them
  const names = $state<Record<string, { name: string; pos: string | null; team: string | null }>>({});

  $effect(() => {
    const l = league;
    const g = give;
    const t = getIds;
    error = null;
    if (!g.length && !t.length) {
      answer = null;
      return;
    }
    const path = freeTradePath(l, g, t);
    loading = true;
    get<FreeTrade>(path)
      .then((a) => {
        if (league !== l || path !== freeTradePath(league, give, getIds)) return;
        answer = a;
      })
      .catch((e) => {
        if (e instanceof Unauthorized) onauth();
        else error = e instanceof ApiError && e.status === 400 ? e.message : e instanceof Error ? e.message : String(e);
      })
      .finally(() => (loading = false));
  });

  function setSide(side: "give" | "get", ids: string[]) {
    setParams({ [side]: ids.length ? ids.join(",") : null });
  }
  function add(side: "give" | "get", h: Hit) {
    const cur = side === "give" ? give : getIds;
    const other = side === "give" ? getIds : give;
    if (cur.includes(h.gsis_id) || cur.length >= MAX) return;
    names[h.gsis_id] = { name: h.player_name, pos: h.position, team: h.nfl_team };
    if (other.includes(h.gsis_id)) setParams({ [side === "give" ? "get" : "give"]: other.filter((x) => x !== h.gsis_id).join(",") || null, [side]: [...cur, h.gsis_id].join(",") });
    else setSide(side, [...cur, h.gsis_id]);
  }
  function remove(side: "give" | "get", id: string) {
    setSide(side, (side === "give" ? give : getIds).filter((x) => x !== id));
  }
  function swap() {
    setParams({ give: getIds.length ? getIds.join(",") : null, get: give.length ? give.join(",") : null });
  }

  // the search per side: two letters → /api/search on this scoring (a 150 ms pause)
  let q = $state<{ give: string; get: string }>({ give: "", get: "" });
  let hits = $state<{ give: Hit[]; get: Hit[] }>({ give: [], get: [] });
  const timers: Record<string, ReturnType<typeof setTimeout> | undefined> = {};
  function onSearch(side: "give" | "get") {
    clearTimeout(timers[side]);
    const text = q[side].trim();
    if (text.length < 2) {
      hits[side] = [];
      return;
    }
    const l = league;
    timers[side] = setTimeout(() => {
      get<Hit[]>(paths.search(l, text))
        .then((h) => {
          if (q[side].trim() === text) hits[side] = h.filter((x) => ID.test(x.gsis_id)).slice(0, 8);
        })
        .catch((e) => e instanceof Unauthorized && onauth());
    }, 150);
  }
  function pickHit(side: "give" | "get", h: Hit) {
    add(side, h);
    q[side] = "";
    hits[side] = [];
  }

  const rowOf = (side: FreeTradeSide | undefined, id: string) => side?.players.find((p) => p.gsis_id === id) ?? null;
  const v0 = (v: number | null | undefined) => (v === null || v === undefined ? "—" : fmt.whole(v));
  const tone = $derived(answer?.verdict.even ? "even" : answer?.verdict.lean === "get" ? "good" : answer?.verdict.lean === "give" ? "bad" : "none");
  const maxV = $derived(Math.max(1, answer?.give.value ?? 0, answer?.get.value ?? 0));
  const shown = $derived(answer);
</script>

{#snippet player(side: "give" | "get", id: string, p: FreeTradePlayer | null)}
  {@const n = names[id]}
  <li class="flex min-h-14 items-center gap-2.5 px-3 py-2" data-testid={`ft-${side}-row`} data-id={id}>
    <span class="min-w-0 flex-1">
      <span class="block truncate text-base font-semibold">
        <a
          class="ll-name"
          href={`/player/${id}?league=${encodeURIComponent(league)}`}
          onclick={(e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            openPane(id, { from: "search", context: { name: p?.player_name ?? n?.name ?? id } });
          }}
          data-testid={`ft-${side}-name`}>{p?.player_name ?? n?.name ?? id}</a
        >
      </span>
      <span class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-ink-3">
        <PosBadge pos={p?.position ?? n?.pos} />
        {#if (p?.position ?? n?.pos) !== "DEF"}<TeamBadge team={p?.team ?? n?.team} />{/if}
        {#if p && !p.no_projection}
          <span>{p.position}{p.value_rank_pos} by value</span>
          {#if p.outlook}
            <span>·</span>
            {#if p.outlook.bye}<span>bye in week {p.outlook.week}</span>
            {:else if p.outlook.points !== null}<span data-testid="ft-outlook"
                >week {p.outlook.week}: {fmt.pts(p.outlook.points)}{#if p.outlook.p10 !== null && p.outlook.p90 !== null}&nbsp;({fmt.whole(p.outlook.p10)}–{fmt.whole(p.outlook.p90)}){/if}</span
              >{/if}
            {#if p.outlook.per_game !== null}<span>· {fmt.pts(p.outlook.per_game)} per game over the season left</span>{/if}
          {/if}
        {:else if p?.no_projection}
          <span class="text-warn">no projection: unknown, not zero</span>
        {/if}
      </span>
    </span>
    <span class="shrink-0 text-right">
      <span class="block text-lg font-bold tabnum" title="Season points above the best free player at his position">{p ? v0(p.value) : "…"}</span>
      {#if p && p.ros_points !== null && p.ros_points !== undefined}<span class="block text-xs text-ink-3 tabnum">{fmt.whole(p.ros_points)} pts</span>{/if}
    </span>
    <button type="button" class="grid h-10 w-10 shrink-0 place-items-center rounded-md text-ink-3 hover:bg-raised hover:text-ink" aria-label={`Remove ${p?.player_name ?? n?.name ?? id}`} onclick={() => remove(side, id)} data-testid={`ft-${side}-remove`}
      >×</button
    >
  </li>
{/snippet}

{#snippet sideCard(side: "give" | "get", ids: string[], title: string)}
  {@const s = side === "give" ? shown?.give : shown?.get}
  <Card {title} pad={false} testid={`ft-side-${side}`}>
    <div class="-mt-1 px-3 pb-2">
      <label class="sr-only" for={`ft-q-${side}`}>Add a player to “{title}”</label>
      <input
        id={`ft-q-${side}`}
        class="ll-input w-full py-1.5 text-sm"
        type="search"
        placeholder={ids.length >= MAX ? `Six players is the most a side takes` : "Add a player: type a name"}
        autocomplete="off"
        disabled={ids.length >= MAX}
        bind:value={q[side]}
        oninput={() => onSearch(side)}
        onkeydown={(e) => {
          if (e.key === "Enter" && hits[side][0]) pickHit(side, hits[side][0]);
        }}
        data-testid={`ft-search-${side}`}
      />
      {#if hits[side].length}
        <ul class="mt-1 max-h-72 overflow-y-auto rounded-md border border-line" data-testid={`ft-hits-${side}`}>
          {#each hits[side] as h (h.gsis_id)}
            <li>
              <button type="button" class="block min-h-11 w-full px-3 py-2 text-left text-base hover:bg-raised" onclick={() => pickHit(side, h)} data-testid={`ft-hit-${side}`}>{h.label}</button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
    {#if ids.length}
      <ul class="divide-y divide-line border-t border-line">
        {#each ids as id (id)}{@render player(side, id, rowOf(s, id))}{/each}
      </ul>
      {#if s}
        <p class="border-t border-line px-3 py-2 text-sm text-ink-2" data-testid={`ft-total-${side}`}>
          Value <strong class="text-ink tabnum">{v0(s.value)}</strong>
          {#if s.ros_points !== null}· {fmt.whole(s.ros_points)} season points{#if s.low !== null && s.high !== null}, likely {fmt.whole(s.low)}–{fmt.whole(s.high)}{/if}{/if}
        </p>
      {/if}
    {:else}
      <p class="border-t border-line px-3 py-3 text-sm text-ink-3">No player yet.</p>
    {/if}
  </Card>
{/snippet}

<main class="space-y-4" data-testid="free-trade">
  <ScreenHead eyebrow="Trades" title="Trade calculator">
    {#snippet answer()}
      Any two sides, in {refLabel(league)}: what each side is worth over the rest of the regular season, and whether the gap is bigger than the
      uncertainty.
    {/snippet}
  </ScreenHead>

  <Card tone={shown && tone !== "none" ? "accent" : "plain"} testid="ft-verdict">
    {#if error}
      <p class="text-bad" data-testid="ft-error">{error}</p>
    {:else if !shown}
      <p class="text-base text-ink-2" data-testid="ft-empty">Add a player to each side to compare them. Values are {refAssumes(league).replace(/^Value/, "for")}.</p>
    {:else}
      <p class="text-lg leading-snug font-bold {tone === 'good' ? 'text-good' : tone === 'bad' ? 'text-bad' : ''}" data-testid="ft-words" aria-live="polite">
        {shown.verdict.words}{#if loading}<span class="sr-only"> (updating)</span>{/if}
      </p>
      {#if shown.verdict.one_player}<p class="mt-1 text-sm text-ink-2" data-testid="ft-one">{shown.verdict.one_player.words}</p>{/if}
      {#if shown.give.value !== null && shown.get.value !== null}
        <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="ft-bars">
          {#each [{ k: "You give", s: shown.give }, { k: "You get", s: shown.get }] as x (x.k)}
            <div>
              <div class="flex items-baseline justify-between text-sm"><span class="ll-label text-ink-3">{x.k}</span><span class="font-bold tabnum">{v0(x.s.value)}</span></div>
              <div class="mt-1 h-2 rounded-full bg-sunken"><div class="h-2 rounded-full bg-accent" style={`width:${Math.round((100 * (x.s.value ?? 0)) / maxV)}%`}></div></div>
            </div>
          {/each}
        </div>
      {/if}
      {#if shown.roster_spots}<p class="mt-3 text-sm text-ink-2" data-testid="ft-spots">{shown.roster_spots.words}</p>{/if}
    {/if}
    <p class="mt-3 text-sm text-ink-3" data-testid="ft-assumes">{refAssumes(league)}. <a class="ll-link" href="/leagues" data-testid="ft-open">{CALC_FOOT}</a></p>
    <!-- ---- IQ-4: what we know about the rest of season (the values are rest-of-season points) -->
    {#if shown?.ros_grade}<p class="mt-2 text-sm text-ink-3" data-testid="ft-ros-grade">{shown.ros_grade.words}{shown.ros_grade.kd_words ? ` ${shown.ros_grade.kd_words}` : ""}</p>{/if}
    <!-- ---- end IQ-4 -->
  </Card>

  <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
    {@render sideCard("give", give, "You give")}
    {@render sideCard("get", getIds, "You get")}
  </div>
  {#if give.length || getIds.length}
    <div class="flex justify-center"><button type="button" class="min-h-10 rounded-md border border-line px-4 text-sm font-semibold" onclick={swap} data-testid="ft-swap">Swap sides</button></div>
  {/if}

  {#if shown}
    <Expander title="How this is priced" testid="ft-how">
      <div class="space-y-2 text-sm text-ink-2">
        <p data-testid="ft-pricing">{shown.pricing.words}</p>
        {#if shown.value_words}<p>{shown.value_words}</p>{/if}
        <p>
          The likely range is the middle 80% of the season points each side could score (each player's weeks read as independent): “about even” means the
          gap's range holds zero, or the two sides are within 10 points or 10%. A value is this season only: no draft picks, no keeper costs, no seasons after
          this one.
        </p>
      </div>
    </Expander>
  {/if}
</main>
