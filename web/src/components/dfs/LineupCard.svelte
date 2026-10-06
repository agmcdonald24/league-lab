<script lang="ts">
  // ---- IM-5: one built lineup — its players by slot, the salary left, the projected total and its range, Copy.
  import { fmt } from "../../lib/theme";
  import { withContext } from "../../lib/md";
  import { money, type Lineup } from "./dfs";

  let { lineup, index, cap, league, team, site }: { lineup: Lineup; index: number; cap: number; league: string | null; team: number | null; site: string } =
    $props();
  let copied = $state(false);

  const slotWord = (s: string, pos: string) => (s === "DST" || s === "DEF" ? (site === "dk" ? "DST" : "DEF") : s === "FLEX" && pos ? `FLEX` : s);
  function text(): string {
    const rows = lineup.slots.map((s) => `${s.slot}\t${s.name ?? s.key}\t${s.team ?? ""}\t${money(s.salary)}\t${fmt.pts(s.proj)}`);
    return [`Lineup ${index + 1}: ${fmt.pts(lineup.proj)} projected, ${money(lineup.salary)} of ${money(cap)}`, ...rows].join("\n");
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(text());
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }
</script>

<article class="min-w-0 rounded-lg border border-line bg-surface p-3" style="box-shadow:var(--ll-shadow)" data-testid="dfs-lineup">
  <header class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
    <h3 class="text-base font-bold">Lineup {index + 1}</h3>
    <p class="text-sm text-ink-2">
      <span class="tabnum font-bold text-ink" data-testid="dfs-lineup-proj">{fmt.pts(lineup.proj)}</span> projected ·
      <span class="tabnum">{money(lineup.salary_left)}</span> left
    </p>
  </header>
  <ul class="mt-2 divide-y divide-line">
    {#each lineup.slots as s, i (i)}
      <li class="flex items-center gap-2 py-1.5 text-sm">
        <span class="w-10 shrink-0 text-xs font-bold text-ink-3">{slotWord(s.slot, s.position)}</span>
        <span class="min-w-0 flex-1 truncate">
          {#if s.gsis_id && league}
            <a class="ll-link font-semibold" href={withContext(`/player/${s.gsis_id}`, { league, team })}>{s.name}</a>
          {:else}
            <span class="font-semibold">{s.name}</span>
          {/if}
          <span class="text-ink-3"> · {s.team ?? ""}{s.multiplier !== 1 ? " · ×1.5" : ""}</span>
        </span>
        <span class="tabnum w-16 shrink-0 text-right text-ink-2">{money(s.salary)}</span>
        <span class="tabnum w-10 shrink-0 text-right font-semibold">{fmt.pts(s.proj)}</span>
      </li>
    {/each}
  </ul>
  <p class="mt-2 text-sm text-ink-3" data-testid="dfs-lineup-range">
    {#if lineup.low !== null && lineup.high !== null}
      Low-end to high-end outcome: <span class="tabnum">{fmt.pts(lineup.low)}–{fmt.pts(lineup.high)}</span> (if the players' weeks were independent; teammates
      and opponents move together, so the real range is wider).
    {:else}
      No range: a player has no low-end or high-end outcome.
    {/if}
    {#if !lineup.proven}<br />The solver's budget ran out: the best lineup it found, not proven the best.{/if}
  </p>
  <button type="button" class="mt-2 min-h-9 rounded-md border border-line-strong px-3 text-sm font-semibold text-ink-2 hover:text-ink" onclick={copy} data-testid="dfs-copy"
    >{copied ? "Copied" : "Copy"}</button
  >
</article>
