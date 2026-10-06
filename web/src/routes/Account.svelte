<script lang="ts">
  // ---- IK-4 (Wave I-K): the account (docs/ACCOUNTS.md § "Built, phase 1"). Sign in with an emailed link (no password);
  // the leagues saved to the account, the team in each, the default league; save this device's leagues; sign out (here
  // or everywhere); delete the account. Off on the server (GET /api/account/status → enabled: false): one plain line,
  // and the setup screen is one tap away — guest use never needs an account.
  // ---- IM-4 (Wave I-M): passkeys (docs/ACCOUNTS.md § "Passkeys"): "Create an account with a passkey" (this device's
  // leagues go in by themselves), "Sign in with a passkey", the passkeys listed with "Add another passkey" and Remove
  // (never the last way in). The emailed-link form stays when the server has a mailer; with both, both are offered.
  import { onMount } from "svelte";
  import { APP_MARK, APP_NAME } from "../lib/brand";
  import { leagueLine } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import {
    account,
    AccountError,
    addPasskey,
    createWithPasskey,
    deleteAccount,
    dropLinkToken,
    GateClosed,
    linkToken,
    loadStatus,
    methodsOf,
    passkeyBlocked,
    PROVIDER_LABEL,
    removeLeague,
    removePasskey,
    requestLink,
    saveLeagues,
    setDefault,
    signInWithPasskey,
    signOut,
    unsaved,
    verifyLink,
    type Passkey,
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
  const nWatch = $derived(new Set((account.me?.watchlist ?? []).map((w) => w.player_key)).size); // ---- IL-5
  const toSave = $derived(unsaved(me));
  // ---- IM-4
  const methods = $derived(methodsOf(st));
  const passkeyOn = $derived(methods.includes("passkey"));
  const emailOn = $derived(methods.includes("email"));
  const blocked = passkeyBlocked();
  const home = $derived(st?.passkey_home ?? "https://isuckatfantasy.io");
  const homeHost = $derived(home.replace(/^https?:\/\//, ""));
  const canPasskey = $derived(passkeyOn && blocked === null && st?.passkey_here !== false);
  const keys = $derived<Passkey[]>(me?.passkeys ?? []);
  const emailWorks = $derived(Boolean(me?.sign_in?.email));
  let confirmRemove = $state<string | null>(null);
  let notice = $state<string | null>(null);
  const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : null);
  const used = (k: Passkey) => (k.last_used_at ? `last used ${day(k.last_used_at)}` : "not used to sign in yet");

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
    const adding = Boolean(st?.signed_in && me && !me.email); // ---- IM-4: the link adds the email to this account
    const ok = await run(() => verifyLink(t));
    dropLinkToken();
    token = null;
    if (ok) {
      gone = false;
      sentTo = null;
      if (adding) notice = "Your email is added: it is a second way into your account.";
    }
  }

  async function leave(everywhere: boolean) {
    if (await run(() => signOut(everywhere))) sentTo = null;
  }

  // ---- IM-4: the passkey buttons (each opens the device's own sheet)
  async function passkey(fn: () => Promise<unknown>, done: string | null) {
    notice = null;
    if (await run(fn)) {
      gone = false;
      sentTo = null;
      notice = done;
    }
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
    {:else if token && me && !me.email}
      <!-- ---- IM-4: a passkey-only account opened the link it asked for: one tap adds the address -->
      <section class="space-y-3 rounded-lg border border-line bg-surface p-4" data-testid="link-add">
        <p class="text-base">Add this email to your {APP_NAME} account?</p>
        <button class="w-full rounded-md bg-accent px-4 py-3 font-bold text-on-accent disabled:opacity-60" disabled={busy} onclick={useLink} data-testid="link-add-go"
          >Add my email</button
        >
      </section>
    {:else if !st.signed_in || !me}
      {#if gone}
        <p class="text-base text-ink-2" data-testid="account-deleted">Your account is deleted. The leagues on this device stay here.</p>
      {/if}
      <!-- ---- IM-4: passkeys first when the server has them (no email, nothing typed) -->
      {#if passkeyOn && !sentTo}
        <section class="space-y-3" data-testid="passkey-start">
          <p class="text-base text-ink-2">An account keeps your leagues, your team in each and your saved Stats views, on any phone or computer.</p>
          {#if st.passkey_here === false}
            <p class="rounded-md bg-surface px-3 py-2 text-base" data-testid="passkey-elsewhere">
              Passkeys work on {homeHost} only. <a class="ll-link" href={`${home}/account`}>Open {homeHost}</a> to use one.
            </p>
          {:else if blocked !== null}
            <p class="rounded-md bg-surface px-3 py-2 text-base" data-testid="passkey-unsupported">
              This browser cannot use passkeys (an app's built-in browser often cannot). Open {homeHost} in Safari, Chrome, Edge or Firefox to use one.
            </p>
          {:else}
            <button class="w-full rounded-md bg-accent px-4 py-3 font-bold text-on-accent disabled:opacity-60" disabled={busy} onclick={() => passkey(createWithPasskey, "Your account is made and this device's leagues are saved to it.")} data-testid="passkey-create"
              >Create an account with a passkey</button
            >
            <p class="text-sm text-ink-3">A passkey is your phone's or computer's own lock: Face ID, a fingerprint or its PIN. No password, no email.</p>
            <button class="w-full rounded-md border border-line bg-surface px-4 py-3 font-bold disabled:opacity-60" disabled={busy} onclick={() => passkey(signInWithPasskey, null)} data-testid="passkey-signin"
              >Sign in with a passkey</button
            >
          {/if}
        </section>
      {/if}
      {#if !emailOn}
        <p class="text-sm text-ink-3">You can keep using {APP_NAME} without an account: your leagues stay on this device.</p>
      {:else if sentTo}
        <section class="space-y-2" data-testid="link-sent" role="status">
          <p class="text-base font-semibold">Check your email.</p>
          <p class="text-base text-ink-2">
            A sign-in link is on its way to <strong>{sentTo}</strong>. It works once, for 15 minutes, on the device you open it on.
          </p>
          <button class="ll-link py-1 text-base" onclick={() => (sentTo = null)} data-testid="link-again">Use another address</button>
        </section>
      {:else}
        <form class="space-y-3" class:border-t={passkeyOn} class:border-line={passkeyOn} class:pt-4={passkeyOn} onsubmit={ask} data-testid="signin-form">
          {#if passkeyOn}
            <h2 class="ll-label">Or use your email</h2>
            <p class="text-base text-ink-2">No password: we email you a link.</p>
          {:else}
            <p class="text-base text-ink-2">
              An account keeps your leagues, your team in each and your saved Stats views, on any phone or computer. No password: we email you a
              link.
            </p>
          {/if}
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
      {#if me.email}
        <p class="text-base text-ink-2" data-testid="account-email-line">Signed in as <strong>{me.email}</strong>.</p>
      {:else}
        <p class="text-base text-ink-2" data-testid="account-email-line">Signed in with a passkey.</p>
      {/if}
      {#if notice}
        <p class="rounded-md bg-accent-soft px-3 py-2 text-sm font-semibold" role="status" data-testid="account-notice-line">{notice}</p>
      {/if}

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
            {#each me.leagues as l, ix (`${l.league_key}#${ix}`)}
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

      <!-- ---- IL-5 (Wave I-L): the watchlist and the connections the account keeps (never a token) -->
      <section class="space-y-2" data-testid="account-more">
        <h2 class="ll-label">Players and connections</h2>
        <p class="text-base text-ink-2">
          <a class="ll-link" href={current ? withContext("/watchlist", { league: current, team: null }) : "/watchlist"} data-testid="account-watchlist"
            >Your watchlist</a
          >: {nWatch === 1 ? "1 player" : `${nWatch} players`}.
        </p>
        {#each me.connections ?? [] as c, ix (`${c.provider}|${c.external_user_id}#${ix}`)}
          <p class="text-base text-ink-2" data-testid="account-connection" data-provider={c.provider} data-status={c.status}>
            {c.provider === "yahoo" ? "Yahoo" : "ESPN"}: {c.status === "active"
              ? `connected${c.connected_at ? ` ${c.connected_at.slice(0, 10)}` : ""} — it comes back on any device you sign in on.`
              : "needs reconnecting (it no longer opens your leagues)."}
            {#if c.status !== "active"}<a class="ll-link" href={`/leagues?platform=${c.provider}`} data-testid="account-reconnect">Reconnect {c.provider === "yahoo" ? "Yahoo" : "ESPN"}</a>{/if}
          </p>
        {:else}
          <p class="text-sm text-ink-3" data-testid="account-no-connection">No Yahoo or ESPN connection saved. Connect one on the league setup screen while signed in and it follows you.</p>
        {/each}
      </section>
      <!-- ---- end IL-5 -->

      <!-- ---- IM-4: the passkeys (labels and dates only), add one, remove one (never the only way in) -->
      {#if passkeyOn || keys.length}
        <section class="space-y-2" data-testid="passkeys">
          <h2 class="ll-label">Passkeys</h2>
          {#if keys.length}
            <ul class="divide-y divide-line rounded-lg border border-line bg-surface">
              {#each keys as k, ix (`${k.id}#${ix}`)}
                {@const last = keys.length === 1 && !emailWorks}
                <li class="flex items-center justify-between gap-3 px-3 py-3" data-testid="passkey-row" data-label={k.label}>
                  <div class="min-w-0">
                    <p class="truncate text-base font-semibold">{k.label}</p>
                    <p class="text-xs text-ink-3">added {day(k.created_at)} · {used(k)}</p>
                  </div>
                  {#if last}
                    <span class="shrink-0 text-xs text-ink-3" data-testid="passkey-only">Your only way in</span>
                  {:else if confirmRemove === k.id}
                    <span class="flex shrink-0 gap-3 text-sm">
                      <button class="min-h-9 font-bold text-bad underline" disabled={busy} onclick={async () => { if (await run(() => removePasskey(k.id))) confirmRemove = null; }} data-testid="passkey-remove-go">Remove</button>
                      <button class="min-h-9 underline" onclick={() => (confirmRemove = null)}>Keep</button>
                    </span>
                  {:else}
                    <button class="min-h-9 shrink-0 text-sm text-ink-3 underline" disabled={busy} onclick={() => (confirmRemove = k.id)} data-testid="passkey-remove">Remove</button>
                  {/if}
                </li>
              {/each}
            </ul>
            {#if confirmRemove}
              <p class="text-sm text-ink-2" data-testid="passkey-remove-note">It stays in that device's passkey list until you delete it there, but it no longer opens this account.</p>
            {/if}
          {:else}
            <p class="text-base text-ink-2" data-testid="passkeys-none">No passkey yet. Add one to sign in with this device's own lock instead of an email.</p>
          {/if}
          {#if canPasskey}
            <button class="rounded-md border border-line bg-surface px-4 py-2.5 font-bold disabled:opacity-60" disabled={busy} onclick={() => passkey(addPasskey, "Passkey added.")} data-testid="passkey-add"
              >{keys.length ? "Add another passkey" : "Add a passkey"}</button
            >
          {:else if passkeyOn && st.passkey_here === false}
            <p class="text-sm text-ink-3" data-testid="passkey-elsewhere">Passkeys work on {homeHost} only. <a class="ll-link" href={`${home}/account`}>Open {homeHost}</a> to add one.</p>
          {:else if passkeyOn && blocked !== null}
            <p class="text-sm text-ink-3" data-testid="passkey-unsupported">This browser cannot make passkeys. Open {homeHost} in Safari, Chrome, Edge or Firefox to add one.</p>
          {/if}
          {#if keys.length && !emailWorks}
            <p class="text-sm text-ink-3" data-testid="passkey-recovery">
              If you lose every device that holds your passkeys, this account cannot be recovered: add one on a second device{emailOn && !me.email
                ? ", or add your email below"
                : ""}.
            </p>
          {/if}
          {#if emailOn && !me.email}
            {#if sentTo}
              <p class="text-base text-ink-2" role="status" data-testid="email-add-sent">
                Check your email: open the link on this device to add <strong>{sentTo}</strong> to your account. It works once, for 15 minutes.
              </p>
            {:else}
              <form class="flex flex-wrap items-end gap-2 pt-1" onsubmit={ask} data-testid="email-add">
                <label class="ll-label w-full" for="account-add-email">Add an email</label>
                <input
                  id="account-add-email"
                  class="ll-input min-w-0 flex-1 py-2.5"
                  type="email"
                  autocomplete="email"
                  inputmode="email"
                  placeholder="you@example.com"
                  bind:value={email}
                  data-testid="email-add-input"
                />
                <button class="rounded-md border border-line bg-surface px-4 py-2.5 font-bold disabled:opacity-60" disabled={busy || !email.trim()} data-testid="email-add-go"
                  >Email me a link</button
                >
              </form>
            {/if}
          {/if}
        </section>
      {/if}
      <!-- ---- end IM-4 -->

      <section class="space-y-3 border-t border-line pt-4">
        <div class="flex flex-wrap gap-x-5 gap-y-2 text-base">
          <button class="ll-link min-h-11" disabled={busy} onclick={() => leave(false)} data-testid="signout">Sign out</button>
          <button class="ll-link min-h-11" disabled={busy} onclick={() => leave(true)} data-testid="signout-all">Sign out everywhere</button>
        </div>
        {#if !confirmDelete}
          <button class="min-h-11 text-sm text-bad underline" onclick={() => (confirmDelete = true)} data-testid="delete-ask">Delete my account</button>
        {:else}
          <div class="space-y-2 rounded-lg border border-bad p-3" data-testid="delete-confirm">
            <p class="text-sm">This deletes your email address, your saved leagues and your preferences from {APP_NAME} now. Your watchlist, your passkeys and any Yahoo or ESPN connection go too. The leagues on this device stay.</p>
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
      An account keeps your email address if you give one, the names of your passkeys (never anything that unlocks your device), the leagues and teams
      you save, your saved views and watchlist, and a Yahoo or ESPN connection only if you make one (encrypted) — nothing else. Signing in keeps you signed in on that device for {st.session_days}
      days.
    </p>
  {/if}
</main>
