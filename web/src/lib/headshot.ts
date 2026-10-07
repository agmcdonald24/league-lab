// The picture a Headshot asks for. dim_player's headshot_url is nflverse's link to the NFL's original (3400 x 2450,
// 0.5 - 0.9 MB each: a 50-row list was ~30 MB of pictures). The NFL's image host resizes on request, so ask for the
// width the circle needs (2x for sharp screens; the picture is landscape and the circle covers by height). Any other
// address is returned as it is. Hotfix 2026-10-07.
const NFL = /^(https:\/\/static\.www\.nfl\.com\/image\/(?:upload|private)\/)f_auto,q_auto(\/.+)$/;

export function headshotWidth(size: number): number {
  if (size <= 44) return 128;
  if (size <= 64) return 192;
  if (size <= 84) return 256;
  return 320;
}

export function sizedHeadshot(url: string | null | undefined, size: number): string | null {
  if (!url) return null;
  const m = NFL.exec(url);
  return m ? `${m[1]}f_auto,q_auto,w_${headshotWidth(size)}${m[2]}` : url;
}
