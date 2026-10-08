<script lang="ts">
  // II-1 (Wave I-I, the product and analytics handoff § 2): the trade card's fields — the label (a plausible offer / a
  // roster-fit idea / implausible), both lineup effects, the required drops, depth or future cost, both teams' waiver
  // alternatives (guaranteed or a claim that might be lost), why they might consider it, reasons they might refuse, and
  // the legality notes. Everything is a sentence the API derived from its numbers; there is no acceptance probability.
  // `compact`: the label, the two effects and the first reason each way (the Finder's "Explore alternatives").
  import type { TradeCard } from "../../lib/api";
  import Expander from "../../components/Expander.svelte";

  let { card, compact = false, testid = "trade-card" }: { card: TradeCard; compact?: boolean; testid?: string } = $props();

  // PO (Wave I-R): green only when the card is also worth proposing — a green "Plausible offer" under "Not worth proposing" read as a contradiction
  const tone = $derived(card.plausibility.key === "plausible" ? (card.credible ? "text-good" : "text-ink-2") : card.plausibility.key === "implausible" ? "text-bad" : "text-warn");
  const drops = $derived([...card.drops.mine, ...card.drops.theirs].map((d) => d.words));
</script>

<div class="space-y-1.5 text-sm leading-snug" data-testid={testid}>
  <p class="flex flex-wrap items-baseline gap-x-2">
    <strong class={tone} data-testid="card-plausibility">{card.plausibility.label}</strong>
    {#if card.credible}<span class="ll-label text-good" data-testid="card-credible">Beats both teams' alternatives</span>{/if}
  </p>
  <p data-testid="card-your-effect"><span class="ll-label">You</span> {card.your_effect.words}</p>
  <p data-testid="card-their-effect"><span class="ll-label">Them</span> {card.their_effect.words}</p>
  {#if compact}
    {#if card.why_refuse.length}<p class="text-ink-2" data-testid="card-refuse-first"><span class="ll-label">They might refuse</span> {card.why_refuse[0]}</p>{/if}
  {:else}
    {#if drops.length}<p data-testid="card-drops"><span class="ll-label">Required drops</span> {drops.join(" ")}</p>{/if}
    {#if card.depth_cost.mine}<p data-testid="card-depth"><span class="ll-label">Depth and roster spots</span> {card.depth_cost.mine}</p>{/if}
    {#if card.depth_cost.horizon}<p class="text-ink-2" data-testid="card-horizon">{card.depth_cost.horizon}</p>{/if}
    <p data-testid="card-alternatives"><span class="ll-label">Waiver alternatives</span> {card.waiver_alternative.words}</p>
    {#if card.why_consider.length}
      <div data-testid="card-consider">
        <span class="ll-label">Why they might consider it</span>
        <ul class="ml-4 list-disc">{#each card.why_consider as x, i (i)}<li>{x}</li>{/each}</ul>
      </div>
    {/if}
    {#if card.why_refuse.length}
      <div data-testid="card-refuse">
        <span class="ll-label">Reasons they might refuse</span>
        <ul class="ml-4 list-disc">{#each card.why_refuse as x, i (i)}<li>{x}</li>{/each}</ul>
      </div>
    {/if}
    {#if card.legal.notes.length || !card.legal.ok}
      <Expander title={card.legal.ok ? "Legality: checked" : "Legality: not allowed now"} testid="card-legal">
        <ul class="ml-4 list-disc">{#each card.legal.notes as x, i (i)}<li>{x}</li>{/each}</ul>
        <p class="mt-1 text-ink-3">Checked: {card.legal.checks.join("; ")}.</p>
      </Expander>
    {/if}
  {/if}
</div>
