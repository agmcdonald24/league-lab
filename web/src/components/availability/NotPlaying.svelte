<script lang="ts">
  // ---- IR-1 (Wave I-R): who is not on a list because he cannot play — the status, its source and time, the reason in
  // words; never a number (a dash). Rankings, rest of season, the matchup board.
  // ---- IS-1 (Wave I-S): two labelled parts when both exist — "Out" (cannot play) and "Unlikely to play" (a status
  // whose players rarely play: Doubtful); the server orders each part so the players a visitor looks for lead.
  import type { NotPlaying } from "../../lib/api";
  import { openPane } from "../../lib/pane.svelte";
  import { teamLabel } from "../../lib/theme";
  import Headshot from "../Headshot.svelte";

  let { rows, words = null, testid = "not-playing" }: { rows: NotPlaying[]; words?: string | null; testid?: string } = $props();

  const PARTS: { key: "out" | "unlikely"; label: string }[] = [
    { key: "out", label: "Out" },
    { key: "unlikely", label: "Unlikely to play" },
  ];
  const parts = $derived(
    PARTS.map((p) => ({ ...p, rows: rows.filter((r) => (r.group ?? "out") === p.key) })).filter((p) => p.rows.length > 0),
  );
</script>

{#if rows.length}
  <section class="rounded-lg border border-line bg-surface p-3" style="box-shadow:var(--ll-shadow)" data-testid={testid}>
    <h2 class="text-sm font-bold text-ink">Not playing <span class="font-normal text-ink-3">· {rows.length}</span></h2>
    {#if words}<p class="mt-0.5 text-xs leading-snug text-ink-3">{words}</p>{/if}
    {#each parts as part (part.key)}
      {#if parts.length > 1}
        <h3 class="mt-3 text-[11px] font-bold tracking-[0.08em] text-ink-2 uppercase" data-testid={`${testid}-part`} data-part={part.key}>
          {part.label} <span class="font-normal text-ink-3">· {part.rows.length}</span>
        </h3>
      {/if}
      <ul class="mt-2 grid gap-x-6 gap-y-1 wide:grid-cols-2">
        {#each part.rows as x (x.key)}
          <li data-testid={`${testid}-row`} data-key={x.key} data-code={x.code} data-group={x.group ?? "out"}>
            <button type="button" class="flex w-full min-w-0 items-center gap-2.5 rounded-md p-1.5 text-left hover:bg-raised" onclick={() => x.gsis_id && openPane(x.gsis_id, { from: "list", context: { name: x.player_name } })}>
              <Headshot url={x.headshot_url ?? null} name={x.player_name ?? undefined} team={x.team} size={32} />
              <span class="min-w-0 flex-1">
                <span class="flex min-w-0 items-center gap-1.5">
                  <span class="truncate font-semibold text-ink">{x.player_name}</span>
                  <span class="shrink-0 rounded-sm bg-raised px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-warn ring-1 ring-line-strong ring-inset" data-testid={`${testid}-status`}>{x.status ?? "No number yet"}</span>
                </span>
                <span class="block truncate text-xs text-ink-3">{x.position ?? ""} · {teamLabel(x.team) ?? "—"}{x.why ? ` · ${x.why}` : ""}</span>
                <span class="block text-xs leading-snug text-ink-2" data-testid={`${testid}-words`}>{x.words}</span>
              </span>
              <span class="tabnum shrink-0 font-bold text-ink-3" title="No projection: he is not expected to play">—</span>
            </button>
          </li>
        {/each}
      </ul>
    {/each}
  </section>
{/if}
