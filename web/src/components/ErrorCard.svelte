<script lang="ts">
  // ---- IH-1 (Wave I-H): the error states a screen did not have — a plain card with what happened and a way out,
  // never a spinner forever. `failure` from lib/remote.svelte.ts (`failureOf`, or a Remote's `failure`); `onretry`
  // asks again (Remote.retry, or the screen's own reload). A 500 names the status page (/api/status: whether the data
  // is up, when it was last updated); the API down says so in words and offers Try again.
  import { STATUS_PATH, type Failure } from "../lib/remote.svelte";
  import { track } from "../lib/analytics"; // ---- IN-5

  // ---- IN-5 (Wave I-N): `crashed` = the name of a screen that hit a render error (App.svelte's <svelte:boundary>): "This
  // screen hit a problem" + Reload, and the screen's name to analytics as an `exception` event (no message, no data)
  let {
    failure = null,
    onretry,
    compact = false,
    crashed = null,
  }: { failure?: Failure | null; onretry?: () => void; compact?: boolean; crashed?: string | null } = $props();
  const CRASH: Failure = { kind: "other", status: null, words: "Something on this screen did not load. Reload the page; the other screens still work." };
  const f = $derived(crashed !== null ? CRASH : (failure ?? CRASH));
  $effect(() => {
    if (crashed !== null) track("exception", { description: `screen: ${crashed}`, fatal: false, screen_name: crashed });
  });
  // ---- end IN-5

  // a title only where the words do not already say it (the words stand alone on the screens that show a plain line)
  const TITLE: Partial<Record<Failure["kind"], string>> = {
    slow: "Still waiting",
    server: "Something broke on our side",
  };
  const title = $derived(crashed !== null ? "This screen hit a problem" : (TITLE[f.kind] ?? null)); // IN-5: crashed
  const showStatus = $derived(f.kind === "server" || f.kind === "notready");
</script>

<div
  class="space-y-2 rounded-lg border border-line bg-surface {compact ? 'p-3' : 'p-4'}"
  style="box-shadow:var(--ll-shadow)"
  role="alert"
  data-testid="error-card"
  data-kind={crashed !== null ? "crashed" : f.kind}
  data-screen={crashed}
>
  {#if f.kind === "needsleague"}
    <!-- ---- IM-3: a screen that needs a league, asked without one (`ref:` keys): the invitation, not a warning -->
    <p class="text-base font-bold" data-testid="error-words">{f.words}</p>
    <a href="/leagues" class="inline-flex min-h-11 items-center rounded-md bg-accent px-4 font-semibold text-on-accent" data-testid="invite-open">Open your league</a>
  {:else if title}
    <p class="flex items-center gap-2 text-base font-bold" data-testid="error-title">
      <span class={f.kind === "slow" ? "text-ink-3" : "text-warn"} aria-hidden="true">{f.kind === "slow" ? "…" : "⚠︎"}</span>{title}
    </p>
    <p class="leading-snug text-ink-2" data-testid="error-words">{f.words}</p>
  {:else}
    <p class="flex items-start gap-2 leading-snug font-semibold" data-testid="error-words">
      <span class="text-warn" aria-hidden="true">⚠︎</span><span>{f.words}</span>
    </p>
  {/if}
  {#if showStatus}
    <p class="text-sm text-ink-3" data-testid="error-status">
      The status page: <a class="ll-link" href={STATUS_PATH} target="_blank" rel="noopener" data-testid="error-status-link">{STATUS_PATH}</a>
    </p>
  {/if}
  {#if crashed !== null}
    <!-- ---- IN-5: a render error: the page again (the screen's state is gone; a new mount reads the answers anew) -->
    <button type="button" class="min-h-11 rounded-md bg-accent px-4 py-2 font-semibold text-on-accent" onclick={() => location.reload()} data-testid="error-reload"
      >Reload</button
    >
  {:else if onretry && f.kind !== "needsleague"}
    <button
      type="button"
      class="min-h-11 rounded-md bg-accent px-4 py-2 font-semibold text-on-accent"
      onclick={() => onretry?.()}
      data-testid="error-retry">Try again</button
    >
  {/if}
</div>
