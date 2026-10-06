<script lang="ts">
  // ---- IO-3 (Wave I-O): the blog editor — "/blog/new" and "/blog/edit/<id>" (docs/BLOG.md § "The editor"). Only an
  // account the server lists in LEAGUE_LAB_EDITORS gets past the first call; everyone else sees one line and a link.
  // Title, summary, tags, author line, the address, and the markdown body with a live preview through lib/md.ts `mdDoc`
  // (components/blog/PostBody.svelte: the public post's own renderer — escaped first, no second renderer), side by side
  // from 900 px, a Write / Preview switch below. A draft saves itself (2.5 s after the last change, to the server) and
  // its unsent text is kept on this device too; a published post saves when "Save changes" is tapped, so readers never
  // see half a sentence. A stale save is a conflict shown in words — never a silent overwrite.
  import { onDestroy } from "svelte";
  import { blogPaths, forget, get, paths, type Hit, type StatsColumn, type StatsFrame, statsPath } from "../lib/api";
  import { loadStatus } from "../lib/account.svelte";
  import { navigate } from "../lib/router.svelte";
  import { REF_DEFAULT } from "../lib/refleague";
  import PostBody from "../components/blog/PostBody.svelte";
  import { DEFAULT_COLS, MAX_COLS, MAX_PLAYERS } from "../components/blog/PlayersBlock.svelte";
  import {
    bytesOf,
    checkEditor,
    dropLocal,
    editor,
    editorApi,
    EditorError,
    EXPORT_PATH,
    keepLocal,
    readLocal,
    slugFrom,
    tagsFrom,
    type Draft,
    type EditorImage,
    type EditorPost,
    type LocalCopy,
    uploadImage,
  } from "../components/blog/editor.svelte";
  import { STARTERS, starter, type StarterKind } from "../components/blog/starters";

  let { id = null, league }: { id?: string | null; league: string } = $props();

  const AUTOSAVE_MS = 2500;
  const LIMIT_KB = 200;

  type Gate = "loading" | "ok" | "signed_out" | "not_editor" | "missing" | "failed";
  let gate = $state<Gate>("loading");
  let post = $state<EditorPost | null>(null);
  let title = $state("");
  let summary = $state("");
  let tagsText = $state("");
  let author = $state("");
  let body = $state("");
  let slug = $state("");
  let slugTouched = $state(false);
  let saveState = $state<"idle" | "dirty" | "saving" | "saved" | "error">("idle");
  let savedAt = $state<Date | null>(null);
  let problem = $state<string | null>(null); // the last refusal's words
  let slugWords = $state<string | null>(null);
  let conflict = $state<EditorPost | null>(null);
  let offer = $state<LocalCopy | null>(null); // unsent text found on this device
  let view = $state<"write" | "preview">("write");
  let preview = $state("");
  let confirmDelete = $state(false);
  let copied = $state<"idle" | "copied" | "manual">("idle");
  let starting = $state<StarterKind | null>(null);
  let panel = $state<"none" | "player" | "table" | "picture">("none");
  let area = $state<HTMLTextAreaElement | null>(null);

  const draft = (): Draft => ({ title, summary, tags: tagsFrom(tagsText), author, body, slug: slug.trim() || null });
  const sent = { text: "" }; // the draft as last sent (not reactive: compared on each change)
  const localKey = () => post?.id ?? "new";
  const published = $derived(post?.status === "published");
  const deleted = $derived(post?.status === "deleted");
  const size = $derived(bytesOf(body));
  const over = $derived(size > LIMIT_KB * 1024);
  const publicUrl = $derived(post ? `${location.origin}/blog/${post.slug}` : "");

  function fill(p: EditorPost) {
    post = p;
    title = p.title;
    summary = p.summary;
    tagsText = p.tags.join(", ");
    author = p.author;
    body = p.body ?? "";
    slug = p.slug;
    slugTouched = true;
    preview = body;
    sent.text = JSON.stringify(draft());
  }

  // ---- loading: the account, then whether it writes, then the post (or a new one)
  let loadedFor: string | null = "unset";
  $effect(() => {
    const want = id;
    if (loadedFor === want || (want && post?.id === want)) return; // our own address change after the first save
    loadedFor = want;
    void load(want);
  });
  async function load(want: string | null) {
    gate = "loading";
    const st = await loadStatus();
    if (!st.enabled || !st.signed_in) {
      gate = st.enabled ? "signed_out" : "missing";
      return;
    }
    const ok = await checkEditor();
    if (!ok) {
      gate = "not_editor";
      return;
    }
    if (!want) {
      post = null;
      title = summary = tagsText = body = slug = "";
      slugTouched = false;
      author = editor.mine?.author ?? "";
      sent.text = JSON.stringify(draft());
      offer = readLocal("new");
      gate = "ok";
      return;
    }
    try {
      fill(await editorApi.post(want));
      const local = readLocal(want);
      offer = local && local.body !== body && local.revision >= (post?.revision ?? 0) ? local : null;
      gate = "ok";
    } catch (e) {
      gate = e instanceof EditorError && e.status === 404 ? "missing" : e instanceof EditorError && e.status === 401 ? "signed_out" : "failed";
    }
  }

  // ---- the address follows the title until the writer types one (a draft only)
  $effect(() => {
    if (!slugTouched && !published) slug = title.trim() ? slugFrom(title) : "";
  });

  // ---- every change: the device copy at once (cheap), the server's after a pause (a draft), the preview debounced
  let saveTimer: ReturnType<typeof setTimeout> | undefined;
  let previewTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const text = JSON.stringify(draft());
    if (gate !== "ok" || deleted) return;
    if (text === sent.text) return;
    keepLocal(localKey(), draft(), post?.revision ?? 0);
    saveState = "dirty";
    clearTimeout(saveTimer);
    if (!published && !conflict && !over) saveTimer = setTimeout(() => void save(true), AUTOSAVE_MS);
  });
  $effect(() => {
    const b = body;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => (preview = b), b.length > 20_000 ? 400 : 150);
  });
  onDestroy(() => {
    clearTimeout(saveTimer);
    clearTimeout(previewTimer);
  });

  let inFlight: Promise<boolean> | null = null;
  /** Send the draft (create it on the first save). True when the server holds this text. */
  async function save(auto = false): Promise<boolean> {
    if (inFlight) await inFlight;
    const d = draft();
    const text = JSON.stringify(d);
    if (post && text === sent.text) return true;
    if (over) {
      problem = `The post is over ${LIMIT_KB} KB. Split it in two.`;
      saveState = "error";
      return false;
    }
    saveState = "saving";
    inFlight = (async () => {
      try {
        const p = post ? await editorApi.save(post.id, d, post.revision, auto) : await editorApi.create(d);
        const first = !post;
        post = { ...p, body: d.body };
        sent.text = text;
        slugWords = p.slug_words ?? null;
        if (p.slug !== slug && (first || p.slug_problem)) {
          slug = p.slug; // the server's address (a file or another post held the one asked for)
          sent.text = JSON.stringify(draft());
        }
        problem = null;
        savedAt = new Date();
        saveState = JSON.stringify(draft()) === sent.text ? "saved" : "dirty";
        if (first) {
          dropLocal("new");
          navigate(`/blog/edit/${p.id}`, { replace: true });
        }
        if (saveState === "saved") dropLocal(p.id);
        if (p.status === "published") forgetPublic(p.slug);
        return true;
      } catch (e) {
        if (e instanceof EditorError && e.code === "conflict" && e.post) {
          conflict = e.post;
          saveState = "error";
          problem = e.message;
        } else {
          saveState = "error";
          problem = e instanceof Error ? e.message : "Not saved.";
        }
        return false;
      } finally {
        inFlight = null;
      }
    })();
    return inFlight;
  }

  function useNewer() {
    if (!conflict) return;
    const c = conflict;
    conflict = null;
    fill(c);
    dropLocal(c.id);
    saveState = "saved";
    problem = null;
  }
  async function keepMine() {
    if (!conflict || !post) return;
    post = { ...post, revision: conflict.revision, status: conflict.status, slug: conflict.slug };
    conflict = null;
    sent.text = "";
    await save(false);
  }
  function restoreLocal() {
    if (!offer) return;
    title = offer.title;
    summary = offer.summary;
    tagsText = offer.tags.join(", ");
    author = offer.author;
    body = offer.body;
    if (offer.slug) slug = offer.slug;
    slugTouched = !!offer.slug;
    offer = null;
  }

  function forgetPublic(s: string) {
    forget(blogPaths.list(50));
    forget(blogPaths.list(20));
    forget(blogPaths.post(s));
  }

  async function act(what: "publish" | "unpublish" | "delete" | "restore") {
    if (!post && what !== "publish") return;
    if (what === "publish" && !(await save(false))) return;
    if (!post) return;
    try {
      const p =
        what === "publish"
          ? await editorApi.publish(post.id, post.revision)
          : what === "unpublish"
            ? await editorApi.unpublish(post.id)
            : what === "delete"
              ? await editorApi.remove(post.id)
              : await editorApi.restore(post.id);
      post = { ...p, body };
      problem = null;
      confirmDelete = false;
      forgetPublic(p.slug);
      void checkEditor(true);
      if (what === "publish") copied = "idle";
    } catch (e) {
      if (e instanceof EditorError && e.code === "conflict" && e.post) conflict = e.post;
      problem = e instanceof Error ? e.message : "That did not work.";
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(publicUrl);
      copied = "copied";
      setTimeout(() => (copied = "idle"), 2500);
    } catch {
      copied = "manual";
    }
  }

  async function fromStarter(kind: StarterKind) {
    if (starting) return;
    starting = kind;
    problem = null;
    try {
      const d = await starter(kind);
      title = d.title;
      summary = d.summary;
      tagsText = d.tags.join(", ");
      if (!author) author = d.author;
      body = d.body;
      slugTouched = false;
    } catch {
      problem = "The week's numbers did not load. Try again in a minute.";
    } finally {
      starting = null;
    }
  }

  // ---- the toolbar: edits at the cursor in the body
  function edit(fn: (before: string, sel: string, after: string) => { text: string; start: number; end: number }) {
    const el = area;
    const s = el?.selectionStart ?? body.length;
    const e = el?.selectionEnd ?? body.length;
    const r = fn(body.slice(0, s), body.slice(s, e), body.slice(e));
    body = r.text;
    queueMicrotask(() => {
      el?.focus();
      el?.setSelectionRange(r.start, r.end);
    });
  }
  const wrap = (mark: string, placeholder: string) =>
    edit((b, sel, a) => {
      const inner = sel || placeholder;
      return { text: `${b}${mark}${inner}${mark}${a}`, start: b.length + mark.length, end: b.length + mark.length + inner.length };
    });
  const prefix = (p: string, placeholder: string) =>
    edit((b, sel, a) => {
      const lineStart = b.lastIndexOf("\n") + 1;
      const head = b.slice(0, lineStart);
      const lines = (b.slice(lineStart) + (sel || placeholder)).split("\n").map((l) => (l.startsWith(p) ? l : p + l));
      const mid = lines.join("\n");
      return { text: head + mid + a, start: head.length, end: head.length + mid.length };
    });
  const insert = (text: string) =>
    edit((b, _sel, a) => {
      const lead = b && !b.endsWith("\n\n") ? (b.endsWith("\n") ? "\n" : "\n\n") : "";
      const t = lead + text;
      return { text: b + t + a, start: b.length + t.length, end: b.length + t.length };
    });
  const linkAt = () =>
    edit((b, sel, a) => {
      const words = sel || "words";
      const t = `[${words}](https://)`;
      return { text: b + t + a, start: b.length + words.length + 3, end: b.length + t.length - 1 };
    });
  const TABLE = "| Player | Note |\n|---|---|\n| | |\n";

  // ---- Player: search → [Name](/player/<gsis>)
  let q = $state("");
  let hits = $state<Hit[]>([]);
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  function onSearch() {
    clearTimeout(searchTimer);
    const text = q.trim();
    if (text.length < 2) {
      hits = [];
      return;
    }
    searchTimer = setTimeout(() => {
      get<Hit[]>(paths.search(REF_DEFAULT, text))
        .then((h) => q.trim() === text && (hits = h.slice(0, 8)))
        .catch(() => (hits = []));
    }, 200);
  }
  const plainName = (s: string) => s.replace(/[[\]()*`|]/g, "").trim();
  function pickPlayer(h: Hit) {
    if (panel === "player") {
      edit((b, _sel, a) => {
        const t = `[${plainName(h.player_name)}](/player/${h.gsis_id})`;
        return { text: b + t + a, start: b.length + t.length, end: b.length + t.length };
      });
      panel = "none";
    } else if (!picked.some((p) => p.gsis_id === h.gsis_id) && picked.length < MAX_PLAYERS) picked = [...picked, h];
    q = "";
    hits = [];
  }

  // ---- Players table: pick players and columns → the ```players block (one per post: components/blog/PlayersBlock)
  let picked = $state<Hit[]>([]);
  let cols = $state<string[]>([...DEFAULT_COLS]);
  let catalogue = $state<StatsColumn[]>([]);
  $effect(() => {
    if (panel !== "table" || catalogue.length) return;
    get<StatsFrame>(statsPath(REF_DEFAULT, { position: "ALL", window: "season" }))
      .then((f) => (catalogue = f.catalogue.filter((c) => c.status !== "unavailable")))
      .catch(() => (catalogue = []));
  });
  const hasBlock = $derived(/^ {0,3}```players[ \t]*$/m.test(body));
  function toggleCol(c: string) {
    cols = cols.includes(c) ? cols.filter((x) => x !== c) : cols.length < MAX_COLS ? [...cols, c] : cols;
  }
  function insertTable() {
    if (!picked.length) return;
    insert("```players\n" + picked.map((p) => p.gsis_id).join("\n") + `\ncols: ${cols.join(", ")}\n` + "```\n");
    picked = [];
    panel = "none";
  }

  // ---- Picture: upload (PNG / JPEG / WebP, ≤ 300 KB) → ![words](/blog/img/db/<id>); the ones uploaded before
  let images = $state<EditorImage[]>([]);
  let uploading = $state(false);
  let picWords = $state<string | null>(null);
  $effect(() => {
    if (panel === "picture") images = editor.mine?.images ?? [];
  });
  async function onFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const f = input.files?.[0];
    input.value = "";
    if (!f) return;
    picWords = null;
    if (f.size > 300 * 1024) {
      picWords = "A picture is 300 KB at most. Make it smaller first.";
      return;
    }
    uploading = true;
    try {
      const img = await uploadImage(f);
      images = [img, ...images];
      insertImage(img, f.name.replace(/\.[a-z0-9]+$/i, ""));
      void checkEditor(true);
    } catch (err) {
      picWords = err instanceof Error ? err.message : "The picture did not upload.";
    } finally {
      uploading = false;
    }
  }
  function insertImage(img: EditorImage, words = "A picture") {
    insert(`![${plainName(words).replace(/[!]/g, "") || "A picture"}](${img.url})\n`);
    panel = "none";
  }
  async function deleteImage(img: EditorImage) {
    try {
      await editorApi.removeImage(img.id);
      images = images.filter((x) => x.id !== img.id);
      void checkEditor(true);
    } catch (err) {
      picWords = err instanceof Error ? err.message : "That did not work.";
    }
  }

  // ---- Earlier versions: the server keeps the last 20 (blog.revisions); one tap puts one back as the text being edited
  let versions = $state<NonNullable<EditorPost["revisions"]> | null>(null);
  let versionWords = $state<string | null>(null);
  async function openVersions() {
    if (!post) return;
    if (versions) {
      versions = null;
      return;
    }
    try {
      versions = (await editorApi.post(post.id)).revisions ?? [];
    } catch (e) {
      problem = e instanceof Error ? e.message : "The earlier versions did not load.";
    }
  }
  const at = (t: string | null) => (t ? new Date(t).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");
  async function loadVersion(rid: number) {
    if (!post) return;
    try {
      const v = await editorApi.revision(post.id, rid);
      title = v.title;
      body = v.body;
      versions = null;
      versionWords = `The version saved ${at(v.saved_at)} is back in the editor. It saves as a new version: nothing is lost.`;
    } catch (e) {
      problem = e instanceof Error ? e.message : "That version did not load.";
    }
  }

  const savedWords = $derived.by(() => {
    if (deleted) return "Deleted";
    if (saveState === "saving") return "Saving…";
    if (saveState === "error") return "Not saved";
    if (saveState === "dirty") return published ? "Changes not saved yet" : "Saving soon…";
    if (savedAt) return `Saved ${savedAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
    return post ? "Saved" : "";
  });
</script>

{#snippet tool(label: string, run: () => void, testid: string, wide = false)}
  <button
    type="button"
    class="inline-flex min-h-10 items-center rounded-md border border-line bg-surface px-2.5 text-sm font-semibold hover:bg-raised {wide ? 'px-3' : ''}"
    onclick={run}
    data-testid={testid}>{label}</button
  >
{/snippet}

<main class="space-y-4 pb-10" data-testid="blog-editor">
  <a href="/blog" class="ll-link inline-block py-1 text-base">‹ Blog</a>
  {#if gate === "loading"}
    <div class="space-y-3" aria-label="Loading"><div class="ll-skel h-10 w-1/2"></div><div class="ll-skel h-64"></div></div>
  {:else if gate !== "ok"}
    <section class="max-w-xl space-y-2 rounded-lg border border-line bg-surface p-5" data-testid="editor-closed">
      {#if gate === "signed_out"}
        <h1 class="text-xl font-bold">Sign in to write</h1>
        <p class="text-ink-2">Writing on the blog needs the editor's account. <a class="ll-link" href="/account">Sign in</a></p>
      {:else if gate === "not_editor"}
        <h1 class="text-xl font-bold">This account does not write on the blog</h1>
        <p class="text-ink-2">The blog has one editor for now. <a class="ll-link" href="/blog">Read the blog</a></p>
      {:else if gate === "missing"}
        <h1 class="text-xl font-bold">No post at that address.</h1>
        <p class="text-ink-2"><a class="ll-link" href="/blog">See every post</a></p>
      {:else}
        <h1 class="text-xl font-bold">The editor did not load</h1>
        <p class="text-ink-2">Try again in a minute.</p>
      {/if}
    </section>
  {:else}
    <header class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <h1 class="text-2xl font-extrabold tracking-tight">{post ? "Edit post" : "Write a post"}</h1>
      {#if post}
        <span
          class="rounded-sm px-1.5 text-xs font-semibold {published ? 'bg-accent-soft text-ink' : deleted ? 'bg-bad-soft text-ink' : 'bg-warn-soft text-ink'}"
          data-testid="editor-status">{published ? "Published" : deleted ? "Deleted" : "Draft"}</span
        >
      {/if}
      <span class="text-sm text-ink-3" aria-live="polite" data-testid="editor-saved">{savedWords}</span>
    </header>

    {#if offer}
      <div class="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-raised p-3 text-sm" data-testid="editor-local">
        <span>This device kept text that was not saved{offer.at ? ` (${new Date(offer.at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })})` : ""}.</span>
        <button type="button" class="ll-link font-semibold" onclick={restoreLocal} data-testid="editor-local-restore">Put it back</button>
        <button
          type="button"
          class="ll-link"
          onclick={() => {
            dropLocal(localKey());
            offer = null;
          }}>Discard it</button
        >
      </div>
    {/if}

    {#if conflict}
      <div class="space-y-2 rounded-lg border border-bad bg-bad-soft p-3 text-sm" role="alert" data-testid="editor-conflict">
        <p>This post was changed in another tab or on another device (saved version {conflict.revision}). Nothing was overwritten.</p>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="min-h-10 rounded-md border border-line bg-surface px-3 font-semibold" onclick={useNewer} data-testid="conflict-newer"
            >Use the newer version</button
          >
          <button type="button" class="min-h-10 rounded-md border border-line bg-surface px-3 font-semibold" onclick={keepMine} data-testid="conflict-mine"
            >Keep mine and save it over</button
          >
        </div>
      </div>
    {:else if problem}
      <p class="rounded-lg bg-bad-soft p-3 text-sm" role="alert" data-testid="editor-problem">{problem}</p>
    {/if}

    {#if !post && !body.trim()}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-3" data-testid="editor-starters">
        <h2 class="ll-label">New post from…</h2>
        <div class="grid gap-2 wide:grid-cols-3">
          {#each STARTERS as s (s.kind)}
            <button
              type="button"
              class="min-h-11 rounded-md border border-line px-3 py-2 text-left hover:bg-raised disabled:opacity-60"
              disabled={starting !== null}
              onclick={() => fromStarter(s.kind)}
              data-testid={`starter-${s.kind}`}
            >
              <span class="block font-semibold">{starting === s.kind ? "Filling in…" : s.label}</span>
              <span class="block text-sm text-ink-3">{s.hint}</span>
            </button>
          {/each}
        </div>
        <p class="text-sm text-ink-3">A starter fills a draft with this week's numbers written in, on Half PPR. It never publishes by itself.</p>
      </section>
    {/if}

    <div class="grid grid-cols-[minmax(0,1fr)] gap-3 wide:grid-cols-2">
      <label class="block wide:col-span-2">
        <span class="ll-label">Title</span>
        <input class="ll-input mt-1 w-full text-lg font-semibold" maxlength="140" bind:value={title} disabled={deleted} data-testid="editor-title" />
      </label>
      <label class="block wide:col-span-2">
        <span class="ll-label">Summary <span class="font-normal text-ink-3">(the list, link previews and the feed show it)</span></span>
        <textarea class="ll-input mt-1 w-full" rows="2" maxlength="400" bind:value={summary} disabled={deleted} data-testid="editor-summary"></textarea>
      </label>
      <label class="block">
        <span class="ll-label">Tags <span class="font-normal text-ink-3">(commas between)</span></span>
        <input class="ll-input mt-1 w-full" bind:value={tagsText} disabled={deleted} placeholder="matchups, week 5" data-testid="editor-tags" />
      </label>
      <label class="block">
        <span class="ll-label">Author line</span>
        <input class="ll-input mt-1 w-full" maxlength="60" bind:value={author} disabled={deleted} placeholder="isuckatfantasy" data-testid="editor-author" />
      </label>
      <label class="block wide:col-span-2">
        <span class="ll-label">Address</span>
        <span class="mt-1 flex items-center gap-1">
          <span class="text-sm text-ink-3">/blog/</span>
          <input
            class="ll-input w-full min-w-0 font-mono text-sm"
            maxlength="80"
            bind:value={slug}
            oninput={() => (slugTouched = true)}
            disabled={published || deleted}
            data-testid="editor-slug"
          />
        </span>
        {#if published}<span class="mt-1 block text-sm text-ink-3">A published post keeps its address.</span>{/if}
        {#if slugWords}<span class="mt-1 block text-sm text-bad" data-testid="editor-slug-words">{slugWords}</span>{/if}
      </label>
    </div>

    <div class="flex flex-wrap items-center gap-1.5" role="toolbar" aria-label="Formatting" data-testid="editor-toolbar">
      {@render tool("Bold", () => wrap("**", "bold words"), "tool-bold")}
      {@render tool("Heading", () => prefix("## ", "A heading"), "tool-heading")}
      {@render tool("List", () => prefix("- ", "A point"), "tool-list")}
      {@render tool("Quote", () => prefix("> ", "Quoted words"), "tool-quote")}
      {@render tool("Link", linkAt, "tool-link")}
      {@render tool("Table", () => insert(TABLE), "tool-table")}
      {@render tool("Player", () => (panel = panel === "player" ? "none" : "player"), "tool-player", true)}
      {@render tool("Players table", () => (panel = panel === "table" ? "none" : "table"), "tool-players-table", true)}
      {@render tool("Picture", () => (panel = panel === "picture" ? "none" : "picture"), "tool-picture", true)}
    </div>

    {#if panel === "picture"}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-3" data-testid="editor-picture">
        <label class="block">
          <span class="ll-label">Add a picture <span class="font-normal text-ink-3">(PNG, JPEG or WebP, 300 KB at most)</span></span>
          <input type="file" accept="image/png,image/jpeg,image/webp" class="mt-1 block w-full text-sm" onchange={onFile} disabled={uploading} data-testid="picture-file" />
        </label>
        {#if uploading}<p class="text-sm text-ink-3">Uploading…</p>{/if}
        {#if picWords}<p class="text-sm text-bad" role="alert" data-testid="picture-problem">{picWords}</p>{/if}
        {#if images.length}
          <h3 class="ll-label">Your pictures ({images.length} of {editor.mine?.limits.images ?? 50})</h3>
          <ul class="grid grid-cols-2 gap-2 wide:grid-cols-4" data-testid="picture-list">
            {#each images as img (img.id)}
              <li class="space-y-1 rounded-md border border-line p-2">
                <img src={img.url} alt="" class="h-20 w-full rounded-sm object-cover" loading="lazy" />
                <div class="flex flex-wrap gap-2 text-sm">
                  <button type="button" class="ll-link font-semibold" onclick={() => insertImage(img)}>Insert</button>
                  <button type="button" class="ll-link" onclick={() => deleteImage(img)}>Delete</button>
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {:else if panel !== "none"}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-3" data-testid="editor-panel">
        <label class="block">
          <span class="ll-label">{panel === "player" ? "Link a player" : `Players for the table (up to ${MAX_PLAYERS})`}</span>
          <input class="ll-input mt-1 w-full" placeholder="Search a name" bind:value={q} oninput={onSearch} data-testid="panel-search" />
        </label>
        {#if hits.length}
          <ul class="divide-y divide-line rounded-md border border-line" data-testid="panel-hits">
            {#each hits as h (h.gsis_id)}
              <li>
                <button type="button" class="block min-h-11 w-full px-3 py-2 text-left hover:bg-raised" onclick={() => pickPlayer(h)} data-testid="panel-hit"
                  >{h.player_name} <span class="text-sm text-ink-3">{h.position} · {h.nfl_team ?? "–"}</span></button
                >
              </li>
            {/each}
          </ul>
        {/if}
        {#if panel === "table"}
          {#if hasBlock}<p class="text-sm text-ink-3">This post already has a players table: only the first one becomes a table.</p>{/if}
          <div class="flex flex-wrap gap-1.5" data-testid="panel-picked">
            {#each picked as p (p.gsis_id)}
              <button type="button" class="rounded-full bg-raised px-2.5 py-1 text-sm" onclick={() => (picked = picked.filter((x) => x.gsis_id !== p.gsis_id))}
                >{p.player_name} ✕</button
              >
            {/each}
          </div>
          <fieldset>
            <legend class="ll-label">Columns (up to {MAX_COLS})</legend>
            <div class="mt-1 flex max-h-48 flex-wrap gap-1.5 overflow-y-auto">
              {#each catalogue.length ? catalogue : DEFAULT_COLS.map((c) => ({ id: c, label: c }) as StatsColumn) as c (c.id)}
                <label class="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-line px-2 text-sm">
                  <input type="checkbox" checked={cols.includes(c.id)} onchange={() => toggleCol(c.id)} />{c.label}
                </label>
              {/each}
            </div>
          </fieldset>
          <button
            type="button"
            class="min-h-11 rounded-md bg-accent px-4 font-semibold text-on-accent disabled:opacity-50"
            disabled={!picked.length}
            onclick={insertTable}
            data-testid="panel-insert-table">Insert the table</button
          >
          <p class="text-sm text-ink-3">The table shows each player's Stats row, Half PPR, season to date — it updates with every nightly.</p>
        {/if}
      </section>
    {/if}

    <div class="flex rounded-md border border-line p-0.5 wide:hidden" role="tablist" aria-label="Write or preview" data-testid="editor-switch">
      {#each [["write", "Write"], ["preview", "Preview"]] as [k, label] (k)}
        <button
          type="button"
          role="tab"
          aria-selected={view === k}
          class="min-h-10 flex-1 rounded-[5px] text-sm font-semibold {view === k ? 'bg-accent text-on-accent' : ''}"
          onclick={() => (view = k as "write" | "preview")}
          data-testid={`switch-${k}`}>{label}</button
        >
      {/each}
    </div>

    <div class="grid grid-cols-[minmax(0,1fr)] gap-4 wide:grid-cols-2 wide:items-start">
      <div class="min-w-0 {view === 'write' ? '' : 'hidden wide:block'}">
        <label class="block">
          <span class="ll-label">The post <span class="font-normal text-ink-3">(markdown)</span></span>
          <textarea
            bind:this={area}
            bind:value={body}
            disabled={deleted}
            class="ll-input mt-1 min-h-[55vh] w-full font-mono text-[0.9375rem] leading-relaxed wide:min-h-[65vh]"
            spellcheck="true"
            data-testid="editor-body"
          ></textarea>
        </label>
        <p class="mt-1 text-sm {over ? 'font-semibold text-bad' : 'text-ink-3'}" data-testid="editor-size">
          {(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB of {LIMIT_KB} KB
        </p>
        <p class="mt-1 text-sm text-ink-3" data-testid="editor-pictures">
          Pictures: <strong>Picture</strong> above uploads one (PNG, JPEG or WebP, 300 KB at most). A file in <code>blog/img/</code> in the repository works too:
          <code>![words](/blog/img/name.png)</code>.
        </p>
      </div>
      <section class="min-w-0 {view === 'preview' ? '' : 'hidden wide:block'}" aria-label="Preview" data-testid="editor-preview">
        <span class="ll-label">Preview</span>
        <div class="mt-1 rounded-lg border border-line bg-surface p-4 wide:max-h-[75vh] wide:overflow-y-auto">
          <h2 class="text-2xl leading-tight font-extrabold break-words" data-testid="preview-title">{title || "Untitled"}</h2>
          {#if preview.trim()}
            <PostBody markdown={preview} {league} />
          {:else}
            <p class="mt-3 text-ink-3">The post shows here as readers will see it.</p>
          {/if}
        </div>
      </section>
    </div>

    <div class="flex flex-wrap items-center gap-2 border-t border-line pt-3" data-testid="editor-actions">
      {#if deleted}
        <button type="button" class="min-h-11 rounded-md bg-accent px-4 font-semibold text-on-accent" onclick={() => act("restore")} data-testid="editor-restore"
          >Restore as a draft</button
        >
        <span class="text-sm text-ink-3">Deleted posts can be restored for {editor.mine?.limits.restore_days ?? 30} days.</span>
      {:else}
        {#if published}
          <button
            type="button"
            class="min-h-11 rounded-md bg-accent px-4 font-semibold text-on-accent disabled:opacity-50"
            disabled={saveState === "saving" || saveState === "saved" || saveState === "idle"}
            onclick={() => save(false)}
            data-testid="editor-save">Save changes</button
          >
          <button type="button" class="min-h-11 rounded-md border border-line px-4 font-semibold" onclick={() => act("unpublish")} data-testid="editor-unpublish"
            >Unpublish</button
          >
        {:else}
          <button
            type="button"
            class="min-h-11 rounded-md bg-accent px-4 font-semibold text-on-accent disabled:opacity-50"
            disabled={!title.trim() || over || saveState === "saving"}
            onclick={() => act("publish")}
            data-testid="editor-publish">Publish</button
          >
        {/if}
        {#if post}
          {#if confirmDelete}
            <button type="button" class="min-h-11 rounded-md border border-bad px-4 font-semibold text-bad" onclick={() => act("delete")} data-testid="editor-delete-confirm"
              >Delete it</button
            >
            <button type="button" class="ll-link" onclick={() => (confirmDelete = false)}>Keep it</button>
          {:else}
            <button type="button" class="min-h-11 rounded-md border border-line px-4 font-semibold" onclick={() => (confirmDelete = true)} data-testid="editor-delete"
              >Delete</button
            >
          {/if}
        {/if}
      {/if}
      {#if post && !deleted}<button type="button" class="ll-link ml-auto text-sm" onclick={openVersions} data-testid="editor-versions">Earlier versions</button>{/if}
      <a class="ll-link text-sm {post && !deleted ? '' : 'ml-auto'}" href={EXPORT_PATH} download data-testid="editor-export">Download every post</a>
    </div>
    {#if versionWords}<p class="rounded-lg bg-accent-soft p-3 text-sm" role="status" data-testid="editor-version-words">{versionWords}</p>{/if}
    {#if versions}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-3 text-sm" data-testid="editor-version-list">
        <h2 class="ll-label">Earlier versions <span class="font-normal text-ink-3">(the last {editor.mine?.limits.revisions ?? 20} kept)</span></h2>
        {#if !versions.length}<p class="text-ink-3">No earlier versions yet.</p>{/if}
        <ul class="divide-y divide-line">
          {#each versions as v (v.id)}
            <li class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span>{at(v.saved_at)}</span>
              <span class="text-ink-3">{(v.bytes / 1024).toFixed(1)} KB</span>
              <button type="button" class="ll-link ml-auto font-semibold" onclick={() => loadVersion(v.id)} data-testid="editor-version-load">Put this one back</button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if published && post}
      <div class="space-y-1 rounded-lg border border-line bg-surface p-3 text-sm" data-testid="editor-live">
        <p>
          Live at <a class="ll-link" href={`/blog/${post.slug}`} data-testid="editor-live-link">/blog/{post.slug}</a>
          <button type="button" class="ml-2 inline-flex min-h-9 items-center rounded-md border border-line px-3 font-semibold" onclick={copyLink} data-testid="editor-copy"
            >{copied === "copied" ? "Link copied" : "Copy link"}</button
          >
        </p>
        {#if copied === "manual"}
          <input class="ll-input w-full py-1.5 text-sm" readonly value={publicUrl} onfocus={(e) => e.currentTarget.select()} />
        {/if}
      </div>
    {/if}
  {/if}
</main>
