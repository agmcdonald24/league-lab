<script lang="ts">
  // ---- IM-5: add the salary file — a file input, drag and drop, or paste the text. One request; nothing is uploaded
  // anywhere else and the server keeps nothing.
  import { MAX_BYTES, type Site } from "./dfs";

  let { site, busy = false, onfile }: { site: Site; busy?: boolean; onfile: (text: string) => void } = $props();
  let over = $state(false);
  let pasted = $state("");
  let pasteOpen = $state(false);
  let local = $state<string | null>(null);
  const name = $derived(site === "dk" ? "DraftKings" : "FanDuel");

  async function take(f: File | null | undefined) {
    local = null;
    if (!f) return;
    if (f.size > MAX_BYTES) {
      local = `That file is ${(f.size / 1e6).toFixed(1)} MB: a salary file is under 1 MB.`;
      return;
    }
    onfile(await f.text());
  }
</script>

<div
  class="rounded-lg border-2 border-dashed p-4 text-center {over ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface'}"
  role="region"
  aria-label="Add the salary file"
  ondragover={(e) => {
    e.preventDefault();
    over = true;
  }}
  ondragleave={() => (over = false)}
  ondrop={(e) => {
    e.preventDefault();
    over = false;
    void take(e.dataTransfer?.files?.[0]);
  }}
  data-testid="dfs-filebox"
>
  <p class="text-base font-semibold">Add the {name} salary file to see value</p>
  <p class="mt-1 text-sm text-ink-3">Drop the CSV here, choose it, or paste its text. It stays in this tab.</p>
  <div class="mt-3 flex flex-wrap items-center justify-center gap-2">
    <label class="inline-flex min-h-10 cursor-pointer items-center rounded-md bg-accent px-4 text-sm font-bold text-on-accent {busy ? 'opacity-60' : ''}">
      {busy ? "Reading…" : "Choose the file"}
      <input
        class="sr-only"
        type="file"
        accept=".csv,text/csv,text/plain"
        disabled={busy}
        onchange={(e) => void take((e.currentTarget as HTMLInputElement).files?.[0])}
        data-testid="dfs-file"
      />
    </label>
    <button type="button" class="min-h-10 rounded-md border border-line-strong px-3 text-sm font-semibold text-ink-2 hover:text-ink" aria-expanded={pasteOpen} onclick={() => (pasteOpen = !pasteOpen)} data-testid="dfs-paste-open"
      >Paste the text</button
    >
  </div>
  {#if pasteOpen}
    <div class="mt-3 space-y-2 text-left">
      <label class="ll-label" for="dfs-paste">The file's text</label>
      <textarea id="dfs-paste" class="h-28 w-full rounded-md border border-line bg-sunken p-2 font-mono text-xs" bind:value={pasted} data-testid="dfs-paste"></textarea>
      <button
        type="button"
        class="min-h-10 rounded-md bg-accent px-4 text-sm font-bold text-on-accent disabled:opacity-50"
        disabled={busy || !pasted.trim()}
        onclick={() => onfile(pasted)}
        data-testid="dfs-paste-add">Read it</button
      >
    </div>
  {/if}
  {#if local}<p class="mt-2 text-sm text-bad" role="alert">{local}</p>{/if}
</div>
