<script lang="ts">
  // A position chip: the position's color as a wash and a dot, the text in ink (text never wears the data color).
  import { positionColor } from "../lib/theme";

  let { pos, size = "sm" }: { pos: string | null | undefined; size?: "sm" | "md" } = $props();
  const c = $derived(positionColor(pos));
</script>

{#if pos}
  <span
    class="inline-flex items-center gap-1 rounded-sm font-semibold tracking-wide text-ink {size === 'md' ? 'px-2 py-0.5 text-sm' : 'px-1.5 text-[11px] leading-[18px]'}"
    style="background:color-mix(in oklab, {c} 22%, transparent)"
    data-testid="pos-badge"
  >
    <span class="inline-block h-1.5 w-1.5 rounded-full" style="background:{c}" aria-hidden="true"></span>{pos}
  </span>
{/if}
