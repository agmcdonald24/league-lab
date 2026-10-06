<script lang="ts">
  // ---- IL-5 (Wave I-L): the watchlist — the players the signed-in person saved with Watch on any player's card.
  // Each row is the player as his card has him in the league on screen (GET /api/account/watchlist?league=&team=):
  // his name, position and NFL team, his status today (the injury report after the availability overlay), this week's
  // projected points in this league's scoring, and where he is in this league (free agent / rostered by whom / yours).
  // A name opens the drawer (II-2's link hook); Remove takes him off. Signed out: one line to sign in (not a wall);
  // accounts off on the server: one line.
  import { account, AccountError, GateClosed, loadStatus } from "../lib/account.svelte";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { fmt } from "../lib/theme";
  import { loadWatchlist, unwatch, type WatchAnswer, type WatchRow } from "../lib/watchlist.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<WatchAnswer | null>(null);
  let failed = $state<string | null>(null);
  let busy = $state<string | null>(null);
  let ready = $state(false);

  const name = $derived(options.find((o) => o.league_id === league)?.name ?? data?.league_name ?? "this league");
  const signedIn = $derived(!!(account.status?.enabled && account.status.signed_in));
  // the rows the account still holds (a Remove here, or Watch / Watching in the drawer, changes account.me at once)
  const kept = $derived(new Set((account.me?.watchlist ?? []).map((w) => w.player_key)));
  const rows = $derived((data?.players ?? []).filter((p) => kept.has(p.player_key)));
  const ctx = $derived({ league, team });

  // read again when the league or team changes, or when a player was added (Watch in the drawer, on this screen); a
  // removal needs no read (`rows` follows the account at once)
  let askedFor = "";
  $effect(() => {
    const lt = `${league}|${team ?? ""}`;
    const keys = (account.me?.watchlist ?? []).map((w) => w.player_key);
    void loadStatus().then(async (s) => {
      ready = true;
      if (!s.enabled || !s.signed_in || !account.me) return;
      const missing = keys.some((k) => !data?.players.some((p) => p.player_key === k));
      if (lt === askedFor && !missing) return;
      askedFor = lt;
      failed = null;
      try {
        data = await loadWatchlist(league, team);
      } catch (e) {
        if (e instanceof GateClosed) onauth();
        else failed = e instanceof AccountError ? e.message : "Could not read your watchlist. Try again in a minute.";
      }
    });
  });

  async function remove(p: WatchRow) {
    busy = p.player_key;
    try {
      await unwatch(p.player_key, "watchlist");
    } catch {
      failed = "Not removed: try again in a minute.";
    } finally {
      busy = null;
    }
  }

  const statusWords = (p: WatchRow) => p.status ?? "No injury designation";
  const statusTone = (s: string | null) => (s === null ? "text-ink-3" : /out|ir|doubtful|suspend/i.test(s) ? "text-bad" : "text-warn");
  const projWords = (p: WatchRow) => (p.proj_points === null ? "not projected this week" : `${fmt.pts(p.proj_points)} projected`);
</script>

<main class="space-y-4" data-testid="watchlist">
  <ScreenHead eyebrow={`Watchlist · ${name}`} title="Watchlist">
    {#snippet answer()}
      {#if !ready}
        Loading…
      {:else if !account.status?.enabled}
        <span data-testid="watchlist-off">A watchlist comes with an account, and accounts are not on for this server yet.</span>
      {:else if !signedIn}
        <span data-testid="watchlist-signin"
          >Sign in to keep a watchlist on any device: <a class="ll-link font-semibold" href="/account" data-testid="watchlist-signin-link">sign in or make an account</a>, then tap
          ☆ Watch on any player's card.</span
        >
      {:else if data && rows.length}
        <span data-testid="watchlist-stamp"
          >{rows.length === 1 ? "1 player" : `${rows.length} players`}{data.count > data.shown ? ` (the first ${data.shown} of ${data.count})` : ""} · projected points in {data.league_name ??
            name} scoring{data.week ? `, week ${data.week}` : ""}. Tap a name for his card.</span
        >
      {:else if data}
        <span data-testid="watchlist-empty">No players on your watchlist yet. Open any player's card and tap ☆ Watch.</span>
      {:else if !failed}
        Reading your watchlist…
      {/if}
    {/snippet}
  </ScreenHead>

  {#if failed}<p class="text-base text-bad" role="alert" data-testid="watchlist-error">{failed}</p>{/if}

  {#if signedIn && !data && !failed}
    <div class="space-y-2" aria-label="Loading" data-testid="watchlist-loading"><div class="ll-skel h-16"></div><div class="ll-skel h-16"></div></div>
  {/if}

  {#if signedIn && rows.length}
    <ul class="grid gap-2 wide:grid-cols-2" data-testid="watchlist-rows">
      {#each rows as p (p.player_key)}
        <li
          class="flex items-start gap-3 rounded-lg border border-line bg-surface p-3"
          style="box-shadow:var(--ll-shadow)"
          data-testid="watchlist-row"
          data-player={p.player_key}
          data-owner={p.owner?.kind ?? "unread"}
        >
          <div class="min-w-0 flex-1 space-y-0.5">
            {#if p.read}
              <a class="ll-name text-lg leading-snug font-bold break-words" href={withContext(`/player/${encodeURIComponent(p.player_key)}`, ctx)} data-testid="watchlist-name"
                >{p.player_name}</a
              >
              <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-ink-2">
                <PosBadge pos={p.position} />
                <span>{p.team ?? "no NFL team"}</span>
                <span class="font-semibold {statusTone(p.status)}" data-testid="watchlist-status">{statusWords(p)}</span>
              </div>
              <div class="text-sm leading-snug text-ink-2">
                <span class="font-semibold text-ink tabular-nums" data-testid="watchlist-proj">{projWords(p)}</span>{p.proj_points !== null && p.week ? ` · week ${p.week}` : ""}
                · <span data-testid="watchlist-owner">{p.owner?.words ?? ""}</span>
              </div>
            {:else}
              <div class="font-mono text-sm text-ink-2">{p.player_key}</div>
              <div class="text-sm text-ink-3" data-testid="watchlist-unread">Not read: {p.words ?? "try again in a minute"}.</div>
            {/if}
          </div>
          <button
            type="button"
            class="inline-flex min-h-11 shrink-0 items-center rounded-md border border-line-strong px-3 text-sm font-semibold text-ink disabled:opacity-60"
            disabled={busy === p.player_key}
            aria-label={`Remove ${p.player_name ?? p.player_key} from your watchlist`}
            onclick={() => remove(p)}
            data-testid="watchlist-remove">Remove</button
          >
        </li>
      {/each}
    </ul>
  {/if}
</main>
