<script lang="ts">
  import { login } from "../lib/api";

  let { onok }: { onok: () => void } = $props();
  let password = $state("");
  let wrong = $state(false);
  let busy = $state(false);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    wrong = false;
    const ok = await login(password);
    busy = false;
    if (ok) onok();
    else wrong = true;
  }
</script>

<form class="mx-auto mt-16 max-w-sm space-y-4 px-4" onsubmit={submit} data-testid="login">
  <h1 class="text-2xl font-bold">League Lab</h1>
  <p class="text-sm text-zinc-500">Private beta. Enter the password from your invite.</p>
  <input
    class="w-full rounded-xl border border-zinc-300 bg-transparent px-3 py-3 text-base dark:border-zinc-700"
    type="password"
    autocomplete="current-password"
    placeholder="Password"
    bind:value={password}
  />
  {#if wrong}<p class="text-sm text-red-700 dark:text-red-400">That is not it.</p>{/if}
  <button class="w-full rounded-xl bg-green-700 px-4 py-3 font-semibold text-white disabled:opacity-60" disabled={busy || !password}>
    Open League Lab
  </button>
</form>
