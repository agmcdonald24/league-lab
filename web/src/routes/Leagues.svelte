<script lang="ts">
  // Sign in with a Sleeper username → the league picker (plan F2). One field; the answer is the user's leagues this
  // season, each a real link to its My Week with the user's own team pre-selected. Remembered on this phone.
  import { ApiError, get, paths, Unauthorized, type UserLeagues } from "../lib/api";
  import { leagueLine } from "../lib/leagues";
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
