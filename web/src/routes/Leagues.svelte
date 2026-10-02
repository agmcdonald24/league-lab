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

<main class="space-y-5 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-10" data-testid="leagues">
  <header class="space-y-1">
    {#if current}
      <a href={withContext("/", { league: current, team: prefs.team(current) })} class="ll-link inline-block py-1 text-[15px]" data-testid="to-week"
        >‹ My week</a
      >
    {/if}
    <h1 class="text-2xl font-bold">League Lab</h1>
    <p class="text-[15px] leading-snug text-zinc-600 dark:text-zinc-300">
      Who to start this week and what each player is worth, in your Sleeper league's scoring.
    </p>
  </header>

  <form class="space-y-2" onsubmit={submit} data-testid="username-form">
    <label class="block text-[15px] font-semibold" for="ll-username">Your Sleeper username</label>
    <div class="flex gap-2">
      <input
        id="ll-username"
        class="min-w-0 flex-1 rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-base dark:border-zinc-700 dark:bg-zinc-900"
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
        class="shrink-0 rounded-xl bg-green-700 px-4 py-2.5 font-semibold text-white disabled:opacity-60"
        disabled={busy || !username.trim()}
        data-testid="username-go">{busy ? "Looking…" : "Find my leagues"}</button
      >
    </div>
    <p class="text-[13px] leading-snug text-zinc-500 dark:text-zinc-400">
      No password to Sleeper: League Lab only reads what Sleeper shows anyone (your leagues, rosters and scoring).
    </p>
    {#if error}<p class="text-[15px] text-red-700 dark:text-red-400" data-testid="username-error">{error}</p>{/if}
  </form>

  {#if mine}
    <section class="space-y-2" data-testid="league-list">
      <div class="flex items-baseline justify-between gap-2">
        <h2 class="text-[15px] font-semibold">
          {mine.user.display_name || mine.user.username}'s leagues, {mine.season}
        </h2>
        <button type="button" class="text-[13px] text-green-700 underline dark:text-green-400" onclick={notMe} data-testid="not-me">Not you?</button>
      </div>
      {#if mine.leagues.length === 0}
        <p class="rounded-2xl bg-zinc-100 p-4 text-[15px] dark:bg-zinc-900" data-testid="no-leagues">
          {mine.user.username} has no Sleeper football leagues this season. A league you join shows up here.
        </p>
      {/if}
      <ul class="space-y-2">
        {#each mine.leagues as l (l.league_id)}
          <li>
            <a
              href={href(l.league_id, l.roster_id)}
              class="block rounded-2xl border p-4 {l.league_id === current
                ? 'border-green-700 ring-1 ring-green-700 dark:border-green-500 dark:ring-green-500'
                : 'border-zinc-200 dark:border-zinc-800'}"
              data-testid="league-row"
              data-league={l.league_id}
            >
              <div class="text-[16px] leading-snug font-semibold">{l.name}</div>
              {#if leagueLine(l)}<div class="text-[13px] leading-snug text-zinc-500 dark:text-zinc-400">{leagueLine(l)}</div>{/if}
              <div class="mt-1 text-[14px] leading-snug">
                {#if l.roster_id !== null}
                  Your team: <strong>{l.team_name ?? `team ${l.roster_id}`}</strong>
                {:else}
                  <span class="text-amber-800 dark:text-amber-300">You have no team in this league: pick the team to see after you open it.</span>
                {/if}
              </div>
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</main>
