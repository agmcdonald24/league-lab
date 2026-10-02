<script lang="ts">
  // A row of filter chips (position, scope): one tap, aria-pressed, fits 390 px (wraps).
  let {
    items,
    current,
    onpick,
    label,
    testid = "chips",
  }: { items: { key: string; label: string }[]; current: string; onpick: (key: string) => void; label: string; testid?: string } = $props();
</script>

<div class="flex flex-wrap gap-1.5" role="group" aria-label={label} data-testid={testid}>
  {#each items as it (it.key)}
    <button
      type="button"
      class="inline-flex min-h-9 items-center rounded-full border px-3 text-sm font-semibold {it.key === current
        ? 'border-accent bg-accent text-on-accent'
        : 'border-line-strong text-ink-2 hover:text-ink'}"
      aria-pressed={it.key === current}
      onclick={() => onpick(it.key)}
      data-testid={`${testid}-${it.key}`}>{it.label}</button
    >
  {/each}
</div>
