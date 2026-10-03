<script lang="ts">
  // IA-2: the interest dial (docs/DESIGN.md § Charts, "Dial"). A half-circle gauge in four equal bands — No deal ·
  // Maybe · Likely · Hard to say no — and a needle at `score` (0–100) that swings to its new place on every change
  // (a CSS transition on the needle: no redraw, no page reload). The label is printed under the needle in words, so
  // color is never the only carrier; the band colors are the state tokens (bad / warn / good) at a light wash, the
  // picked band at full strength. `you` is the second, small number: your own gain over the window, with its sign.
  let {
    score,
    label,
    caption,
    you = null,
    youLabel = "You",
    busy = false,
    testid = "dial",
  }: { score: number; label: string; caption: string; you?: number | null; youLabel?: string; busy?: boolean; testid?: string } = $props();

  const BANDS = [
    { from: 0, to: 25, label: "No deal", color: "var(--ll-bad)" },
    { from: 25, to: 50, label: "Maybe", color: "var(--ll-warn)" },
    { from: 50, to: 75, label: "Likely", color: "var(--ll-good)" },
    { from: 75, to: 100, label: "Hard to say no", color: "var(--ll-good)" },
  ];
  const CX = 100;
  const CY = 100;
  const R = 78;
  const pt = (s: number, r = R) => ({ x: CX - r * Math.cos((Math.PI * s) / 100), y: CY - r * Math.sin((Math.PI * s) / 100) });
  const arc = (a: number, b: number) => {
    const p = pt(a);
    const q = pt(b);
    return `M ${p.x.toFixed(2)} ${p.y.toFixed(2)} A ${R} ${R} 0 0 1 ${q.x.toFixed(2)} ${q.y.toFixed(2)}`;
  };
  const clamped = $derived(Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0)));
  const band = $derived(BANDS.find((b) => b.label === label) ?? BANDS[0]);
  const tone = $derived(label === "No deal" ? "text-bad" : label === "Maybe" ? "text-warn" : "text-good");
  const sg = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");
</script>

<figure class="flex min-w-0 flex-col items-center" data-testid={testid} data-score={clamped} data-label={label} aria-busy={busy}>
  <svg viewBox="0 0 200 112" class="w-full max-w-[15rem]" role="img" aria-label={`Their interest: ${Math.round(clamped)} of 100, ${label}. ${caption}`}>
    {#each BANDS as b (b.label)}
      <path
        d={arc(b.from + 1, b.to - 1)}
        fill="none"
        stroke={b.color}
        stroke-width="14"
        stroke-linecap="butt"
        opacity={b.label === band.label ? 1 : 0.22}
        style="transition: opacity 300ms ease"
      />
    {/each}
    <!-- the needle: drawn pointing at 0 (left), turned by the score (180° = 100) -->
    <g style="transform: rotate({(clamped / 100) * 180}deg); transform-origin: {CX}px {CY}px; transition: transform 450ms cubic-bezier(.2,.8,.2,1)" data-testid="dial-needle">
      <line x1={CX} y1={CY} x2={CX - R + 10} y2={CY} stroke="var(--ll-ink)" stroke-width="3" stroke-linecap="round" />
    </g>
    <circle cx={CX} cy={CY} r="6" fill="var(--ll-ink)" />
  </svg>
  <figcaption class="-mt-1 text-center">
    <span class="ll-label block">Their interest</span>
    <span class="block text-2xl leading-tight font-bold {tone}" data-testid="dial-label">{label}</span>
    <span class="tabnum block text-sm text-ink-2"><span data-testid="dial-score">{Math.round(clamped)}</span> / 100 · {caption}</span>
    {#if you !== null && you !== undefined}
      <span class="mt-1 inline-flex items-baseline gap-1.5 text-sm text-ink-2" data-testid="dial-you">
        <span class="ll-label">{youLabel}</span><strong class="tabnum text-base text-ink">{sg(you)}</strong>
      </span>
    {/if}
  </figcaption>
</figure>
