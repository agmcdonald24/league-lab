<script lang="ts">
  // ---- IN-1 (Wave I-N): a post's body — lib/md.ts `mdDoc` (escaped first; only its own tags) in the reading styles
  // below: a readable measure, headings, lists, quotes, code, pictures, and tables that scroll inside themselves on a
  // phone (the page never scrolls sideways). Player links carry the frame's league, so a tap opens the drawer.
  import { isYoutubeId, mdDoc } from "../../lib/md";
  import PlayersBlock from "./PlayersBlock.svelte";
  import { onXMessage, X_ATTEMPTS, X_GIVE_UP_MS, X_NEAR, X_SANDBOX, xFrameSrc } from "./xframe";

  let { markdown, league }: { markdown: string; league: string } = $props();
  // the first ```players block becomes the live table; the text before and after it is markdown (escaped first)
  const FENCE = /^ {0,3}```players[ \t]*\n([\s\S]*?)^ {0,3}```[ \t]*$/m;
  const parts = $derived.by(() => {
    const m = FENCE.exec(markdown);
    if (!m) return { before: mdDoc(markdown, { league }), block: null as string | null, after: "" };
    return { before: mdDoc(markdown.slice(0, m.index), { league }), block: m[1], after: mdDoc(markdown.slice(m.index + m[0].length), { league }) };
  });

  // ---- IU-6 (Wave I-U): a YouTube embed is a Play button until the reader taps it (md.ts `embed`); only then is the
  // iframe made — to youtube-nocookie.com, from the id checked again here, sandboxed, lazy, with a title. Nothing from
  // YouTube or X is asked for before that tap, and no script from either is ever loaded.
  let root = $state<HTMLDivElement | null>(null);
  function play(e: MouseEvent) {
    const btn = (e.target as Element | null)?.closest?.("button[data-yt-play]") as HTMLButtonElement | null;
    if (!btn || !root?.contains(btn)) return;
    const id = btn.dataset.ytPlay;
    if (!isYoutubeId(id)) return;
    const frame = document.createElement("iframe");
    frame.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1`;
    frame.title = "YouTube video";
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation allow-popups");
    frame.setAttribute("loading", "lazy");
    frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    frame.setAttribute("allow", "autoplay; encrypted-media; picture-in-picture; fullscreen");
    frame.allowFullscreen = true;
    frame.className = "ll-embed-frame";
    frame.dataset.testid = "embed-frame";
    btn.replaceWith(frame);
  }
  $effect(() => {
    const el = root;
    if (!el) return;
    el.addEventListener("click", play);
    return () => el.removeEventListener("click", play);
  });

  // ---- IY-1 / IY-2 (Wave I-Y): a post on X is our own card (md.ts `xBlock`) from the first paint. When the block comes
  // within 600 px of the screen (once per block), X's frame — platform.twitter.com/embed/Tweet.html from the id checked
  // again here, sandboxed, no referrer, a title — is made in the block OUT OF SIGHT: absolutely placed over the card's
  // own box (it takes no room), at its real width (min(550px, 100%)), opacity 0, not clickable, not focusable. Opacity
  // rather than visibility: hidden or a zero height, because Chrome throttles a cross-origin frame it counts as not
  // visible (hidden, no area, off screen) and X only measures and sends its size once it has painted. On X's first
  // resize message (xframe.ts: that origin, that frame) the frame takes the card's place at that height and the card
  // goes; later messages keep the height. No message in 10 s: the frame is removed and the card stays — it is a complete
  // block by itself. `color-scheme: light` on the frame: X's document is light-scheme, and a frame whose scheme differs
  // from the page's gets an opaque backdrop (white on our dark page).
  const dark = () => typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
  // ---- IY-3: X sends its size only after it has painted, and a document that is not being painted (a background tab)
  // never paints it: the 10 seconds count only while the document is visible. After a give-up the block tries once
  // more the next time it is on screen in a visible document — two attempts in all, then the card stays.
  const attempts = new WeakMap<Element, number>();
  const stops = new WeakMap<HTMLIFrameElement, () => void>(); // a waiting frame's give-up watch, stopped when it shows
  const cleanups: (() => void)[] = [];
  const visible = () => typeof document === "undefined" || document.visibilityState === "visible";
  function loadX(fig: HTMLElement) {
    const n = attempts.get(fig) ?? 0;
    const src = xFrameSrc(fig.dataset.xPost ?? "", dark());
    if (n >= X_ATTEMPTS || !src || fig.querySelector("iframe[data-x-frame]")) return;
    attempts.set(fig, n + 1);
    const frame = document.createElement("iframe");
    frame.src = src;
    frame.title = "Post on X";
    frame.setAttribute("sandbox", X_SANDBOX);
    frame.setAttribute("referrerpolicy", "no-referrer");
    frame.setAttribute("scrolling", "no"); // IY-3: as X's own script sets it — no scrollbar, X's card the frame's full width
    frame.allowFullscreen = true; // IY-3: the post's video may go full screen
    frame.setAttribute("aria-hidden", "true");
    frame.tabIndex = -1;
    frame.className = "ll-embed-xframe ll-embed-xframe-waiting";
    frame.dataset.testid = "x-frame";
    frame.dataset.xFrame = "waiting";
    fig.insertBefore(frame, fig.firstChild);
    watchGiveUp(frame, fig);
  }
  function watchGiveUp(frame: HTMLIFrameElement, fig: HTMLElement) {
    let left = X_GIVE_UP_MS;
    let since = 0;
    let t: ReturnType<typeof setTimeout> | undefined;
    const pause = () => {
      if (t === undefined) return;
      clearTimeout(t);
      t = undefined;
      left -= Date.now() - since;
    };
    const run = () => {
      if (t !== undefined || !visible()) return;
      since = Date.now();
      t = setTimeout(giveUp, Math.max(0, left));
    };
    const onVisibility = () => (visible() ? run() : pause());
    const stop = () => {
      pause();
      document.removeEventListener("visibilitychange", onVisibility);
      stops.delete(frame);
    };
    const giveUp = () => {
      t = undefined;
      stop();
      if (frame.dataset.xFrame !== "waiting") return;
      frame.remove(); // X never answered: the card is the block
      tryAgainOnScreen(fig);
    };
    document.addEventListener("visibilitychange", onVisibility);
    stops.set(frame, stop);
    cleanups.push(stop);
    run();
  }
  function tryAgainOnScreen(fig: HTMLElement) {
    if ((attempts.get(fig) ?? 0) >= X_ATTEMPTS || typeof IntersectionObserver !== "function") return;
    let onScreen = false;
    const go = () => {
      if (!onScreen || !visible()) return;
      io.disconnect();
      document.removeEventListener("visibilitychange", go);
      loadX(fig);
    };
    const io = new IntersectionObserver((entries) => {
      onScreen = entries.some((e) => e.isIntersecting);
      go();
    });
    document.addEventListener("visibilitychange", go);
    io.observe(fig);
    cleanups.push(() => {
      io.disconnect();
      document.removeEventListener("visibilitychange", go);
    });
  }
  function showFrame(frame: HTMLIFrameElement) {
    if (frame.dataset.xFrame !== "waiting") return;
    stops.get(frame)?.();
    frame.dataset.xFrame = "shown";
    frame.classList.remove("ll-embed-xframe-waiting");
    frame.removeAttribute("aria-hidden");
    frame.removeAttribute("tabindex");
    frame.closest("figure")?.querySelector("[data-x-body]")?.remove();
  }
  $effect(() => {
    const el = root;
    void parts; // the post's HTML is new (the editor's preview): look at its blocks again
    if (!el) return;
    const figs = Array.from(el.querySelectorAll<HTMLElement>("figure.ll-embed-x[data-x-post]"));
    if (!figs.length) return;
    if (typeof IntersectionObserver !== "function") {
      figs.forEach(loadX);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          if (e.isIntersecting) {
            io.unobserve(e.target);
            loadX(e.target as HTMLElement);
          }
      },
      { rootMargin: X_NEAR },
    );
    figs.forEach((f) => io.observe(f));
    return () => {
      io.disconnect();
      cleanups.splice(0).forEach((f) => f());
    };
  });
  $effect(() => {
    const el = root;
    if (!el) return;
    const onMessage = (e: MessageEvent) => {
      const f = onXMessage(e, el.querySelectorAll<HTMLIFrameElement>("iframe[data-x-frame]"));
      if (f) showFrame(f as HTMLIFrameElement);
    };
    // IY-2: a YouTube still that fails to load goes (error does not bubble: caught on the way down); the grey block stays
    const onError = (e: Event) => {
      const t = e.target as Element | null;
      if (t instanceof HTMLImageElement && t.classList.contains("ll-embed-still")) t.remove();
    };
    window.addEventListener("message", onMessage);
    el.addEventListener("error", onError, true);
    return () => {
      window.removeEventListener("message", onMessage);
      el.removeEventListener("error", onError, true);
    };
  });
</script>

<div class="mt-5" data-testid="post-body" bind:this={root}>
  <div class="ll-prose">{@html parts.before}</div>
  {#if parts.block !== null}
    <PlayersBlock body={parts.block} /><!-- the Stats table keeps its own styles: outside the reading styles -->
    <div class="ll-prose">{@html parts.after}</div>
  {/if}
</div>

<style>
  .ll-prose {
    font-size: 1.0625rem;
    line-height: 1.65;
    color: var(--ll-ink);
    overflow-wrap: break-word;
  }
  .ll-prose :global(p),
  .ll-prose :global(ul),
  .ll-prose :global(ol),
  .ll-prose :global(blockquote),
  .ll-prose :global(pre),
  .ll-prose :global(.ll-md-table) {
    margin: 0 0 1.1em;
  }
  .ll-prose :global(h2) {
    margin: 1.8em 0 0.5em;
    font-size: 1.375rem;
    line-height: 1.25;
    font-weight: 800;
    letter-spacing: -0.01em;
  }
  .ll-prose :global(h3),
  .ll-prose :global(h4),
  .ll-prose :global(h5) {
    margin: 1.5em 0 0.4em;
    font-size: 1.125rem;
    line-height: 1.3;
    font-weight: 700;
  }
  .ll-prose :global(ul) {
    list-style: disc;
    padding-left: 1.4em;
  }
  .ll-prose :global(ol) {
    list-style: decimal;
    padding-left: 1.6em;
  }
  .ll-prose :global(li) {
    margin: 0.3em 0;
  }
  .ll-prose :global(blockquote) {
    border-left: 3px solid var(--ll-accent);
    padding: 0.2em 0 0.2em 1em;
    color: var(--ll-ink-2);
  }
  .ll-prose :global(blockquote p:last-child) {
    margin-bottom: 0;
  }
  .ll-prose :global(code) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9em;
    background: var(--ll-raised);
    border-radius: 4px;
    padding: 0.1em 0.3em;
  }
  .ll-prose :global(pre) {
    overflow-x: auto;
    background: var(--ll-sunken);
    border: 1px solid var(--ll-line);
    border-radius: 10px;
    padding: 0.8em 1em;
    font-size: 0.875rem;
    line-height: 1.5;
  }
  .ll-prose :global(pre code) {
    background: none;
    padding: 0;
  }
  .ll-prose :global(hr) {
    border: 0;
    border-top: 1px solid var(--ll-line-strong);
    margin: 2em 0;
  }
  .ll-prose :global(img.ll-md-img) {
    display: block;
    max-width: 100%;
    height: auto;
    border-radius: 10px;
    margin: 0.5em 0;
  }
  /* a table scrolls inside its own box (375 px); the page never does */
  .ll-prose :global(.ll-md-table) {
    max-width: 100%;
    overflow-x: auto;
    border: 1px solid var(--ll-line);
    border-radius: 10px;
  }
  .ll-prose :global(.ll-md-table:focus-visible) {
    outline: 2px solid var(--ll-accent);
  }
  .ll-prose :global(table) {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.9375rem;
    font-variant-numeric: tabular-nums;
  }
  .ll-prose :global(th),
  .ll-prose :global(td) {
    padding: 0.5em 0.75em;
    border-bottom: 1px solid var(--ll-line);
    text-align: left;
    white-space: nowrap;
  }
  .ll-prose :global(thead th) {
    background: var(--ll-raised);
    font-size: 0.8125rem;
    font-weight: 700;
    color: var(--ll-ink-2);
  }
  .ll-prose :global(tbody tr:last-child td) {
    border-bottom: 0;
  }
  /* ---- IU-6: embeds (md.ts `embed`) */
  .ll-prose :global(.ll-embed) {
    margin: 0 0 1.1em;
  }
  .ll-prose :global(.ll-embed-play),
  .ll-prose :global(.ll-embed-frame) {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.25em;
    width: 100%;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--ll-line);
    border-radius: 10px;
    background: var(--ll-sunken);
    color: var(--ll-ink);
    cursor: pointer;
  }
  .ll-prose :global(.ll-embed-frame) {
    display: block;
    border: 0;
    cursor: auto;
  }
  .ll-prose :global(.ll-embed-play:hover) {
    border-color: var(--ll-line-strong);
  }
  .ll-prose :global(.ll-embed-play:focus-visible),
  .ll-prose :global(.ll-embed-card:focus-visible) {
    outline: 2px solid var(--ll-accent);
  }
  .ll-prose :global(.ll-embed-k) {
    font-weight: 700;
  }
  .ll-prose :global(.ll-embed-s) {
    font-size: 0.875rem;
    color: var(--ll-ink-2);
  }
  .ll-prose :global(.ll-embed figcaption) {
    margin-top: 0.35em;
    font-size: 0.875rem;
  }
  .ll-prose :global(.ll-embed-card) {
    display: flex;
    flex-direction: column;
    gap: 0.15em;
    padding: 0.75em 1em;
    border: 1px solid var(--ll-line);
    border-left: 4px solid var(--ll-line-strong);
    border-radius: 10px;
    background: var(--ll-raised);
    color: var(--ll-ink);
    text-decoration: none;
  }
  .ll-prose :global(.ll-embed-card:hover) {
    border-color: var(--ll-line-strong);
  }
  /* ---- IY-1: a post on X — its words in our markup, then X's frame after the tap */
  .ll-prose :global(.ll-embed-quote) {
    margin: 0;
    padding: 0.75em 1em;
    border: 1px solid var(--ll-line);
    border-left: 4px solid var(--ll-line-strong);
    border-radius: 10px;
    background: var(--ll-raised);
    font-style: normal;
  }
  .ll-prose :global(.ll-embed-words) {
    margin: 0 0 0.5em;
    overflow-wrap: anywhere;
  }
  .ll-prose :global(.ll-embed-by) {
    font-size: 0.875rem;
    color: var(--ll-ink-2);
    overflow-wrap: anywhere;
  }
  .ll-prose :global(.ll-embed-actions) {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5em 1em;
    margin-top: 0.5em;
    font-size: 0.9375rem;
  }
  /* IY-2: X's frame — at most X's card width (550 px), on the column's left edge; a light scheme like X's document, so
     no opaque backdrop is painted behind X's dark card on our dark page; out of sight until X has laid the post out */
  .ll-prose :global(.ll-embed-x) {
    position: relative;
  }
  .ll-prose :global(.ll-embed-xframe) {
    display: block;
    width: min(550px, 100%);
    max-width: 100%;
    margin: 0;
    border: 0;
    border-radius: 12px;
    color-scheme: light;
  }
  .ll-prose :global(.ll-embed-xframe-waiting) {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    opacity: 0;
    pointer-events: none;
  }
  /* IY-2: the YouTube still fills the 16:9 box under the Play label; without it, the grey block as before */
  .ll-prose :global(.ll-embed-play) {
    position: relative;
    overflow: hidden;
  }
  .ll-prose :global(.ll-embed-still) {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .ll-prose :global(.ll-embed-play .ll-embed-k) {
    position: relative;
    padding: 0.45em 0.9em;
    border-radius: 999px;
    background: rgb(0 0 0 / 0.72);
    color: #fff;
  }
  .ll-prose :global(.ll-embed-h) {
    font-weight: 700;
    overflow-wrap: anywhere;
  }
</style>
