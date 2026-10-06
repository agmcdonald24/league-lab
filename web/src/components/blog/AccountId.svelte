<script lang="ts">
  // ---- IO-3 (Wave I-O): the signed-in account's id with a copy button — the blog's editors are listed by this id in the
  // server's LEAGUE_LAB_EDITORS (docs/BLOG.md § "Adding an editor"). It is not a password: it opens nothing by itself.
  let { id }: { id: string | null | undefined } = $props();
  let copied = $state<"idle" | "copied" | "manual">("idle");
  async function copy() {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
      copied = "copied";
      setTimeout(() => (copied = "idle"), 2500);
    } catch {
      copied = "manual";
    }
  }
</script>

{#if id}
  <section class="space-y-1 text-sm" data-testid="account-id">
    <h2 class="ll-label">Your account id</h2>
    <div class="flex flex-wrap items-center gap-2">
      <code class="rounded-sm bg-raised px-1.5 py-0.5 text-[0.8125rem] break-all" data-testid="account-id-value">{id}</code>
      <button type="button" class="inline-flex min-h-9 items-center rounded-md border border-line px-3 font-semibold" onclick={copy} data-testid="account-id-copy"
        >{copied === "copied" ? "Copied" : "Copy"}</button
      >
    </div>
    {#if copied === "manual"}<input class="ll-input w-full py-1.5 text-sm" readonly value={id} onfocus={(e) => e.currentTarget.select()} />{/if}
    <p class="text-ink-3">Only needed to be made a writer on the blog. It is not a password.</p>
    <span class="sr-only" aria-live="polite">{copied === "copied" ? "Account id copied" : ""}</span>
  </section>
{/if}
