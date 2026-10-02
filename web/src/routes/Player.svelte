<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type Hit, type PlayerCard, type Section, type SectionKey } from "../lib/api";
  import { plain, withContext } from "../lib/md";
  import { learnLeagueName } from "../lib/names.svelte";
  import { back, navigate, restoreScroll, route } from "../lib/router.svelte";
  import { fmt, teamLabel } from "../lib/theme";
  import Expander from "../components/Expander.svelte";
  import GameLog from "../components/GameLog.svelte";
  import Md from "../components/Md.svelte";
  import PlayerCardView from "../components/PlayerCard.svelte";
  import SectionBox from "../components/Section.svelte";

  let { gsis, league, team, onauth }: { gsis: string; league: string | null; team: number | null; onauth: () => void } = $props();

  let data = $state<PlayerCard | null>(null);
  let error = $state<string | null>(null);
  let q = $state("");
  let hits = $state<Hit[]>([]);
  let searched = $state("");

  const ctx = $derived({ league, team });
  const home = $derived(withContext("/", ctx));
  // The card's answer first: this week's projection and where he sits in the lineup, then the rest.
  const order: SectionKey[] = ["projection", "value", "availability", "usage", "signals"];
  const NAMES: Record<string, string> = { usage: "Usage", projection: "Projection", availability: "Availability", value: "Value", signals: "Signals" };
  const RANKED = ["QB", "RB", "WR", "TE", "K", "DEF"];

  // The Projection section plus the rest-of-season line: the API's sentence (app/lib/ros.py card_line) is in the
  // section today; `ros.line` is added when the API sends it separately and the section does not already have it.
  // Then a link to the rest-of-season list at his position.
  function projection(d: PlayerCard): Section | undefined {
    const sec = d.sections.projection;
    if (!sec) return sec;
    const blocks = [...sec.blocks];
    const has = blocks.some((b) => (b.text ?? "").startsWith("Rest of season"));
    if (!has && d.ros?.line) blocks.push({ kind: "markdown", text: d.ros.line });
    if ((has || d.ros) && RANKED.includes(d.position))
      blocks.push({ kind: "caption", text: `[Every ${d.position} for the rest of the season](/ros?position=${d.position})` });
    return { ...sec, blocks };
  }
  const sections = $derived(
    data ? order.map((k) => ({ key: k, sec: k === "projection" ? projection(data!) : data!.sections[k] })).filter((x) => !!x.sec) : [],
  );
  // the header line without the position and team the badges already show ("WR · DET · WR1 on the depth chart …")
  const headLine = $derived.by(() => {
    if (!data) return "";
    const parts = plain(data.header).split(" · ");
    const drop = new Set([data.position, data.team ?? "", teamLabel(data.team) ?? ""]);
    while (parts.length && drop.has(parts[0])) parts.shift();
    return parts.join(" · ");
  });
  const missing = $derived((data?.missing ?? []).filter((k) => !data?.sections[k as SectionKey]).map((k) => NAMES[k] ?? k));

  $effect(() => {
    const id = gsis;
    const l = league;
    const t = team;
    error = null;
    if (!l) return;
    const path = paths.player(id, l, t);
    const hit = peek<PlayerCard>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<PlayerCard>(path)
      .then((d) => {
        if (gsis !== id || league !== l) return;
        data = d;
        learnLeagueName(d.league_id, d.league_name);
        restoreScroll();
      })
      .catch((e) => {
        if (gsis !== id) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = `No player with id ${id}. Search for him above.`;
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });

  let timer: ReturnType<typeof setTimeout> | undefined;
  function onInput() {
    clearTimeout(timer);
    const text = q.trim();
    if (text.length < 2 || !league) {
      hits = [];
      searched = "";
      return;
    }
    const l = league;
    timer = setTimeout(() => {
      get<Hit[]>(paths.search(l, text))
        .then((h) => {
          if (q.trim() !== text) return;
          hits = h;
          searched = text;
        })
        .catch((e) => e instanceof Unauthorized && onauth());
    }, 150);
  }

  function pick(id: string) {
    q = "";
    hits = [];
    searched = "";
    navigate(withContext(`/player/${id}`, ctx));
  }
</script>

<header class="border-b border-line bg-surface pt-[env(safe-area-inset-top)]">
<div class="relative mx-auto flex max-w-6xl items-center gap-2 px-4 py-2">
  <button
    type="button"
    class="flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 text-base font-semibold text-accent"
    onclick={() => back(home)}
    data-testid="back"
  >
    <span aria-hidden="true" class="text-xl leading-none">‹</span>{route.current.depth > 0 ? "Back" : "My week"}
  </button>
  <label class="sr-only" for="ll-search">Find a player</label>
  <input
    id="ll-search"
    class="ll-input flex-1"
    type="search"
    placeholder="Find another player"
    autocomplete="off"
    bind:value={q}
    oninput={onInput}
    data-testid="search"
  />
  {#if searched}
    <ul
      class="absolute top-full right-4 left-4 z-30 max-h-[60vh] overflow-y-auto rounded-lg border border-line bg-surface shadow-lg"
      data-testid="search-results"
    >
      {#if hits.length === 0}
        <li class="p-3 text-sm text-ink-3">No QB, RB, WR, TE or K named like “{searched}” in this season's pool.</li>
      {/if}
      {#each hits as h (h.gsis_id)}
        <li>
          <a
            class="block min-h-11 px-3 py-2.5 text-base hover:bg-raised"
            href={withContext(`/player/${h.gsis_id}`, ctx)}
            onclick={(e) => {
              e.preventDefault();
              pick(h.gsis_id);
            }}>{h.label}</a
          >
        </li>
      {/each}
    </ul>
  {/if}
</div>
</header>

<main class="mx-auto max-w-6xl space-y-3 px-4 pt-4 pb-10" data-testid="player">
  {#if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-32"></div>
      {#each [0, 1, 2] as i (i)}<div class="ll-skel h-28"></div>{/each}
    </div>
  {:else}
    <h1 class="sr-only" data-testid="player-name">{data.player_name}</h1>
    <PlayerCardView
      player={{ gsis_id: data.gsis_id, player_name: data.player_name, position: data.position, team: data.team, headshot_url: data.headshot_url ?? null }}
      number={fmt.pts(data.proj_points)}
      numberLabel={data.week ? `Week ${data.week}` : "Projection"}
      line={headLine}
      context={data.injury_status ?? null}
      testid="player-header"
    />
    <div class="grid grid-cols-1 gap-3 wide:grid-cols-2 wide:items-start">
      <div class="space-y-3">
        {#each sections.slice(0, 1) as x (x.key)}
          <SectionBox section={x.sec!} {ctx} testid={`section-${x.key}`} />
        {/each}
        {#if league}<GameLog gsis={data.gsis_id} {league} season={data.season} {onauth} leagueName={data.league_name} />{/if}
      </div>
      <div class="space-y-3">
        {#each sections.slice(1) as x (x.key)}
          <SectionBox section={x.sec!} {ctx} testid={`section-${x.key}`} />
        {/each}
      </div>
    </div>
    {#if missing.length}
      <p class="text-sm leading-snug text-ink-3" data-testid="missing">
        Not shown for {data.league_name} yet: {missing.join(", ")}.
      </p>
    {/if}
    <Expander title="How to read this" testid="howto"><Md text={data.howto} {ctx} block class="text-base leading-snug" /></Expander>
  {/if}
</main>
