<script lang="ts">
  // A segmented row of choices. With `href` each choice is a real link (one tap, one history entry, shareable); without,
  // a button (`onpick`) with aria-pressed. Fits 390 px: the choices share the row (`fill`) or wrap.
  export interface TabItem {
    key: string;
    label: string;
    href?: string;
    badge?: string;
  }

  let {
    items,
    current,
    onpick,
    fill = false,
    size = "md",
    label = "Choices",
    testid = "tabs",
  }: {
    items: TabItem[];
    current: string;
    onpick?: (key: string) => void;
    fill?: boolean;
    size?: "sm" | "md";
    label?: string;
    testid?: string;
  } = $props();

  const base = $derived(
    `inline-flex items-center justify-center gap-1 rounded-sm font-semibold whitespace-nowrap transition-colors ${size === "sm" ? "min-h-8 px-2.5 text-sm" : "min-h-9 px-3 text-base"} ${fill ? "flex-1" : ""}`,
  );
  const on = "bg-accent text-on-accent";
  const off = "text-ink-2 hover:bg-raised hover:text-ink";
</script>

<nav class="flex {fill ? '' : 'flex-wrap'} gap-1 rounded-md border border-line bg-surface p-1" aria-label={label} data-testid={testid}>
  {#each items as t, ix (`${t.key}#${ix}`)}
    {#if t.href}
      <a
        href={t.href}
        class="{base} {t.key === current ? on : off}"
        aria-current={t.key === current ? "page" : undefined}
        data-testid={`${testid}-${t.key}`}
        >{t.label}{#if t.badge}<span class="text-[10px] font-medium opacity-70">{t.badge}</span>{/if}</a
      >
    {:else}
      <button
        type="button"
        class="{base} {t.key === current ? on : off}"
        aria-pressed={t.key === current}
        onclick={() => onpick?.(t.key)}
        data-testid={`${testid}-${t.key}`}>{t.label}</button
      >
    {/if}
  {/each}
</nav>
