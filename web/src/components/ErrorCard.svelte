<script lang="ts">
  // ---- IH-1 (Wave I-H): the error states a screen did not have — a plain card with what happened and a way out,
  // never a spinner forever. `failure` from lib/remote.svelte.ts (`failureOf`, or a Remote's `failure`); `onretry`
  // asks again (Remote.retry, or the screen's own reload). A 500 names the status page (/api/status: whether the data
  // is up, when it was last updated); the API down says so in words and offers Try again.
  import { STATUS_PATH, type Failure } from "../lib/remote.svelte";

  let { failure, onretry, compact = false }: { failure: Failure; onretry?: () => void; compact?: boolean } = $props();

  // a title only where the words do not already say it (the words stand alone on the screens that show a plain line)
  const TITLE: Partial<Record<Failure["kind"], string>> = {
    slow: "Still waiting",
    server: "Something broke on our side",
  };
  const title = $derived(TITLE[failure.kind] ?? null);
  const showStatus = $derived(failure.kind === "server" || failure.kind === "notready");
</script>

<div
  class="space-y-2 rounded-lg border border-line bg-surface {compact ? 'p-3' : 'p-4'}"
  style="box-shadow:var(--ll-shadow)"
  role="alert"
  data-testid="error-card"
  data-kind={failure.kind}
>
  {#if title}
    <p class="flex items-center gap-2 text-base font-bold" data-testid="error-title">
      <span class={failure.kind === "slow" ? "text-ink-3" : "text-warn"} aria-hidden="true">{failure.kind === "slow" ? "…" : "⚠︎"}</span>{title}
    </p>
    <p class="leading-snug text-ink-2" data-testid="error-words">{failure.words}</p>
  {:else}
    <p class="flex items-start gap-2 leading-snug font-semibold" data-testid="error-words">
      <span class="text-warn" aria-hidden="true">⚠︎</span><span>{failure.words}</span>
    </p>
  {/if}
  {#if showStatus}
    <p class="text-sm text-ink-3" data-testid="error-status">
      The status page: <a class="ll-link" href={STATUS_PATH} target="_blank" rel="noopener" data-testid="error-status-link">{STATUS_PATH}</a>
    </p>
  {/if}
  {#if onretry}
    <button
      type="button"
      class="min-h-11 rounded-md bg-accent px-4 py-2 font-semibold text-on-accent"
      onclick={() => onretry?.()}
      data-testid="error-retry">Try again</button
    >
  {/if}
</div>
