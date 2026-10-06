<script lang="ts">
  // ---- IN-2 (Wave I-N): the scoring picker while browsing without a league — where the league picker is. A compact
  // button ("Half PPR ▾"; on a phone "PPR +2") opens a panel: the scoring (PPR · Half PPR · Standard · ESPN default ·
  // Yahoo default, the picked one's rules in a line, and why there is no "Sleeper" preset), the options (superflex, TE
  // premium, 6-pt pass TD) and the league size (8 · 10 · 12 · 14). Every change rewrites the URL's `league=` in place
  // and is remembered on this device (`prefs.setRefKey`); "Open your league" stays one tap away beside it.
  import { prefs } from "../../lib/prefs";
  import { setParams } from "../../lib/router.svelte";
  import { parseRef, REF_BASES, REF_DEFAULT, REF_OPTIONS, REF_TEAMS, refKey, refLabel, refShort, SLEEPER_WORDS, type RefShape } from "../../lib/refleague";

  let { league }: { league: string } = $props();

  const shape = $derived<RefShape>(parseRef(league) ?? parseRef(REF_DEFAULT)!);
  let open = $state(false);
  let box = $state<HTMLElement | null>(null);
  let button = $state<HTMLButtonElement | null>(null);

  function pick(next: Partial<RefShape>) {
    const k = refKey({ ...shape, ...next });
    prefs.setRefKey(k);
    setParams({ league: k, team: null });
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "Escape" && open) {
      open = false;
      button?.focus();
    }
  }

  function onDoc(e: MouseEvent) {
    if (open && box && !box.contains(e.target as Node)) open = false;
  }

  const rules = $derived(REF_BASES.find((b) => b.id === shape.base)?.rules ?? "");
</script>

<svelte:window onkeydown={onKey} onclick={onDoc} />

<div class="relative flex min-w-0 items-center gap-2" bind:this={box} data-testid="ref-picker">
  <button
    type="button"
    bind:this={button}
    class="ll-input inline-flex min-h-10 min-w-0 shrink items-center gap-1.5 py-1.5 text-sm font-semibold"
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls="ll-scoring-panel"
    onclick={() => (open = !open)}
    data-testid="ref-button"
  >
    <span class="sr-only">Scoring:</span>
    <span class="truncate sm:hidden" data-testid="ref-short">{refShort(league)}</span>
    <span class="hidden truncate sm:inline" data-testid="ref-label">{refLabel(league)}</span>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true" class="shrink-0"><path d="M6 9l6 6 6-6" /></svg>
  </button>
  <a href="/leagues" class="inline-flex min-h-10 shrink-0 items-center rounded-md bg-accent px-3 text-sm font-semibold whitespace-nowrap text-on-accent" data-testid="ref-open"
    >Open your league</a
  >

  {#if open}
    <div
      id="ll-scoring-panel"
      role="dialog"
      aria-label="Scoring"
      class="fixed inset-x-2 top-14 z-50 max-h-[80dvh] overflow-y-auto rounded-lg border border-line bg-surface p-4 shadow-lg wide:absolute wide:inset-x-auto wide:top-full wide:right-0 wide:mt-1 wide:w-[26rem]"
      data-testid="ref-panel"
    >
      <fieldset class="space-y-2">
        <legend class="ll-label mb-1 text-ink-3">Scoring</legend>
        <div class="flex flex-wrap gap-1.5">
          {#each REF_BASES as b (b.id)}
            {@const on = shape.base === b.id}
            <button
              type="button"
              class="min-h-10 rounded-full border px-3 text-sm font-semibold {on ? 'border-accent bg-accent-soft text-ink' : 'border-line text-ink-2 hover:text-ink'}"
              aria-pressed={on}
              onclick={() => pick({ base: b.id })}
              data-testid={`ref-base-${b.id}`}>{b.label}</button
            >
          {/each}
        </div>
        <p class="text-sm text-ink-2" data-testid="ref-rules">{rules}</p>
        <p class="text-xs text-ink-3" data-testid="ref-sleeper">{SLEEPER_WORDS}</p>
      </fieldset>

      <fieldset class="mt-4 space-y-1">
        <legend class="ll-label mb-1 text-ink-3">Options</legend>
        {#each REF_OPTIONS as o (o.id)}
          <label class="flex min-h-10 cursor-pointer items-center gap-2.5 text-sm" data-testid={`ref-opt-${o.id}`}>
            <input type="checkbox" class="h-5 w-5 shrink-0 accent-[var(--ll-accent)]" checked={shape[o.id]} onchange={(e) => pick({ [o.id]: e.currentTarget.checked })} />
            <span class="font-semibold">{o.label}</span>
            <span class="text-ink-3">{o.help}</span>
          </label>
        {/each}
      </fieldset>

      <fieldset class="mt-4">
        <legend class="ll-label mb-1 text-ink-3">League size</legend>
        <div class="flex gap-1.5">
          {#each REF_TEAMS as t (t)}
            {@const on = shape.teams === t}
            <button
              type="button"
              class="min-h-10 flex-1 rounded-md border text-sm font-semibold tabnum {on ? 'border-accent bg-accent-soft text-ink' : 'border-line text-ink-2 hover:text-ink'}"
              aria-pressed={on}
              onclick={() => pick({ teams: t })}
              data-testid={`ref-teams-${t}`}>{t} teams</button
            >
          {/each}
        </div>
        <p class="mt-2 text-xs text-ink-3">The size and superflex change a player's value (who is left on waivers), not his points.</p>
      </fieldset>

      <div class="mt-4 flex items-center justify-between gap-2 border-t border-line pt-3">
        <a href="/leagues" class="ll-link text-sm font-semibold" data-testid="ref-panel-open">Open your league</a>
        <button type="button" class="min-h-10 rounded-md border border-line px-4 text-sm font-semibold" onclick={() => (open = false)} data-testid="ref-done">Done</button>
      </div>
    </div>
  {/if}
</div>
