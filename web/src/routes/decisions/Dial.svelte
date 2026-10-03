<script lang="ts">
  // IA-2: the dial (docs/DESIGN.md § Charts, "Dial"). A half-circle gauge in four equal bands and a needle at `score`
  // (0–100, the API's piecewise mapping of the gain) that swings to its new place on every change (a CSS transition on
  // the needle: no redraw, no page reload). The label is printed under the needle in words, so color is never the only
  // carrier; the band colors are the state tokens (bad / neutral / good) at a light wash, the picked band at full
  // strength. `you` is the second, small number: your own gain over the window, with its sign.
  // IE-1 (Wave I-E, the casual-user review): the dial is the EFFECT ON THEIR STARTERS — their best lineup's gain over
  // the window, by our numbers — in outcome words (Makes their lineup weaker · About even · Improves their lineup ·
  // Improves it a lot) with the need it fills ("fills their empty RB2"); no "interest", no 0–100 score on screen.
  import { EFFECT_TITLE, effectTone } from "../../lib/decisions";

  let {
    score,
    label,
    caption,
    need = null,
    you = null,
    youLabel = "You",
    busy = false,
    testid = "dial",
  }: { score: number; label: string; caption: string; need?: string | null; you?: number | null; youLabel?: string; busy?: boolean; testid?: string } = $props();

  const BANDS = [
    { from: 0, to: 25, label: "Makes their lineup weaker", color: "var(--ll-bad)" },
    { from: 25, to: 50, label: "About even", color: "var(--ll-ink-3)" },
    { from: 50, to: 75, label: "Improves their lineup", color: "var(--ll-good)" },
    { from: 75, to: 100, label: "Improves it a lot", color: "var(--ll-good)" },
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
  // an answer recorded before Wave I-E carries the old words: its band is the needle's quarter
  const band = $derived(BANDS.find((b) => b.label === label) ?? BANDS[Math.min(3, Math.floor(clamped / 25))]);
  const tone = $derived(effectTone(label));
  const sg = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");
</script>

<figure class="flex min-w-0 flex-col items-center" data-testid={testid} data-score={clamped} data-label={label} aria-busy={busy}>
  <svg viewBox="0 0 200 112" class="w-full max-w-[15rem]" role="img" aria-label={`${EFFECT_TITLE}: ${label}${need ? `, ${need}` : ""}. ${caption}`}>
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
    <span class="ll-label block" data-testid="dial-title">{EFFECT_TITLE}</span>
    <span class="block text-2xl leading-tight font-bold {tone}" data-testid="dial-label">{label}</span>
    {#if need}<span class="block text-base leading-snug text-ink" data-testid="dial-need">It {need}.</span>{/if}
    <span class="block text-sm text-ink-2" data-testid="dial-caption">{caption}</span>
    {#if you !== null && you !== undefined}
      <span class="mt-1 inline-flex items-baseline gap-1.5 text-sm text-ink-2" data-testid="dial-you">
        <span class="ll-label">{youLabel}</span><strong class="tabnum text-base text-ink">{sg(you)}</strong>
      </span>
    {/if}
  </figcaption>
</figure>
