<script lang="ts">
  // ---- IP-2 (Wave I-P): "Who should I start?" — for two to four players, the chance each scores the most this week
  // (GET /api/rankings/start: each player's range as the week's odds draw it, one copula for players of one game), the
  // call in words (under 55 in 100 a coin flip, 55–65 a lean, 65+ clear: the D6 scale) and how sure such a call is.
  // Quiet when the answer cannot be had (an old server, a fixture without it): the screen under it stands alone.
  import { startPath, type StartAnswer } from "../../lib/api";
  import { Remote } from "../../lib/remote.svelte";
  import { fmt, teamLabel } from "../../lib/theme";
  import Headshot from "../Headshot.svelte";

  let { league, ids, onauth, testid = "start-answer" }: { league: string; ids: string[]; onauth: () => void; testid?: string } = $props();

  const s = new Remote<StartAnswer>();
  const path = $derived(ids.length >= 2 ? startPath(league, ids) : null);
  $effect(() => s.load(path, onauth, true));
  const d = $derived(s.data);
  const colors = ["var(--ll-series-1)", "var(--ll-div-hot)", "var(--ll-accent)", "var(--ll-ink-3)"]; // Compare's first two, then two more
  const nameOf = (g: string) => d?.players.find((p) => p.gsis_id === g)?.player_name ?? g;
  const tally = (n: number) => ["", "", "two", "three", "four"][n] ?? String(n);
</script>

{#if ids.length >= 2 && !s.error}
  <section class="space-y-3 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid={testid} aria-live="polite">
    <h2 class="text-lg leading-tight font-extrabold">Who should I start?</h2>
    {#if !d}
      <div class="ll-skel h-16" aria-label="Loading" data-testid={`${testid}-loading`}></div>
    {:else if d.notice || !d.answer}
      <p class="text-ink-2" data-testid={`${testid}-notice`}>{d.notice ?? "Pick at least two players with a game this week."}</p>
      {#each d.missing as m (m.gsis_id)}<p class="text-sm text-ink-3">{nameOf(m.gsis_id)}: {m.why}.</p>{/each}
    {:else}
      <p class="text-base leading-snug font-semibold text-ink wide:text-lg" data-testid={`${testid}-words`} data-verdict={d.answer.verdict}>{d.answer.words}</p>
      {#if d.started_note}<p class="text-sm leading-snug font-semibold text-warn" data-testid={`${testid}-started`}>{d.started_note}</p>{/if}
      <div class="space-y-3 wide:grid wide:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] wide:gap-6 wide:space-y-0">
      <div class="space-y-2">
      <ul class="space-y-2" data-testid={`${testid}-players`}>
        {#each d.players as p, i (`${p.gsis_id}#${i}`)}
          <li class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5" data-testid={`${testid}-player`} data-gsis={p.gsis_id}>
            <Headshot url={p.headshot_url} name={p.player_name} team={p.team} size={32} />
            <span class="min-w-0">
              <span class="block truncate font-semibold">{p.player_name}</span>
              <span class="block truncate text-xs text-ink-3">{p.position} · {p.is_home === false ? "at" : "vs"} {teamLabel(p.opponent) ?? "—"} · {fmt.pts(p.proj_points)} projected</span>
              <span class="mt-1 block h-2 rounded-sm bg-sunken" aria-hidden="true">
                <span class="block h-full rounded-sm" style="width:{Math.max(2, p.pct_best)}%;background:{colors[i] ?? colors[0]}"></span>
              </span>
            </span>
            <span class="tabnum text-right whitespace-nowrap" data-testid={`${testid}-pct`}><span class="text-lg font-extrabold">{p.pct_best}</span><span class="text-xs text-ink-3">&nbsp;in 100</span></span>
          </li>
        {/each}
      </ul>
      <p class="text-xs leading-snug text-ink-3">
        {d.players.length === 2 ? "How often each outscores the other" : `How often each scores the most of the ${tally(d.players.length)}`} this week, in {d.scoring} scoring.
      </p>
      </div>
      <div class="space-y-2">
      <p class="text-sm leading-snug text-ink-2" data-testid={`${testid}-floor`}>{d.floor}</p>
      {#if d.multi_note}<p class="text-xs leading-snug text-ink-3" data-testid={`${testid}-multi`}>{d.multi_note}</p>{/if}
      <p class="text-xs leading-snug text-ink-3" data-testid={`${testid}-assumes`}>{d.assumes}</p>
      </div>
      </div>
    {/if}
  </section>
{/if}
