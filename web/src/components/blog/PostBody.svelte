<script lang="ts">
  // ---- IN-1 (Wave I-N): a post's body — lib/md.ts `mdDoc` (escaped first; only its own tags) in the reading styles
  // below: a readable measure, headings, lists, quotes, code, pictures, and tables that scroll inside themselves on a
  // phone (the page never scrolls sideways). Player links carry the frame's league, so a tap opens the drawer.
  import { isYoutubeId, mdDoc } from "../../lib/md";
  import PlayersBlock from "./PlayersBlock.svelte";

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
  .ll-prose :global(.ll-embed-h) {
    font-weight: 700;
    overflow-wrap: anywhere;
  }
</style>
