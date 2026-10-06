<script lang="ts">
  import { APP_MARK, APP_NAME } from "../lib/brand";
  // Sign in with a Sleeper username → the league picker (plan F2). One field; the answer is the user's leagues this
  // season, each a real link to its My Week with the user's own team pre-selected. Remembered on this phone.
  import { ApiError, get, paths, Unauthorized, type UserLeagues } from "../lib/api";
  import { isMflSearch, leagueLine, mflPath, mflSearchPath, type MflLeague, type MflSearch } from "../lib/leagues";
  import { bigMisses, checkLine, missLine, type LeagueCard, type ScoringCheck, type WithCard } from "../lib/leagues"; // ---- IC-3
  import { withContext } from "../lib/md";
  import { prefs } from "../lib/prefs";
  // ---- II-5 (Wave I-I): one setup flow — platform → league → team → My Week (lib/providers.ts)
  import { route, setParams } from "../lib/router.svelte";
  // IK-3: isMfl no longer needed here (providerShort says the platform by any prefix)
  import type { Roster } from "../lib/api";
  import { looksLikeSleeperLeague, providersPath, setupError, setupGet, sleeperLeaguePath, type FeatureKey, type Platform, type Providers, type SleeperLeague } from "../lib/providers";
  // ---- IK-3 (Wave I-K): ESPN and Yahoo in the same flow
  import { espnConnectPath, espnLeaguePath, isPlatform, PLATFORMS, providerShort, setupPost, yahooConnectPath, yahooDisconnectPath, yahooLeaguePath, yahooMePath, type ProviderLeague, type YahooMe } from "../lib/providers";
  // ---- IM-3 (Wave I-M)'s front door (browse without a league, the record's line) moved to Home in IN-1 (routes/Home.svelte)
  import { tick } from "svelte";

  let {
    mine,
    current,
    onuser,
    onauth,
  }: { mine: UserLeagues | null; current: string | null; onuser: (v: UserLeagues | null) => void; onauth: () => void } = $props();

  // ---- IN-1 (Wave I-N): after a search, the results are put in view and take the focus (a screen reader hears them; a
  // keyboard continues from them). The phone stacks them under the field; the desktop has them beside it.
  let resultsEl = $state<HTMLElement | null>(null);
  async function reveal() {
    await tick();
    const el = resultsEl;
    if (!el) return;
    const top = el.getBoundingClientRect().top;
    // beside the form (desktop) they are usually in view already; under it (a phone) they scroll to the top
    if (top < 0 || top > window.innerHeight * 0.35) el.scrollIntoView({ block: "start", behavior: "auto" });
    el.focus({ preventScroll: true });
  }
  // ---- end IN-1
  let username = $state(prefs.user() ?? "");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let errorCode = $state<string | null>(null); // ---- II-5: the API's key (INTERFACES.md § II-5)
  let errorFix = $state<string | null>(null); // ---- II-5: what to do next

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    const u = username.trim();
    if (!u) return;
    busy = true;
    error = errorCode = errorFix = null;
    sleeperLeague = null; // ---- II-5
    try {
      // ---- II-5: a league link or id in the same box → that league's card and team picker (no username needed)
      if (looksLikeSleeperLeague(u)) {
        sleeperLeague = await setupGet<SleeperLeague>(sleeperLeaguePath(u));
        void reveal(); // ---- IN-1
        return;
      }
      const v = await setupGet<UserLeagues>(paths.userLeagues(u)); // II-5: keeps the error's key (was get)
      prefs.setUser(u);
      prefs.setUserLeagues(v);
      onuser(v);
      void reveal(); // ---- IN-1
    } catch (err) {
      const se = setupError(err); // ---- II-5: the API's specific words when it sends them
      if (err instanceof Unauthorized) onauth();
      else if (se && err instanceof ApiError && err.status === 404) [error, errorCode, errorFix] = [se.words, se.code, se.fix];
      else if (err instanceof ApiError && err.status === 404) error = `Sleeper has no user called “${u}”. Check the spelling: it is the name you sign in to Sleeper with.`;
      else if (err instanceof ApiError && err.status === 502) error = "Sleeper did not answer. Try again in a minute.";
      else error = `Cannot reach ${APP_NAME} right now (${err instanceof Error ? err.message : String(err)}). Try again in a minute.`;
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
  let mflErrorCode = $state<string | null>(null); // ---- II-5
  let mflErrorFix = $state<string | null>(null); // ---- II-5
  let mfl = $state<MflLeague | null>(null);
  let mflFound = $state<MflSearch | null>(null); // I0-C: the leagues a name matched (the box takes a link, an id or a name)
  let mflOpening = $state<string | null>(null);
  const mflSaved = $state(prefs.mflLeagues());

  async function findMfl(e: SubmitEvent) {
    e.preventDefault();
    const t = mflText.trim();
    if (!t) return;
    mflBusy = true;
    mflError = mflErrorCode = mflErrorFix = null; // II-5
    mfl = null;
    mflFound = null;
    try {
      const v = await setupGet<MflLeague | MflSearch>(mflSearchPath(t)); // II-5: keeps the error's key (was get)
      if (isMflSearch(v)) mflFound = v;
      else mfl = v;
      void reveal(); // ---- IN-1
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
      mfl = await setupGet<MflLeague>(mflPath(leagueId)); // II-5: keeps the error's key (was get)
    } catch (err) {
      mflFail(err);
    } finally {
      mflOpening = null;
    }
  }

  function mflFail(err: unknown) {
    const se = setupError(err); // ---- II-5: the API's specific words and the fix
    mflErrorCode = se?.code ?? null;
    mflErrorFix = se?.fix ?? null;
    if (err instanceof Unauthorized) onauth();
    else if (se && err instanceof ApiError && err.status === 404) mflError = se.words;
    else if (err instanceof ApiError && err.status === 404) mflError = `${err.message}.`;
    else if (err instanceof ApiError && err.status === 502) mflError = "MyFantasyLeague did not answer. Try again in a minute.";
    else if (err instanceof ApiError && err.status === 503) mflError = `${APP_NAME} is busy reading MyFantasyLeague. Try again in a minute.`;
    else mflError = `Cannot reach ${APP_NAME} right now (${err instanceof Error ? err.message : String(err)}). Try again in a minute.`;
  }

  function pickMfl(v: MflLeague, rosterId: number) {
    const team = v.teams.find((t) => t.roster_id === rosterId);
    prefs.rememberMfl({ league_id: v.league.league_id, name: v.league.name, scoring_label: v.league.scoring_label,
      total_rosters: v.league.total_rosters, roster_id: rosterId, team_name: team?.team_name ?? null });
  }
  // ---- end I0-B

  // ---- II-5 (Wave I-I): one setup flow (review § 9). One **Fantasy platform** choice (Sleeper / MyFantasyLeague;
  // `?platform=` and remembered on this device) → the identifier (Sleeper: a username or a league link; MFL: a link, an
  // id or the name) → the league → the team (pre-selected when the username owns one, a picker otherwise) → My Week.
  // Specific errors with the fix (the API's `code` / `fix`); what the platform gives (GET /api/providers); no account.
  const urlPlatform = route.current.params.get("platform");
  let platform = $state<Platform>(
    isPlatform(urlPlatform) ? urlPlatform : (prefs.platform() ?? (prefs.mflLeagues().length && !prefs.userLeagues() ? "mfl" : "sleeper")), // IK-3: isPlatform
  );
  if (isPlatform(urlPlatform)) prefs.setPlatform(urlPlatform); // a shared ?platform= link (IK-3: ESPN / Yahoo too; Yahoo's sign-in comes back here)
  let sleeperLeague = $state<SleeperLeague | null>(null);
  let caps = $state<Providers | null>(null);
  // ---- IK-3: the ESPN / Yahoo league found (declared before the steps read it; the rest of IK-3's state is below)
  let provLeague = $state<ProviderLeague | null>(null);
  let provError = $state<string | null>(null);
  let provErrorCode = $state<string | null>(null);
  let provErrorFix = $state<string | null>(null);
  const FEATURES: FeatureKey[] = ["scoring", "roster_slots", "matchups", "players", "waivers", "transactions", "team_assets", "news"];
  const STATUS_WORDS = { yes: "Yes", partial: "Partly", no: "Not yet" } as const;
  const STEPS = [
    { key: "platform", label: "Platform" },
    { key: "league", label: "League" },
    { key: "team", label: "Team" },
    { key: "week", label: "My Week" },
  ] as const;
  const step = $derived(mfl || sleeperLeague || provLeague ? "team" : "league"); // IK-3: provLeague
  const stepIndex = $derived(STEPS.findIndex((s) => s.key === step));

  function choose(p: Platform) {
    platform = p;
    prefs.setPlatform(p);
    if (route.current.name === "leagues") setParams({ platform: p });
    error = errorCode = errorFix = null;
    mflError = mflErrorCode = mflErrorFix = null;
    sleeperLeague = null;
    provLeague = null; // ---- IK-3
    provError = provErrorCode = provErrorFix = null;
    if (p === "yahoo") void loadYahooMe();
  }

  $effect(() => {
    get<Providers>(providersPath)
      .then((v) => (caps = v))
      .catch(() => {}); // the "what works" lines are a nicety: the flow never waits on them
  });

  // a league the username has no team in (a commissioner's, a league they left): pick the team to see, here
  let teamsOf = $state<Record<string, Roster[] | "loading" | "failed">>({});
  async function loadTeams(id: string) {
    if (teamsOf[id] && teamsOf[id] !== "failed") return;
    teamsOf[id] = "loading";
    try {
      teamsOf[id] = await get<Roster[]>(paths.rosters(id));
    } catch (err) {
      if (err instanceof Unauthorized) onauth();
      teamsOf[id] = "failed";
    }
  }

  // a Sleeper league opened by its link is remembered like an MFL one (the switcher and the list below show it)
  function pickSleeper(v: SleeperLeague, rosterId: number) {
    const team = v.teams.find((t) => t.roster_id === rosterId);
    prefs.rememberMfl({ league_id: v.league.league_id, name: v.league.name, scoring_label: v.league.scoring_label,
      total_rosters: v.league.total_rosters, roster_id: rosterId, team_name: team?.team_name ?? null });
  }
  $effect(() => {
    if (sleeperLeague?.card) void loadCheck(sleeperLeague.league.league_id, sleeperLeague.card.check_path);
  });
  // ---- end II-5

  // ---- IK-3 (Wave I-K): ESPN — a league id or link → the league → which team is yours (the MFL card's shape); a private
  // league says so, and offers "Private league?" (the user's own ESPN cookies, IK-1's form) only when the server's switch
  // is on (`/api/providers.espn_private`). Yahoo — "Connect with Yahoo" (IK-2's sign-in, back to ?platform=yahoo) → the
  // user's Yahoo leagues with their team → My Week; a league link works too; "coming soon" until the server has Yahoo's
  // keys (`yahoo_configured`). Every league opened is remembered on this device like an MFL one (prefs.rememberLeague).
  let espnText = $state("");
  let yahooText = $state("");
  let provBusy = $state(false);
  let privateForm = $state(false); // the API said this ESPN league is private and the server reads private leagues
  let espnS2 = $state("");
  let espnSwid = $state("");
  let espnSaved = $state<string | null>(null);
  let yahooMe = $state<YahooMe | null>(null);
  let yahooMeState = $state<"idle" | "loading" | "failed">("idle");
  // IK-2's callback comes back with ?yahoo_error=denied | state | refused | down when the sign-in did not complete
  const YAHOO_ERRORS: Record<string, string> = {
    denied: "Yahoo sign-in was cancelled: nothing was connected.",
    state: "That Yahoo sign-in took too long or started in another browser. Try Connect with Yahoo again.",
    refused: "Yahoo did not accept the sign-in. Try Connect with Yahoo again.",
    down: "Yahoo did not answer. Try again in a minute.",
  };
  // PO 2026-10-05: Yahoo approves every app's fantasy access itself; until it has, the sign-in works and the data does not
  const YAHOO_PENDING =
    "Yahoo leagues are coming soon: Yahoo has not switched on this app's access to fantasy data yet. Nothing is wrong with your league or your Yahoo sign-in. Sleeper and MyFantasyLeague leagues work today.";
  const yahooError = route.current.params.get("yahoo_error");

  async function findProvider(p: "espn" | "yahoo", e?: SubmitEvent) {
    e?.preventDefault();
    const t = (p === "espn" ? espnText : yahooText).trim();
    if (!t) return;
    provBusy = true;
    provError = provErrorCode = provErrorFix = null;
    provLeague = null;
    try {
      provLeague = await setupGet<ProviderLeague>(p === "espn" ? espnLeaguePath(t) : yahooLeaguePath(t));
      privateForm = false;
      void reveal(); // ---- IN-1
    } catch (err) {
      const se = setupError(err);
      provErrorCode = se?.code ?? null;
      provErrorFix = se?.fix ?? null;
      const body = err instanceof ApiError ? (err.body as { private_form?: boolean } | null) : null;
      privateForm = !!body?.private_form;
      const who = p === "espn" ? "ESPN" : "Yahoo";
      if (err instanceof Unauthorized) onauth();
      else if (se && err instanceof ApiError && err.status === 404) provError = se.words;
      else if (err instanceof ApiError && err.status === 404) provError = `${err.message}.`;
      else if (err instanceof ApiError && err.status === 502) provError = `${who} did not answer. Try again in a minute.`;
      else if (err instanceof ApiError && err.status === 503) provError = `${APP_NAME} is busy reading ${who}. Try again in a minute.`;
      else provError = `Cannot reach ${APP_NAME} right now (${err instanceof Error ? err.message : String(err)}). Try again in a minute.`;
    } finally {
      provBusy = false;
    }
  }

  async function sendEspnCookies(e: SubmitEvent) {
    e.preventDefault();
    espnSaved = null;
    try {
      await setupPost(espnConnectPath, { espn_s2: espnS2.trim(), swid: espnSwid.trim() });
      espnS2 = espnSwid = "";
      espnSaved = "Saved in this browser. Looking for the league again…";
      await findProvider("espn");
    } catch (err) {
      if (err instanceof Unauthorized) onauth();
      espnSaved = err instanceof ApiError ? `${err.message}.` : "That did not work. Check both values and try again.";
    }
  }

  async function loadYahooMe() {
    if (yahooMeState === "loading") return;
    yahooMeState = "loading";
    try {
      yahooMe = await setupGet<YahooMe>(yahooMePath);
      yahooMeState = "idle";
    } catch (err) {
      if (err instanceof Unauthorized) onauth();
      yahooMeState = "failed";
    }
  }

  async function disconnectYahoo() {
    try {
      await setupPost(yahooDisconnectPath, {});
    } catch {
      /* the list reloads either way */
    }
    yahooMe = null;
    await loadYahooMe();
  }

  function pickProvider(v: ProviderLeague, rosterId: number) {
    const team = v.teams.find((t) => t.roster_id === rosterId);
    prefs.rememberLeague({ league_id: v.league.league_id, name: v.league.name, scoring_label: v.league.scoring_label,
      total_rosters: v.league.total_rosters, roster_id: rosterId, team_name: team?.team_name ?? null });
  }

  function pickYahooRow(l: YahooMe["leagues"][number]) {
    prefs.rememberLeague({ league_id: l.league_id, name: l.name, scoring_label: l.scoring_label, total_rosters: l.total_rosters,
      roster_id: l.roster_id, team_name: l.team_name });
  }

  $effect(() => {
    if (platform === "yahoo" && yahooMe === null && yahooMeState === "idle") void loadYahooMe();
  });
  $effect(() => {
    if (provLeague?.card) void loadCheck(provLeague.league.league_id, provLeague.card.check_path);
  });
  // ---- end IK-3

  // ---- IC-3 (Wave I-C): the card's scoring check — IC-1's route, loaded after the card shows (never blocks it);
  // a league the check cannot answer for yet says so in one line instead of a number.
  type CheckState = ScoringCheck | "loading" | "none";
  let checks = $state<Record<string, CheckState>>({});
  async function loadCheck(id: string, path: string) {
    if (checks[id]) return;
    checks[id] = "loading";
    try {
      checks[id] = await get<ScoringCheck>(path);
    } catch (err) {
      if (err instanceof Unauthorized) onauth();
      checks[id] = "none";
    }
  }
  const cardOf = (l: object) => (l as WithCard).card ?? null;
  $effect(() => {
    if (mfl?.card) void loadCheck(mfl.league.league_id, mfl.card.check_path);
  });
  $effect(() => {
    for (const l of (mine?.leagues ?? []).slice(0, 8)) {
      const c = cardOf(l);
      if (c) void loadCheck(l.league_id, c.check_path);
    }
  });
  // ---- end IC-3
  import AccountEntry from "../components/AccountEntry.svelte"; // ---- IK-4: the account entry (the block at the bottom)
  // ---- IL-5 (Wave I-L): the provider's status from /api/providers (the verified flip, ESPN's kill switch) and, signed
  // in, where a Yahoo / ESPN connection is kept (this browser and the account)
  import { account as acct } from "../lib/account.svelte";
  const statusOf = (p: string) => caps?.providers.find((x) => x.provider === p) ?? null;
  const espnOff = $derived(statusOf("espn")?.status === "off");
  const keptWithAccount = $derived(!!(acct.status?.enabled && acct.status.signed_in));
  // ---- end IL-5
</script>

<!-- ---- IC-3: the card's read-backs and the scoring check -->
{#snippet readback(card: LeagueCard, id: string)}
  {@const ck = checks[id]}
  <!-- ---- IE-2 (Wave I-E): the read-back collapsed to one status line (the review: league and team first, the scoring
       formula and the check behind it); open, the full read-back and the check as before -->
  {@const estimated = card.scoring.approximated.length > 0 || !!card.scoring.not_priced_text}
  {@const platform = providerShort(id)}<!-- IK-3: was MFL | Sleeper -->
  <details class="text-sm leading-snug" data-testid="league-card" data-league={id}>
    <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-base text-ink-2" data-testid="scoring-status">
      <span class="chev text-ink-3" aria-hidden="true">›</span>
      <span>{estimated ? `Custom ${platform} scoring — some pieces are estimated` : `${platform} scoring, read exactly`}</span>
    </summary>
    <div class="space-y-1 pb-1">
    <!-- ---- end IE-2 -->
    <p class="font-semibold text-ink" data-testid="card-lineup">{card.lineup.text}</p>
    {#if card.lineup.unread_text}<p class="text-warn" data-testid="card-unread">{card.lineup.unread_text}</p>{/if}
    <p class="text-ink-2" data-testid="card-scoring"><span class="font-semibold text-ink">Scoring:</span> {card.scoring.text}</p>
    {#if card.scoring.not_priced_text}<p class="text-ink-3" data-testid="card-not-priced">{card.scoring.not_priced_text}</p>{/if}
    {#if card.scoring.approximated.length}
      <details class="text-ink-3" data-testid="card-approximated">
        <summary class="cursor-pointer py-1">How the projections handle your scoring ({card.scoring.approximated.length})</summary>
        <ul class="list-disc space-y-0.5 pl-5">
          {#each card.scoring.approximated as a, i (i)}<li>{a[0].toUpperCase() + a.slice(1)}{a.endsWith(".") ? "" : "."}</li>{/each}
        </ul>
      </details>
    {/if}
    {#if ck === "loading"}
      <p class="text-ink-3" data-testid="card-check">Checking last week's points…</p>
    {:else if ck === "none"}
      <p class="text-ink-3" data-testid="card-check">The scoring check is not available for this league yet.</p>
    {:else if ck}
      {@const misses = bigMisses(ck)}
      <p class={ck.within_1 === ck.n ? "text-good" : "text-ink-2"} data-testid="card-check">{checkLine(ck)}</p>
      <!-- ---- IE-2: the check stays one line; the misses behind it -->
      {#if misses.length}
        <details class="text-ink-2" data-testid="card-misses">
          <summary class="cursor-pointer py-1">The misses ({misses.length})</summary>
          <p>{misses.map(missLine).join("; ")}.</p>
        </details>
      {/if}
    {/if}
    </div>
  </details>
{/snippet}
<!-- ---- end IC-3 -->

<!-- ---- IN-1 (Wave I-N): the setup screen on a desktop (Andrew: "you have to scroll down to actually see where your leagues
     are … a point where people probably bounce"). Three parts: the form (who you are, the platform, its box), the results,
     the extras (what the platform gives, the account). A phone stacks them in that order, so the leagues come right under
     the field; from 900 px the results sit beside the form, at the top. A search scrolls the results into view and moves
     focus to them. The front door (browse without a league) moved to Home (routes/Home.svelte). -->
<main class="mx-auto max-w-xl px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-10 wide:grid wide:max-w-6xl wide:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] wide:items-start wide:gap-x-10" data-testid="leagues">
  <div class="space-y-5 wide:col-start-1 wide:row-start-1" data-testid="setup-form-col">
    <header class="space-y-1">
      {#if current}
        <a href={withContext("/", { league: current, team: prefs.team(current) })} class="ll-link inline-block py-1 text-base" data-testid="to-week"
          >‹ My week</a
        >
      {:else}
        <a href="/home" class="ll-link inline-block py-1 text-base" data-testid="to-home">‹ Home</a><!-- IN-1: the front door moved to Home -->
      {/if}
      <h1 class="flex items-center gap-2 text-3xl font-extrabold tracking-tight">
        <span class="grid h-9 w-9 place-items-center rounded-sm bg-accent text-sm font-black text-on-accent">{APP_MARK}</span>{APP_NAME}
      </h1>
      <p class="text-base leading-snug text-ink-2">
        <!-- IE-0 (Wave I-E): both platforms, not Sleeper only (the review's P0 #3) -->
        Who to start this week and what each player is worth, in your league's own scoring — on Sleeper, MyFantasyLeague, ESPN or Yahoo.
      </p>
    </header>

    <!-- ---- II-5 (Wave I-I): the steps, the one platform choice, then that platform's box -->
    <ol id="open-league" class="flex scroll-mt-4 flex-wrap items-center gap-x-1 gap-y-1 text-xs sm:text-sm" aria-label="Setup" data-testid="setup-steps">
      {#each STEPS as s, i (s.key)}
        <li
          class="rounded-full px-2 py-0.5 whitespace-nowrap {i === stepIndex ? 'bg-accent font-bold text-on-accent' : i < stepIndex ? 'text-ink-2' : 'text-ink-3'}"
          aria-current={i === stepIndex ? "step" : undefined}
          data-step={s.key}
        >
          {i < stepIndex ? "✓ " : ""}{s.label}
        </li>
        {#if i < STEPS.length - 1}<li class="text-ink-3" aria-hidden="true">›</li>{/if}
      {/each}
    </ol>

    <fieldset class="space-y-2" data-testid="platform-pick">
      <legend class="ll-label mb-2 block">Fantasy platform</legend>
      <div class="grid grid-cols-2 gap-2"><!-- IK-3: four platforms, two by two (MyFantasyLeague does not fit a quarter of the column) -->
        {#each PLATFORMS.map((x) => [x.key, x.name]) as [key, name] (key)}
          <label
            class="flex min-h-11 cursor-pointer items-center justify-center rounded-md border px-3 py-2 text-center text-base font-semibold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent {platform === key ? 'border-accent bg-accent-soft text-ink ring-1 ring-accent' : 'border-line bg-surface text-ink-2'}"
            data-testid="platform-{key}"
          >
            <input class="sr-only" type="radio" name="ll-platform" value={key} checked={platform === key} onchange={() => choose(key as Platform)} />
            {name}
          </label>
        {/each}
      </div>
      <!-- ---- IK-3: II-5's "ESPN or Yahoo?" expander is now the two choices above; what each one is, in a line -->
      {#if platform === "espn" || platform === "yahoo"}
        <p class="text-sm leading-snug text-ink-3" data-testid="platform-note" data-platform={platform}>
          {#if platform === "espn"}Unofficial: ESPN has no public API for fantasy leagues. {APP_NAME} reads what a public league shows anyone, read-only.{:else}Through
            Yahoo's official Fantasy Sports API, read-only, after you allow it with your Yahoo sign-in.{/if}
          {#if (statusOf(platform)?.status ?? "unverified") === "unverified"}New: not verified on a live league yet.{/if}<!-- IL-5: the verified flip -->
        </p>
      {/if}
    </fieldset>

    {#if platform === "sleeper"}
    <form class="space-y-2" onsubmit={submit} data-testid="username-form">
      <label class="ll-label block" for="ll-username">Your Sleeper username, or a league link</label>
      <div class="flex gap-2">
        <input
          id="ll-username"
          class="ll-input flex-1 py-2.5"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          autocorrect="off"
          spellcheck="false"
          placeholder="Username or league link"
          bind:value={username}
          data-testid="username"
        />
        <button
          class="shrink-0 rounded-md bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60"
          disabled={busy || !username.trim()}
          aria-busy={busy}
          data-testid="username-go">{busy ? "Looking…" : "Find my leagues"}</button
        >
      </div>
      <p class="text-sm leading-snug text-ink-3">
        No password to Sleeper: {APP_NAME} only reads what Sleeper shows anyone (your leagues, rosters and scoring).
      </p>
      <!-- ---- II-5: where to find it, with an example -->
      <details class="text-sm leading-snug text-ink-2" data-testid="setup-help">
        <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-ink-3"><span class="chev" aria-hidden="true">›</span>Where do I find these?</summary>
        <ul class="list-disc space-y-1 pb-1 pl-5">
          <li><strong>Username</strong>: the name you sign in to Sleeper with — not your team's name.</li>
          <li>
            <strong>League link</strong>: open the league on sleeper.com; the address looks like
            <span class="font-mono text-xs break-all">sleeper.com/leagues/<strong>1389709692405551104</strong>/team</span>. Paste it, or just
            the long number (the league id).
          </li>
        </ul>
      </details>
      {#if error}<p class="text-base text-bad" role="alert" data-testid="username-error" data-code={errorCode}>{error}</p>{/if}
      {#if error && errorFix}<p class="text-sm leading-snug text-ink-2" data-testid="setup-fix">{errorFix}</p>{/if}
    </form>
    {:else if platform === "mfl"}<!-- IK-3: was {:else} -->
    <!-- I0-B: MyFantasyLeague -->
    <form class="space-y-2" onsubmit={findMfl} data-testid="mfl-form">
      <label class="ll-label block" for="ll-mfl">Find your MyFantasyLeague league</label><!-- II-5: was "On MyFantasyLeague? …" -->
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
        Paste your league link, or type your league's name as it appears in the MFL app. {APP_NAME} only reads what the league shares.
      </p>
      <!-- ---- II-5: where to find the league id, with an example -->
      <details class="text-sm leading-snug text-ink-2" data-testid="setup-help">
        <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-ink-3"><span class="chev" aria-hidden="true">›</span>Where do I find the league id?</summary>
        <p class="pb-1">
          Open your league on the MFL website: the number after <span class="font-mono text-xs">/home/</span> in the address is the league id —
          <span class="font-mono text-xs break-all">www45.myfantasyleague.com/2026/home/<strong>70587</strong></span> is league 70587. Paste the
          whole link or just the number. The MFL app hides the address: type the league's name instead.
        </p>
      </details>
      {#if mflError}<p class="text-base text-bad" role="alert" data-testid="mfl-error" data-code={mflErrorCode}>{mflError}</p>{/if}
      {#if mflError && mflErrorFix}<p class="text-sm leading-snug text-ink-2" data-testid="setup-fix">{mflErrorFix}</p>{/if}
    </form>
    <!-- ---- IL-5: ESPN switched off on this server (LEAGUE_LAB_ESPN_LEAGUES=off): said, no form -->
    {:else if platform === "espn" && espnOff}
    <p class="rounded-lg bg-raised p-4 text-base" data-testid="espn-off">{statusOf("espn")?.off ?? "ESPN leagues: not available right now"}. Sleeper and MyFantasyLeague leagues work as before.</p>
    <!-- ---- IK-3 (Wave I-K): ESPN — a league id or link; "Private league?" only when the server reads private leagues -->
    {:else if platform === "espn"}
    <form class="space-y-2" onsubmit={(e) => findProvider("espn", e)} data-testid="espn-form">
      <label class="ll-label block" for="ll-espn">Your ESPN league link or id</label>
      <div class="flex gap-2">
        <input
          id="ll-espn"
          class="ll-input min-w-0 flex-1 py-2.5"
          type="text"
          inputmode="url"
          enterkeyhint="search"
          autocapitalize="none"
          autocorrect="off"
          spellcheck="false"
          placeholder="League link or id"
          bind:value={espnText}
          data-testid="espn-link"
        />
        <button
          class="shrink-0 rounded-md bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60"
          disabled={provBusy || !espnText.trim()}
          data-testid="espn-go">{provBusy ? "Looking…" : "Find my league"}</button
        >
      </div>
      <p class="text-sm leading-snug text-ink-3" data-testid="espn-help">
        A public ESPN league opens by its id. No password to ESPN: {APP_NAME} only reads what the league shows anyone.
      </p>
      <details class="text-sm leading-snug text-ink-2" data-testid="setup-help">
        <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-ink-3"><span class="chev" aria-hidden="true">›</span>Where do I find the league id?</summary>
        <p class="pb-1">
          Open your league on fantasy.espn.com: the number after <span class="font-mono text-xs">leagueId=</span> in the address is the league id —
          <span class="font-mono text-xs break-all">fantasy.espn.com/football/league?leagueId=<strong>4242</strong></span> is league 4242. Paste the whole
          link or just the number. A private league (the default for many ESPN leagues) can be made public by its manager: Settings → Basic Settings →
          League Visibility.
        </p>
      </details>
      {#if provError}<p class="text-base text-bad" role="alert" data-testid="espn-error" data-code={provErrorCode}>{provError}</p>{/if}
      {#if provError && provErrorFix}<p class="text-sm leading-snug text-ink-2" data-testid="setup-fix">{provErrorFix}</p>{/if}
    </form>
    {#if privateForm && caps?.espn_private}
      <details class="rounded-lg border border-line bg-surface p-3 text-sm leading-snug" data-testid="espn-private" open>
        <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 font-semibold text-ink"><span class="chev" aria-hidden="true">›</span>Private league?</summary>
        <form class="space-y-2 pt-1" onsubmit={sendEspnCookies} data-testid="espn-private-form">
          <p class="text-ink-2">
            {#if keptWithAccount}Your ESPN cookies stay in this browser and, encrypted, with your account, so your other devices read your league
              too; Disconnect removes them from both.{:else}Your ESPN cookies stay in your browser; {APP_NAME} reads your league with them and never stores them.{/if} On a computer signed in to
            espn.com, open the browser's cookies for espn.com and copy <span class="font-mono text-xs">espn_s2</span> and
            <span class="font-mono text-xs">SWID</span>.
          </p>
          <label class="ll-label block" for="ll-espn-s2">espn_s2</label>
          <input id="ll-espn-s2" class="ll-input w-full py-2" type="password" autocomplete="off" bind:value={espnS2} data-testid="espn-s2" />
          <label class="ll-label block" for="ll-espn-swid">SWID</label>
          <input id="ll-espn-swid" class="ll-input w-full py-2" type="password" autocomplete="off" placeholder={"{…}"} bind:value={espnSwid} data-testid="espn-swid" />
          <button class="rounded-md bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60" disabled={!espnS2.trim() || !espnSwid.trim()} data-testid="espn-private-go"
            >Read my private league</button
          >
          {#if espnSaved}<p class="text-ink-2" data-testid="espn-private-said">{espnSaved}</p>{/if}
        </form>
      </details>
    {/if}
    <!-- ---- IK-3: Yahoo — Connect with Yahoo → your leagues → My Week; a league link works too; "coming soon" until set up -->
    {:else}
    <section class="space-y-2" data-testid="yahoo-setup">
      {#if yahooError && !yahooMe?.connected}<p class="text-base text-bad" role="alert" data-testid="yahoo-error-back" data-code={yahooError}>{YAHOO_ERRORS[yahooError] ?? YAHOO_ERRORS.refused}</p>{/if}
      {#if caps?.yahoo_configured === false || yahooMe?.configured === false}
        <button type="button" class="w-full rounded-md border border-line bg-raised px-4 py-2.5 font-bold text-ink-3" disabled data-testid="yahoo-soon"
          >Connect with Yahoo — coming soon</button
        >
        <!-- PO 2026-10-05: the keys are set and Yahoo has not opened the app's fantasy access yet: said so, in the server's words -->
        {#if caps?.yahoo_pending || yahooMe?.pending}
          <p class="text-sm leading-snug text-ink-3" data-testid="yahoo-note" data-pending="1">{yahooMe?.pending && yahooMe.note ? yahooMe.note : YAHOO_PENDING}</p>
        {:else}
          <p class="text-sm leading-snug text-ink-3" data-testid="yahoo-note">Yahoo sign-in is not set up on this server yet. Sleeper and MyFantasyLeague leagues work today.</p>
        {/if}
      {:else if yahooMe?.connected}
        <div class="flex items-baseline justify-between gap-2">
          <h2 class="ll-label">Your Yahoo leagues, {yahooMe.season}</h2>
          <button type="button" class="text-sm text-accent underline" onclick={disconnectYahoo} data-testid="yahoo-disconnect">Disconnect Yahoo</button>
        </div>
        {#if yahooMe.note}<p class="rounded-lg bg-raised p-4 text-base" data-testid="yahoo-note">{yahooMe.note}</p>{/if}
        <ul class="space-y-2" data-testid="yahoo-leagues">
          {#each yahooMe.leagues as l (l.league_id)}
            <li>
              <a
                href={href(l.league_id, l.roster_id)}
                onclick={() => pickYahooRow(l)}
                class="relative block overflow-hidden rounded-lg border bg-surface p-4 pl-5 {l.league_id === current ? 'border-accent ring-1 ring-accent' : 'border-line'}"
                style="box-shadow:var(--ll-shadow)"
                data-testid="yahoo-league"
                data-league={l.league_id}
              >
                <span class="absolute inset-y-0 left-0 w-1 {l.league_id === current ? 'bg-accent' : 'bg-line-strong'}" aria-hidden="true"></span>
                <div class="text-lg leading-snug font-bold break-words">{l.name} <span class="text-sm font-semibold text-ink-3">Yahoo</span></div>
                {#if leagueLine(l)}<div class="text-sm leading-snug text-ink-3">{leagueLine(l)}</div>{/if}
                {#if l.team_name}<div class="mt-1 text-sm leading-snug text-ink-2">Your team: <strong>{l.team_name}</strong></div>{/if}
              </a>
              {#if l.card}<div class="px-1 pt-2">{@render readback(l.card, l.league_id)}</div>{/if}
            </li>
          {/each}
        </ul>
      {:else}
        <a href={yahooConnectPath} class="block w-full rounded-md bg-accent px-4 py-2.5 text-center font-bold text-on-accent" data-testid="yahoo-connect"
          >Connect with Yahoo</a
        >
        <p class="text-sm leading-snug text-ink-3" data-testid="yahoo-note">
          {yahooMeState === "loading" ? "Checking your Yahoo connection…" : yahooMeState === "failed" ? "Could not check your Yahoo connection. Try again in a minute." : (yahooMe?.note ?? "Connect with Yahoo to list your leagues here.")}
          Yahoo asks you to allow read-only access to your fantasy leagues; {APP_NAME} keeps the connection {keptWithAccount
            ? "in this browser and, encrypted, with your account (your other devices get it when you sign in)"
            : "in this browser only"}.
        </p>
      {/if}
      {#if !(caps?.yahoo_configured === false || yahooMe?.configured === false)}
        <form class="space-y-2 pt-1" onsubmit={(e) => findProvider("yahoo", e)} data-testid="yahoo-form">
          <label class="ll-label block" for="ll-yahoo">Or a Yahoo league link</label>
          <div class="flex gap-2">
            <input
              id="ll-yahoo"
              class="ll-input min-w-0 flex-1 py-2.5"
              type="text"
              inputmode="url"
              enterkeyhint="search"
              autocapitalize="none"
              autocorrect="off"
              spellcheck="false"
              placeholder="football.fantasysports.yahoo.com/f1/…"
              bind:value={yahooText}
              data-testid="yahoo-link"
            />
            <button
              class="shrink-0 rounded-md border border-accent px-4 py-2.5 font-bold text-accent disabled:opacity-60"
              disabled={provBusy || !yahooText.trim()}
              data-testid="yahoo-go">{provBusy ? "Looking…" : "Open"}</button
            >
          </div>
          <details class="text-sm leading-snug text-ink-2" data-testid="setup-help">
            <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-ink-3"><span class="chev" aria-hidden="true">›</span>Where do I find the link?</summary>
            <p class="pb-1">
              Open your league on Yahoo Fantasy in a browser: the number after <span class="font-mono text-xs">/f1/</span> is the league id —
              <span class="font-mono text-xs break-all">football.fantasysports.yahoo.com/f1/<strong>12345</strong></span> is league 12345.
            </p>
          </details>
          {#if provError}<p class="text-base text-bad" role="alert" data-testid="yahoo-error" data-code={provErrorCode}>{provError}</p>{/if}
          {#if provError && provErrorFix}<p class="text-sm leading-snug text-ink-2" data-testid="setup-fix">{provErrorFix}</p>{/if}
        </form>
      {/if}
    </section>
    <!-- ---- end IK-3 -->
    {/if}
  </div>

  <!-- ---- IN-1: the results — under the field on a phone, beside it from 900 px; scrolled into view and focused after a search -->
  <section
    class="mt-5 space-y-5 scroll-mt-3 outline-none wide:col-start-2 wide:row-span-2 wide:row-start-1 wide:mt-0 wide:pt-10"
    aria-label="Your leagues"
    tabindex="-1"
    bind:this={resultsEl}
    data-testid="setup-results"
  >
    {#if platform === "sleeper"}{@render mineList()}{/if}
    <!-- ---- II-5: a Sleeper league opened by its link: the league, then "which team is yours?" -->
    {#if sleeperLeague}
      {@const v = sleeperLeague}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid="sleeper-card">
        <div>
          <div class="text-lg leading-snug font-bold break-words">{v.league.name} <span class="text-sm font-semibold text-ink-3">Sleeper</span></div>
          {#if leagueLine(v.league)}<div class="text-sm leading-snug text-ink-3">{leagueLine(v.league)}</div>{/if}
        </div>
        <h2 class="ll-label pt-1">Which team is yours?</h2>
        <ul class="grid grid-cols-1 gap-1.5 sm:grid-cols-2" data-testid="team-pick">
          {#each v.teams as t (t.roster_id)}
            <li>
              <a
                href={href(v.league.league_id, t.roster_id)}
                onclick={() => pickSleeper(v, t.roster_id)}
                class="block rounded-md border border-line px-3 py-2.5 text-base"
                data-testid="team-option"
                data-roster={t.roster_id}
                >{t.team_name}{#if t.manager_name && t.manager_name !== t.team_name}<span class="block text-sm text-ink-3">{t.manager_name}</span>{/if}</a
              >
            </li>
          {/each}
        </ul>
        {#if v.card}{@render readback(v.card, v.league.league_id)}{/if}
      </section>
    {/if}
    <!-- ---- end II-5 -->

    <!-- ---- IK-3: an ESPN / Yahoo league: the league, then "which team is yours?" (the link's team pre-selected) -->
    {#if provLeague}
      {@const v = provLeague}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid="provider-card" data-platform={v.platform}>
        <div>
          <div class="text-lg leading-snug font-bold break-words">{v.league.name} <span class="text-sm font-semibold text-ink-3">{providerShort(v.league.league_id)}</span></div>
          {#if leagueLine(v.league)}<div class="text-sm leading-snug text-ink-3">{leagueLine(v.league)}</div>{/if}
          {#if v.platform === "yahoo"}
            <!-- PO 2026-10-05: Yahoo's attribution policy (docs/YAHOO_TERMS.md) -->
            <div class="text-sm leading-snug text-ink-3" data-testid="yahoo-attribution">Fantasy data provided by <a class="ll-link" href="https://football.fantasysports.yahoo.com/" target="_blank" rel="noopener noreferrer">Yahoo Fantasy</a></div>
          {/if}
        </div>
        <h2 class="ll-label pt-1">Which team is yours?</h2>
        <ul class="grid grid-cols-1 gap-1.5 sm:grid-cols-2" data-testid="team-pick">
          {#each v.teams as t (t.roster_id)}
            <li>
              <a
                href={href(v.league.league_id, t.roster_id)}
                onclick={() => pickProvider(v, t.roster_id)}
                class="block rounded-md border px-3 py-2.5 text-base {t.roster_id === v.roster_id ? 'border-accent font-bold ring-1 ring-accent' : 'border-line'}"
                data-testid="team-option"
                data-roster={t.roster_id}
                >{t.team_name}{#if t.manager_name && t.manager_name !== t.team_name}<span class="block text-sm font-normal text-ink-3">{t.manager_name}</span>{/if}</a
              >
            </li>
          {/each}
        </ul>
        {#if v.card}{@render readback(v.card, v.league.league_id)}{:else}
          <p class="text-sm leading-snug text-ink-2" data-testid="provider-note">{v.scoring_note}</p>
        {/if}
        {#if v.unmapped.length}
          <p class="text-sm leading-snug text-warn" data-testid="provider-unmapped">
            {v.unmapped.length} of {v.players} players have no projection here yet: {v.unmapped.map((u) => u.name ?? u.espn_id ?? u.yahoo_id).join(", ")}.
          </p>
        {/if}
      </section>
    {/if}
    <!-- ---- end IK-3 -->

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
        <!-- ---- IE-2: the team picker first (it was below the scoring read-back, under the first desktop screen) -->
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
        {#if v.card}{@render readback(v.card, v.league.league_id)}{:else}
          <p class="text-sm leading-snug text-ink-2" data-testid="mfl-note">{v.scoring_note}</p>
        {/if}
        {#if v.unmapped.length}
          <p class="text-sm leading-snug text-warn" data-testid="mfl-unmapped">
            {v.unmapped.length} of {v.players} players have no projection here yet: {v.unmapped.map((u) => u.name ?? u.mfl_id).join(", ")}.
          </p>
        {/if}
        <!-- ---- end IE-2 -->
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
              <div class="text-lg leading-snug font-bold">{l.name} <span class="text-sm font-semibold text-ink-3">{providerShort(l.league_id)}</span></div><!-- II-5: a Sleeper league opened by its link too; IK-3: ESPN / Yahoo -->
              {#if leagueLine(l)}<div class="text-sm leading-snug text-ink-3">{leagueLine(l)}</div>{/if}
              {#if l.team_name}<div class="mt-1 text-sm leading-snug text-ink-2">Your team: <strong>{l.team_name}</strong></div>{/if}
            </a>
          </li>
        {/each}
      </ul>
    {/if}
    {#if platform !== "sleeper"}{@render mineList()}{/if}
    {#if !mine && !sleeperLeague && !provLeague && !mfl && !mflFound && !mflSaved.length}
      <div class="hidden rounded-lg border border-dashed border-line-strong p-6 text-base text-ink-3 wide:block" data-testid="setup-results-empty">
        Your leagues show here once you find them.
        <a class="ll-link" href="/home">Or look around without a league ›</a>
      </div>
    {/if}
  </section>

  <div class="mt-5 space-y-5 wide:col-start-1 wide:row-start-2" data-testid="setup-extras">
    <!-- ---- II-5: what this platform gives (GET /api/providers): said, never substituted -->
    {#if caps}
      {@const pv = caps.providers.find((x) => x.provider === platform)}
      {#if pv}
        {@const gaps = FEATURES.filter((f) => pv.features[f]?.status === "no")}
        <details class="text-sm leading-snug" data-testid="provider-caps" data-platform={platform}>
          <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-ink-3">
            <span class="chev" aria-hidden="true">›</span>
            <span>What {APP_NAME} reads from {pv.short} leagues{gaps.length ? ` — ${gaps.length} not available yet` : ""}</span>
          </summary>
          <ul class="space-y-1.5 pb-1">
            {#each FEATURES as f (f)}
              {@const x = pv.features[f]}
              <li class="flex gap-2" data-testid="cap" data-feature={f} data-status={x.status}>
                <span class="w-16 shrink-0 text-xs font-semibold tracking-wide whitespace-nowrap uppercase {x.status === 'yes' ? 'text-good' : x.status === 'partial' ? 'text-warn' : 'text-bad'}">{STATUS_WORDS[x.status]}</span>
                <span class="min-w-0 text-ink-2">{#if x.status === "no"}{x.unavailable}.{:else}<strong class="text-ink">{x.label}</strong>: {x.words}.{/if}</span>
              </li>
            {/each}
          </ul>
        </details>
      {/if}
    {/if}
    <p class="text-sm leading-snug text-ink-3" data-testid="setup-guest">No account needed: {APP_NAME} remembers your leagues on this device.</p>
    <!-- ---- IK-4 (Wave I-K): the account entry — sign in with your email to keep these leagues on any device (only when
         the server has accounts on: components/AccountEntry.svelte) -->
    <AccountEntry />
    <!-- ---- end IK-4 -->
  </div>
</main>

<!-- ---- IN-1: the username's leagues (rendered first in the results for Sleeper, after the other platform's card otherwise) -->
{#snippet mineList()}
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
          No leagues for that username this season. <span class="text-ink-2">A league {mine.user.username} joins on Sleeper shows up here; a league link works too.</span>
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
                  <span class="text-warn">You have no team in this league: pick the team to see below.</span><!-- II-5 -->
                {/if}
              </div>
            </a>
            <!-- ---- II-5: no team of yours in this league: pick the team to see, here (it was "after you open it") -->
            {#if l.roster_id === null}
              {@const tl = teamsOf[l.league_id]}
              <details class="px-1 pt-1 text-base" data-testid="team-pick-open" ontoggle={(e) => e.currentTarget.open && loadTeams(l.league_id)}>
                <summary class="flex min-h-11 cursor-pointer items-center gap-1.5 py-1 text-accent"><span class="chev" aria-hidden="true">›</span>Pick the team to see</summary>
                {#if tl === "loading" || tl === undefined}
                  <p class="text-sm text-ink-3">Loading the teams…</p>
                {:else if tl === "failed"}
                  <p class="text-sm text-bad">The teams did not load. Close and open this again.</p>
                {:else}
                  <ul class="grid grid-cols-1 gap-1.5 pb-1 sm:grid-cols-2" data-testid="team-pick">
                    {#each tl as t (t.roster_id)}
                      <li>
                        <a href={href(l.league_id, t.roster_id)} class="block rounded-md border border-line px-3 py-2.5" data-testid="team-option" data-roster={t.roster_id}
                          >{t.team_name}</a
                        >
                      </li>
                    {/each}
                  </ul>
                {/if}
              </details>
            {/if}
            <!-- ---- end II-5 -->
            {#if cardOf(l)}<div class="px-1 pt-2">{@render readback(cardOf(l) as LeagueCard, l.league_id)}</div>{/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}
{/snippet}
