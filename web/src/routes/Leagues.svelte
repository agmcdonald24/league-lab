<script lang="ts">
  // Sign in with a Sleeper username → the league picker (plan F2). One field; the answer is the user's leagues this
  // season, each a real link to its My Week with the user's own team pre-selected. Remembered on this phone.
  import { ApiError, get, paths, Unauthorized, type UserLeagues } from "../lib/api";
  import { isMflSearch, leagueLine, mflPath, mflSearchPath, type MflLeague, type MflSearch } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { prefs } from "../lib/prefs";

  let {
    mine,
    current,
    onuser,
    onauth,
  }: { mine: UserLeagues | null; current: string | null; onuser: (v: UserLeagues | null) => void; onauth: () => void } = $props();

  let username = $state(prefs.user() ?? "");
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    const u = username.trim();
    if (!u) return;
    busy = true;
    error = null;
    try {
      const v = await get<UserLeagues>(paths.userLeagues(u));
      prefs.setUser(u);
      prefs.setUserLeagues(v);
      onuser(v);
    } catch (err) {
      if (err instanceof Unauthorized) onauth();
      else if (err instanceof ApiError && err.status === 404) error = `Sleeper has no user called “${u}”. Check the spelling: it is the name you sign in to Sleeper with.`;
      else if (err instanceof ApiError && err.status === 502) error = "Sleeper did not answer. Try again in a minute.";
      else error = `Cannot reach League Lab right now (${err instanceof Error ? err.message : String(err)}). Try again in a minute.`;
    } finally {
      busy = false;
    }
  }

  function notMe() {
    prefs.forgetUser();
    username = "";
    onuser(null);
  }

  const href = (id: string, roster: number | null) => `/?league=${encodeURIComponent(id)}${roster !== null ? `&team=${roster}` : ""}`;

  // ---- I0-B (Wave I-0): MyFantasyLeague — paste the league link, pick the team, the same My Week
  let mflText = $state("");
  let mflBusy = $state(false);
  let mflError = $state<string | null>(null);
  let mfl = $state<MflLeague | null>(null);
  let mflFound = $state<MflSearch | null>(null); // I0-C: the leagues a name matched (the box takes a link, an id or a name)
  let mflOpening = $state<string | null>(null);
  const mflSaved = $state(prefs.mflLeagues());

  async function findMfl(e: SubmitEvent) {
    e.preventDefault();
    const t = mflText.trim();
    if (!t) return;
    mflBusy = true;
    mflError = null;
    mfl = null;
    mflFound = null;
    try {
      const v = await get<MflLeague | MflSearch>(mflSearchPath(t));
      if (isMflSearch(v)) mflFound = v;
      else mfl = v;
    } catch (err) {
      mflFail(err);
    } finally {
      mflBusy = false;
    }
  }

  // I0-C: a league picked from the matches → its card and the team picker (the same as a pasted link)
  async function openMfl(leagueId: string) {
    mflOpening = leagueId;
    mflError = null;
    try {
      mfl = await get<MflLeague>(mflPath(leagueId));
    } catch (err) {
      mflFail(err);
    } finally {
      mflOpening = null;
    }
  }

  function mflFail(err: unknown) {
    if (err instanceof Unauthorized) onauth();
    else if (err instanceof ApiError && err.status === 404) mflError = `${err.message}.`;
    else if (err instanceof ApiError && err.status === 502) mflError = "MyFantasyLeague did not answer. Try again in a minute.";
    else if (err instanceof ApiError && err.status === 503) mflError = "League Lab is busy reading MyFantasyLeague. Try again in a minute.";
    else mflError = `Cannot reach League Lab right now (${err instanceof Error ? err.message : String(err)}). Try again in a minute.`;
  }

  function pickMfl(v: MflLeague, rosterId: number) {
    const team = v.teams.find((t) => t.roster_id === rosterId);
    prefs.rememberMfl({ league_id: v.league.league_id, name: v.league.name, scoring_label: v.league.scoring_label,
      total_rosters: v.league.total_rosters, roster_id: rosterId, team_name: team?.team_name ?? null });
  }
  // ---- end I0-B
</script>

<main class="mx-auto max-w-xl space-y-5 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-10" data-testid="leagues">
  <header class="space-y-1">
    {#if current}
      <a href={withContext("/", { league: current, team: prefs.team(current) })} class="ll-link inline-block py-1 text-base" data-testid="to-week"
        >‹ My week</a
      >
    {/if}
    <h1 class="flex items-center gap-2 text-3xl font-extrabold tracking-tight">
      <span class="grid h-9 w-9 place-items-center rounded-sm bg-accent text-sm font-black text-on-accent">LL</span>League Lab
    </h1>
    <p class="text-base leading-snug text-ink-2">
      Who to start this week and what each player is worth, in your Sleeper league's scoring.
    </p>
  </header>

  <form class="space-y-2" onsubmit={submit} data-testid="username-form">
    <label class="ll-label block" for="ll-username">Your Sleeper username</label>
    <div class="flex gap-2">
      <input
        id="ll-username"
        class="ll-input flex-1 py-2.5"
        type="text"
        autocomplete="username"
        autocapitalize="none"
        autocorrect="off"
        spellcheck="false"
        placeholder="e.g. the name on your Sleeper profile"
        bind:value={username}
        data-testid="username"
      />
      <button
        class="shrink-0 rounded-md bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60"
        disabled={busy || !username.trim()}
        data-testid="username-go">{busy ? "Looking…" : "Find my leagues"}</button
      >
    </div>
    <p class="text-sm leading-snug text-ink-3">
      No password to Sleeper: League Lab only reads what Sleeper shows anyone (your leagues, rosters and scoring).
    </p>
    {#if error}<p class="text-base text-bad" data-testid="username-error">{error}</p>{/if}
  </form>

  <!-- I0-B: MyFantasyLeague -->
  <form class="space-y-2" onsubmit={findMfl} data-testid="mfl-form">
    <label class="ll-label block" for="ll-mfl">On MyFantasyLeague? Find your league</label>
    <div class="flex gap-2">
      <input
        id="ll-mfl"
        class="ll-input min-w-0 flex-1 py-2.5"
        type="text"
        enterkeyhint="search"
        autocapitalize="none"
        autocorrect="off"
        spellcheck="false"
        placeholder="Your league link or name"
        bind:value={mflText}
        data-testid="mfl-link"
      />
      <button
        class="shrink-0 rounded-md bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60"
        disabled={mflBusy || !mflText.trim()}
        data-testid="mfl-go">{mflBusy ? "Looking…" : "Find my league"}</button
      >
    </div>
    <p class="text-sm leading-snug text-ink-3" data-testid="mfl-help">
      Paste your league link, or type your league's name as it appears in the MFL app. League Lab only reads what the league shares.
    </p>
    {#if mflError}<p class="text-base text-bad" data-testid="mfl-error">{mflError}</p>{/if}
  </form>

  {#if mfl}
    {@const v = mfl}
    <section class="space-y-2 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid="mfl-card">
      {#if mflFound?.matches.length}
        <button type="button" class="py-1 text-sm text-accent underline" onclick={() => (mfl = null)} data-testid="mfl-back"
          >‹ Not this league</button
        >
      {/if}
      <div>
        <div class="text-lg leading-snug font-bold">{v.league.name} <span class="text-sm font-semibold text-ink-3">MFL</span></div>
        {#if leagueLine(v.league)}<div class="text-sm leading-snug text-ink-3">{leagueLine(v.league)}</div>{/if}
      </div>
      <p class="text-sm leading-snug text-ink-2" data-testid="mfl-note">{v.scoring_note}</p>
      {#if v.unmapped.length}
        <p class="text-sm leading-snug text-warn" data-testid="mfl-unmapped">
          {v.unmapped.length} of {v.players} players have no projection here yet: {v.unmapped.map((u) => u.name ?? u.mfl_id).join(", ")}.
        </p>
      {/if}
      <h2 class="ll-label pt-1">Which team is yours?</h2>
      <ul class="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {#each v.teams as t (t.roster_id)}
          <li>
            <a
              href={href(v.league.league_id, t.roster_id)}
              onclick={() => pickMfl(v, t.roster_id)}
              class="block rounded-md border px-3 py-2.5 text-base {t.roster_id === v.roster_id ? 'border-accent font-bold ring-1 ring-accent' : 'border-line'}"
              data-testid="mfl-team"
              data-roster={t.roster_id}>{t.team_name}</a
            >
          </li>
        {/each}
      </ul>
    </section>
  {:else if mflFound}
    <!-- I0-C: the leagues the name matched; tapping one loads its card and the team picker -->
    <section class="space-y-2" data-testid="mfl-matches">
      <p class="text-sm leading-snug text-ink-2" data-testid="mfl-search-note">{mflFound.note}</p>
      {#if mflFound.matches.length}
        <ul class="space-y-2">
          {#each mflFound.matches as m (m.league_id)}
            <li>
              <button
                type="button"
                class="block w-full rounded-lg border border-line bg-surface p-4 text-left disabled:opacity-60"
                style="box-shadow:var(--ll-shadow)"
                disabled={mflOpening !== null}
                onclick={() => openMfl(m.league_id)}
                data-testid="mfl-match"
                data-league={m.league_id}
              >
                <div class="text-lg leading-snug font-bold break-words">{m.name}</div>
                <div class="text-sm leading-snug text-ink-3">{mflOpening === m.league_id ? "Opening…" : `MFL · ${m.year}`}</div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {:else if mflSaved.length}
    <ul class="space-y-2" data-testid="mfl-saved">
      {#each mflSaved as l (l.league_id)}
        <li>
          <a
            href={href(l.league_id, l.roster_id)}
            class="relative block overflow-hidden rounded-lg border bg-surface p-4 pl-5 {l.league_id === current ? 'border-accent ring-1 ring-accent' : 'border-line'}"
            style="box-shadow:var(--ll-shadow)"
            data-testid="league-row"
            data-league={l.league_id}
          >
            <span class="absolute inset-y-0 left-0 w-1 {l.league_id === current ? 'bg-accent' : 'bg-line-strong'}" aria-hidden="true"></span>
            <div class="text-lg leading-snug font-bold">{l.name} <span class="text-sm font-semibold text-ink-3">MFL</span></div>
            {#if leagueLine(l)}<div class="text-sm leading-snug text-ink-3">{leagueLine(l)}</div>{/if}
            {#if l.team_name}<div class="mt-1 text-sm leading-snug text-ink-2">Your team: <strong>{l.team_name}</strong></div>{/if}
          </a>
        </li>
      {/each}
    </ul>
  {/if}

  {#if mine}
    <section class="space-y-2" data-testid="league-list">
      <div class="flex items-baseline justify-between gap-2">
        <h2 class="ll-label">
          {mine.user.display_name || mine.user.username}'s leagues, {mine.season}
        </h2>
        <button type="button" class="text-sm text-accent underline" onclick={notMe} data-testid="not-me">Not you?</button>
      </div>
      {#if mine.leagues.length === 0}
        <p class="rounded-lg bg-raised p-4 text-base" data-testid="no-leagues">
          {mine.user.username} has no Sleeper football leagues this season. A league you join shows up here.
        </p>
      {/if}
      <ul class="space-y-2">
        {#each mine.leagues as l (l.league_id)}
          <li>
            <a
              href={href(l.league_id, l.roster_id)}
              class="relative block overflow-hidden rounded-lg border bg-surface p-4 pl-5 {l.league_id === current ? 'border-accent ring-1 ring-accent' : 'border-line'}"
              style="box-shadow:var(--ll-shadow)"
              data-testid="league-row"
              data-league={l.league_id}
            >
              <span class="absolute inset-y-0 left-0 w-1 {l.league_id === current ? 'bg-accent' : 'bg-line-strong'}" aria-hidden="true"></span>
              <div class="text-lg leading-snug font-bold">{l.name}</div>
              {#if leagueLine(l)}<div class="text-sm leading-snug text-ink-3">{leagueLine(l)}</div>{/if}
              <div class="mt-1 text-sm leading-snug text-ink-2">
                {#if l.roster_id !== null}
                  Your team: <strong>{l.team_name ?? `team ${l.roster_id}`}</strong>
                {:else}
                  <span class="text-warn">You have no team in this league: pick the team to see after you open it.</span>
                {/if}
              </div>
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</main>
