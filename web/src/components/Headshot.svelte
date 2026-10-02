<script lang="ts">
  // A player's face (dim_player.headshot_url) on his team's color, or a silhouette when there is no picture or it
  // fails to load. Lazy: a list of 50 rows does not fetch 50 pictures before the first screen.
  import { team as teamColors } from "../lib/theme";

  let {
    url = null,
    name = "",
    team = null,
    size = 40,
    eager = false,
  }: { url?: string | null; name?: string; team?: string | null; size?: number; eager?: boolean } = $props();

  let failed = $state(false);
  const accent = $derived(teamColors(team).accent);
  $effect(() => {
    void url;
    failed = false;
  });
</script>

<span
  class="relative inline-flex shrink-0 items-end justify-center overflow-hidden rounded-full bg-raised ring-1 ring-line"
  style="width:{size}px;height:{size}px;background-image:radial-gradient(circle at 50% 110%, color-mix(in oklab, {accent} 55%, transparent) 0%, transparent 70%)"
  data-testid="headshot"
>
  {#if url && !failed}
    <img
      src={url}
      alt=""
      width={size}
      height={size}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      referrerpolicy="no-referrer"
      class="h-full w-full object-cover object-top"
      onerror={() => (failed = true)}
    />
  {:else}
    <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden="true" class="text-ink-3" data-testid="silhouette">
      <circle cx="20" cy="15" r="7.5" fill="currentColor" opacity="0.55" />
      <path d="M5 40c1.5-9 7.5-14 15-14s13.5 5 15 14z" fill="currentColor" opacity="0.55" />
    </svg>
  {/if}
  <span class="sr-only">{name}</span>
</span>
