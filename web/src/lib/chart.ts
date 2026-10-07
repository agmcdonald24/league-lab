// The chart kit's arithmetic (docs/DESIGN.md § Charts): a linear scale and clean ticks. Hand-rolled (no chart
// library: ~1 KB instead of ~60, nothing to load before the first screen); the marks are inline SVG in
// components/LineChart.svelte, Heatmap.svelte, Sparkline.svelte, Bar.svelte.

export type Scale = (v: number) => number;

export function linear(d0: number, d1: number, r0: number, r1: number): Scale {
  const span = d1 - d0 || 1;
  return (v: number) => r0 + ((v - d0) / span) * (r1 - r0);
}

/** Clean tick values (1 / 2 / 5 × 10^k steps) covering [min, max], about `count` of them. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0];
  if (min === max) max = min + 1;
  const raw = (max - min) / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.floor(min / step) * step; v <= max + step * 0.5; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

/** The extent of the numbers given (nulls skipped); [0, 1] when there are none. */
export function extent(values: (number | null | undefined)[]): [number, number] {
  const xs = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  return xs.length ? [Math.min(...xs), Math.max(...xs)] : [0, 1];
}

/** An SVG path through the points, broken where a value is missing (a bye, a game he missed). */
export function linePath(pts: { x: number; y: number | null }[]): string {
  let d = "";
  let pen = false;
  for (const p of pts) {
    if (p.y === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    pen = true;
  }
  return d;
}

/** The area under a line down to `base`, one closed shape per unbroken run. */
export function areaPath(pts: { x: number; y: number | null }[], base: number): string {
  const runs: { x: number; y: number }[][] = [];
  let cur: { x: number; y: number }[] = [];
  for (const p of pts) {
    if (p.y === null) {
      if (cur.length) runs.push(cur);
      cur = [];
    } else cur.push({ x: p.x, y: p.y });
  }
  if (cur.length) runs.push(cur);
  return runs
    .filter((r) => r.length > 1)
    .map((r) => `M${r[0].x.toFixed(1)},${base}` + r.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("") + `L${r[r.length - 1].x.toFixed(1)},${base}Z`)
    .join("");
}

// ---- IP-4 (Wave I-P): the player card's charts (components/card/WeekChart.svelte)
/** A band between two lines (a projection's range), one closed shape per unbroken run of weeks with both ends. */
export function bandPath(pts: { x: number; lo: number | null; hi: number | null }[]): string {
  const runs: { x: number; lo: number; hi: number }[][] = [];
  let cur: { x: number; lo: number; hi: number }[] = [];
  for (const p of pts) {
    if (p.lo === null || p.hi === null) {
      if (cur.length) runs.push(cur);
      cur = [];
    } else cur.push({ x: p.x, lo: p.lo, hi: p.hi });
  }
  if (cur.length) runs.push(cur);
  return runs
    .map((r) => {
      if (r.length === 1) {
        const p = r[0];
        return `M${(p.x - 6).toFixed(1)},${p.hi.toFixed(1)}L${(p.x + 6).toFixed(1)},${p.hi.toFixed(1)}L${(p.x + 6).toFixed(1)},${p.lo.toFixed(1)}L${(p.x - 6).toFixed(1)},${p.lo.toFixed(1)}Z`;
      }
      const top = r.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.hi.toFixed(1)}`).join("");
      const bottom = [...r].reverse().map((p) => `L${p.x.toFixed(1)},${p.lo.toFixed(1)}`).join("");
      return `${top}${bottom}Z`;
    })
    .join("");
}

/** A categorical x scale: n slots across [r0, r1], the slot's centre and its width. */
export function bands(n: number, r0: number, r1: number): { at: (i: number) => number; step: number } {
  const step = (r1 - r0) / Math.max(1, n);
  return { at: (i: number) => r0 + step * (i + 0.5), step };
}
// ---- end IP-4
