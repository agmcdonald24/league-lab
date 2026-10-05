<script lang="ts">
  // ---- IK-4 (Wave I-K): the account (docs/ACCOUNTS.md § "Built, phase 1"). Sign in with an emailed link (no password);
  // the leagues saved to the account, the team in each, the default league; save this device's leagues; sign out (here
  // or everywhere); delete the account. Off on the server (GET /api/account/status → enabled: false): one plain line,
  // and the setup screen is one tap away — guest use never needs an account.
  import { onMount } from "svelte";
  import { APP_MARK, APP_NAME } from "../lib/brand";
  import { leagueLine } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import {
    account,
    AccountError,
    deleteAccount,
    dropLinkToken,
    GateClosed,
    linkToken,
    loadStatus,
    PROVIDER_LABEL,
    removeLeague,
    requestLink,
    saveLeagues,
    setDefault,
    signOut,
    unsaved,
    verifyLink,
    type SavedLeague,
  } from "../lib/account.svelte";

  let { current = null, onauth }: { current?: string | null; onauth: () => void } = $props();

  let email = $state("");
  let sentTo = $state<string | null>(null);
  let busy = $state(false);
  let problem = $state<string | null>(null);
  let token = $state<string | null>(linkToken());
  let confirmDelete = $state(false);
  let gone = $state(false);

  const st = $derived(account.status);
  const me = $derived(account.me);
  const toSave = $derived(unsaved(me));

  onMount(() => {
    void loadStatus();
  });

  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    busy = true;
    problem = null;
    try {
      await fn();
      return true;
    } catch (e) {
      if (e instanceof GateClosed) onauth();
      else problem = e instanceof AccountError ? e.message : `Cannot reach ${APP_NAME} right now. Try again in a minute.`;
      return false;
    } finally {
      busy = false;
    }
  }

  async function ask(e: SubmitEvent) {
    e.preventDefault();
    const to = email.trim();
    if (await run(() => requestLink(to))) sentTo = to;
  }

  async function useLink() {
    const t = token;
    if (!t) return;
    const ok = await run(() => verifyLink(t));
    dropLinkToken();
    token = null;
    if (ok) {
      gone = false;
      sentTo = null;
    }
  }

  async function leave(everywhere: boolean) {
    if (await run(() => signOut(everywhere))) sentTo = null;
  }

  const teamLine = (l: SavedLeague) => (l.team_name ? l.team_name : l.team_id !== null ? `Team ${l.team_id}` : "No team picked");
  const synced = (l: SavedLeague) => (l.last_sync_at ? `read ${new Date(l.last_sync_at).toLocaleDateString()}` : "read when you open it");
  const openHref = (l: SavedLeague) => withContext("/", { league: l.league, team: typeof l.team_id === "number" ? l.team_id : null });
</script>

<!-- the link opened in a tab that already shows this page: only the fragment changes (no reload) -->
<svelte:window onhashchange={() => (token = linkToken())} />

<main class="mx-auto max-w-xl space-y-5 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-10" data-testid="account">
  <header class="space-y-1">
    <a href={current ? withContext("/", { league: current, team: null }) : "/leagues"} class="ll-link inline-block py-1 text-base" data-testid="account-back"
      >‹ {current ? "My week" : "Your leagues"}</a
    >
    <h1 class="flex items-center gap-2 text-3xl font-extrabold tracking-tight">
      <span class="grid h-9 w-9 place-items-center rounded-sm bg-accent text-sm font-black text-on-accent">{APP_MARK}</span>Your account
    </h1>
  </header>

  {#if st === null}
    <div class="ll-skel h-32" aria-label="Loading"></div>
  {:else if !st.enabled}
    <p class="text-base text-ink-2" data-testid="account-off">
      Accounts are not on yet. {APP_NAME} remembers your leagues on this device; <a class="ll-link" href="/leagues">pick a league</a> to start.
    </p>
  {:else}
    {#if problem}
      <p class="rounded-md bg-warn-soft px-3 py-2 text-sm font-semibold text-warn" role="alert" data-testid="account-problem">{problem}</p>
    {/if}

    {#if token && !st.signed_in}
      <!-- the emailed link: one tap signs this device in (a mail scanner opening the link signs nobody in) -->
      <section class="space-y-3 rounded-lg border border-line bg-surface p-4" data-testid="link-confirm">
        <p class="text-base">Sign in to {APP_NAME} on this device?</p>
        <button class="w-full rounded-md bg-accent px-4 py-3 font-bold text-on-accent disabled:opacity-60" disabled={busy} onclick={useLink} data-testid="link-go"
          >Sign in on this device</button
        >
      </section>
    {:else if !st.signed_in || !me}
      {#if gone}
        <p class="text-base text-ink-2" data-testid="account-deleted">Your account is deleted. The leagues on this device stay here.</p>
      {/if}
      {#if sentTo}
        <section class="space-y-2" data-testid="link-sent" role="status">
          <p class="text-base font-semibold">Check your email.</p>
          <p class="text-base text-ink-2">
            A sign-in link is on its way to <strong>{sentTo}</strong>. It works once, for 15 minutes, on the device you open it on.
          </p>
          <button class="ll-link py-1 text-base" onclick={() => (sentTo = null)} data-testid="link-again">Use another address</button>
        </section>
      {:else}
        <form class="space-y-3" onsubmit={ask} data-testid="signin-form">
          <p class="text-base text-ink-2">
            An account keeps your leagues, your team in each and your saved Stats views, on any phone or computer. No password: we email you a
            link.
          </p>
          <label class="ll-label block" for="account-email">Email</label>
          <input
            id="account-email"
            class="ll-input w-full py-3"
            type="email"
            autocomplete="email"
            inputmode="email"
            placeholder="you@example.com"
            bind:value={email}
            data-testid="account-email"
          />
          <button class="w-full rounded-md bg-accent px-4 py-3 font-bold text-on-accent disabled:opacity-60" disabled={busy || !email.trim()} data-testid="account-send"
            >Email me a sign-in link</button
          >
          <p class="text-sm text-ink-3">You can keep using {APP_NAME} without one: your leagues stay on this device.</p>
        </form>
      {/if}
    {:else}
      <p class="text-base text-ink-2" data-testid="account-email-line">Signed in as <strong>{me.email}</strong>.</p>

      {#if toSave.length}
        <section class="space-y-2 rounded-lg border border-line bg-surface p-4" data-testid="save-local">
          <p class="text-base">
            This device has {toSave.length} league{toSave.length === 1 ? "" : "s"} your account does not have yet.
          </p>
          <button class="rounded-md bg-accent px-4 py-2.5 font-bold text-on-accent disabled:opacity-60" disabled={busy} onclick={() => run(() => saveLeagues(toSave))} data-testid="save-local-go"
            >Save {toSave.length === 1 ? "it" : `these ${toSave.length}`} to your account</button
          >
        </section>
      {/if}

      <section class="space-y-2" data-testid="saved-leagues">
        <h2 class="ll-label">Your leagues</h2>
        {#if me.leagues.length === 0}
          <p class="text-base text-ink-2" data-testid="saved-none">None saved yet. <a class="ll-link" href="/leagues">Pick a league</a>: it is saved here as you pick it.</p>
        {:else}
          <ul class="divide-y divide-line rounded-lg border border-line bg-surface">
            {#each me.leagues as l (l.league_key)}
              <li class="space-y-1 px-3 py-3" data-testid="saved-league" data-league={l.league}>
                <div class="flex items-baseline justify-between gap-2">
                  <a class="ll-link min-w-0 truncate text-base font-semibold" href={openHref(l)} data-testid="saved-open">{l.name ?? l.league}</a>
                  {#if l.is_default}<span class="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-bold" data-testid="saved-default">Default</span>{/if}
                </div>
                <p class="text-sm text-ink-2">
                  {PROVIDER_LABEL[l.provider]} · {l.season} · {teamLine(l)}{leagueLine(l) ? ` · ${leagueLine(l)}` : ""}
                </p>
                <p class="text-xs text-ink-3">{l.sync_status === "failing" ? "The last read failed: it is tried again when you open it" : synced(l)}</p>
                <div class="flex gap-4 pt-1 text-sm">
                  {#if !l.is_default}
                    <button class="ll-link min-h-9" disabled={busy} onclick={() => run(() => setDefault(l.league, l.season))} data-testid="saved-make-default">Make default</button>
                  {/if}
                  <button class="min-h-9 text-ink-3 underline" disabled={busy} onclick={() => run(() => removeLeague(l.league_key))} data-testid="saved-remove">Remove</button>
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </section>

      <section class="space-y-3 border-t border-line pt-4">
        <div class="flex flex-wrap gap-x-5 gap-y-2 text-base">
          <button class="ll-link min-h-11" disabled={busy} onclick={() => leave(false)} data-testid="signout">Sign out</button>
          <button class="ll-link min-h-11" disabled={busy} onclick={() => leave(true)} data-testid="signout-all">Sign out everywhere</button>
        </div>
        {#if !confirmDelete}
          <button class="min-h-11 text-sm text-bad underline" onclick={() => (confirmDelete = true)} data-testid="delete-ask">Delete my account</button>
        {:else}
          <div class="space-y-2 rounded-lg border border-bad p-3" data-testid="delete-confirm">
            <p class="text-sm">This deletes your email address, your saved leagues and your preferences from {APP_NAME} now. The leagues on this device stay.</p>
            <div class="flex gap-4">
              <button
                class="rounded-md border border-bad bg-bad-soft px-3 py-2 text-sm font-bold text-bad disabled:opacity-60"
                disabled={busy}
                onclick={async () => {
                  if (await run(deleteAccount)) {
                    gone = true;
                    sentTo = null;
                    confirmDelete = false;
                  }
                }}
                data-testid="delete-go">Yes, delete everything</button
              >
              <button class="text-sm underline" onclick={() => (confirmDelete = false)}>Keep it</button>
            </div>
          </div>
        {/if}
      </section>
    {/if}
    <p class="text-sm text-ink-3" data-testid="account-privacy">
      An account keeps your email address, the leagues and teams you save and your saved views — nothing else. Signing in keeps you signed in on that device for {st.session_days}
      days.
    </p>
  {/if}
</main>
