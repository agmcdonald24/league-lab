<script lang="ts">
  // ---- IK-4 (Wave I-K): the account's entry on the setup screen (Leagues) — only when the server has accounts on.
  // Signed out: one line offering it (guest use stays the default). Signed in: who, and the leagues to save.
  // ---- IM-4: the line names the ways in this server has (a passkey, an email, or both).
  import { onMount } from "svelte";
  import { account, loadStatus, methodsOf, unsaved } from "../lib/account.svelte";

  onMount(() => {
    void loadStatus();
  });
  const st = $derived(account.status);
  const toSave = $derived(unsaved(account.me));
  const methods = $derived(methodsOf(st));
</script>

{#if st?.enabled}
  <section class="border-t border-line pt-4 text-base" data-testid="account-entry">
    {#if st.signed_in && account.me}
      <p class="text-ink-2">
        {#if account.me.email}Signed in as <strong>{account.me.email}</strong>{:else}Signed in with a passkey{/if} ·
        <a class="ll-link" href="/account" data-testid="account-entry-link"
          >{toSave.length ? `Save ${toSave.length} league${toSave.length === 1 ? "" : "s"} to your account` : "Your account"}</a
        >
      </p>
    {:else}
      <p class="text-ink-2">
        {#if !methods.includes("passkey")}
          Want your leagues on another phone or computer? <a class="ll-link" href="/account" data-testid="account-entry-link">Sign in with your email</a> — no password.
        {:else if methods.includes("email")}
          Want your leagues on another phone or computer? <a class="ll-link" href="/account" data-testid="account-entry-link">Save them with a passkey or your email</a> — no password.
        {:else}
          Want your leagues on another phone or computer? <a class="ll-link" href="/account" data-testid="account-entry-link">Save them with a passkey</a> — no password, no email.
        {/if}
      </p>
    {/if}
  </section>
{/if}
