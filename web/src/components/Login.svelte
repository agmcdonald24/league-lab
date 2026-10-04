<script lang="ts">
  import { APP_MARK, APP_NAME } from "../lib/brand";
  import { login } from "../lib/api";

  // ---- IH-1: `notice` — "Signed out — sign in again" when this browser was signed in before (App.svelte)
  let { onok, notice = null }: { onok: () => void; notice?: string | null } = $props();
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
  <h1 class="flex items-center gap-2 text-2xl font-extrabold tracking-tight"><span class="grid h-8 w-8 place-items-center rounded-sm bg-accent text-xs font-black text-on-accent">{APP_MARK}</span>{APP_NAME}</h1>
  {#if notice}
    <p class="rounded-md bg-warn-soft px-3 py-2 text-sm font-semibold text-warn" role="status" data-testid="signed-out">{notice}</p>
  {/if}
  <p class="text-sm text-ink-3">Private beta. Enter the password from your invite.</p>
  <!-- ---- II-5 (Wave I-I): what comes next, so the password is not mistaken for a Sleeper / MFL sign-in -->
  <p class="text-sm text-ink-3" data-testid="login-next">
    Then pick your fantasy platform — Sleeper or MyFantasyLeague — and your league. This is not your Sleeper or MFL password.
  </p>
  <input
    class="ll-input w-full py-3"
    type="password"
    autocomplete="current-password"
    placeholder="Password"
    bind:value={password}
  />
  {#if wrong}<p class="text-sm text-bad">That is not it.</p>{/if}
  <button class="w-full rounded-md bg-accent px-4 py-3 font-bold text-on-accent disabled:opacity-60" disabled={busy || !password}>
    Open {APP_NAME}
  </button>
</form>
