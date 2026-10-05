<script lang="ts">
  // ---- IK-4 (Wave I-K): the account's entry on the setup screen (Leagues) — only when the server has accounts on.
  // Signed out: one line offering it (guest use stays the default). Signed in: who, and the leagues to save.
  import { onMount } from "svelte";
  import { account, loadStatus, unsaved } from "../lib/account.svelte";

  onMount(() => {
    void loadStatus();
  });
  const st = $derived(account.status);
  const toSave = $derived(unsaved(account.me));
</script>

{#if st?.enabled}
  <section class="border-t border-line pt-4 text-base" data-testid="account-entry">
    {#if st.signed_in && account.me}
      <p class="text-ink-2">
        Signed in as <strong>{account.me.email}</strong> ·
        <a class="ll-link" href="/account" data-testid="account-entry-link"
          >{toSave.length ? `Save ${toSave.length} league${toSave.length === 1 ? "" : "s"} to your account` : "Your account"}</a
        >
      </p>
    {:else}
      <p class="text-ink-2">
        Want your leagues on another phone or computer? <a class="ll-link" href="/account" data-testid="account-entry-link">Sign in with your email</a> — no password.
      </p>
    {/if}
  </section>
{/if}
