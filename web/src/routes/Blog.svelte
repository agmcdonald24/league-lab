<script lang="ts">
  // ---- IN-1 (Wave I-N): the blog — the list ("/blog") and a post ("/blog/<slug>"). Posts are markdown files in the
  // repository (blog/*.md; docs/BLOG.md) served by GET /api/blog and /api/blog/{slug}; a post is rendered by
  // lib/md.ts `mdDoc` (escaped first: no raw HTML). A player link in a post opens his card in the drawer like everywhere.
  import { APP_NAME } from "../lib/brand";
  import { ApiError, blogPaths, get, type BlogMeta, type BlogPost } from "../lib/api";
  import { longDate } from "../components/home/home";
  import PostBody from "../components/blog/PostBody.svelte";
  import { coverSrc } from "../components/blog/cover";
  // ---- IO-3 (Wave I-O): an editor (an account the server lists in LEAGUE_LAB_EDITORS) sees "Write a post" and their
  // own posts here; everyone else sees exactly the blog as before (the check is quiet: any failure is "not an editor")
  import { loadStatus } from "../lib/account.svelte";
  import { checkEditor, editor } from "../components/blog/editor.svelte";
  // ---- end IO-3

  let { slug = null, league }: { slug?: string | null; league: string } = $props();
  // ---- IO-3: the editor's own posts and "Edit" on a post of theirs
  $effect(() => void loadStatus().then(() => checkEditor()));
  const minePosts = $derived(editor.on ? (editor.mine?.posts ?? []) : []);
  const editOf = $derived(slug && editor.on ? (minePosts.find((p) => p.slug === slug && p.status === "published")?.id ?? null) : null);
  // ---- end IO-3

  let posts = $state<BlogMeta[] | null>(null);
  let listState = $state<"loading" | "ok" | "failed">("loading");
  $effect(() => {
    get<{ posts: BlogMeta[] }>(blogPaths.list(50))
      .then((d) => {
        posts = d.posts;
        listState = "ok";
      })
      .catch(() => (listState = "failed"));
  });

  let copied = $state<"idle" | "copied" | "manual">("idle");
  let post = $state<BlogPost | null>(null);
  let postState = $state<"loading" | "ok" | "missing" | "failed">("loading");
  $effect(() => {
    const s = slug;
    if (!s) return;
    post = null;
    postState = "loading";
    copied = "idle";
    get<BlogPost>(blogPaths.post(s))
      .then((p) => {
        if (slug !== s) return;
        post = p;
        postState = "ok";
      })
      .catch((e) => {
        if (slug === s) postState = e instanceof ApiError && e.status === 404 ? "missing" : "failed";
      });
  });

  // the tab's title follows the post (the server writes it for a link opened from outside)
  $effect(() => {
    const before = document.title;
    document.title = slug && post ? `${post.title} · ${APP_NAME}` : `Blog · ${APP_NAME}`;
    return () => (document.title = before);
  });

  const shareUrl = $derived(slug ? `${location.origin}/blog/${slug}` : "");
  async function copyLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      copied = "copied";
      setTimeout(() => (copied = "idle"), 2500);
    } catch {
      copied = "manual"; // no clipboard (an app's browser, a denied permission): the address to copy by hand
    }
  }
  const others = $derived((posts ?? []).filter((p) => p.slug !== slug).slice(0, 3));
</script>

{#snippet postMeta(p: BlogMeta)}
  <span>{longDate(p.date)} · {p.minutes} min read</span>{#if p.draft}<span
      class="ml-2 rounded-sm bg-warn-soft px-1.5 text-xs font-semibold text-ink">Draft</span
    >{/if}
{/snippet}

{#snippet aside()}
  <aside class="space-y-4 text-sm leading-snug" data-testid="blog-aside">
    <div class="rounded-lg border border-line bg-surface p-4">
      <h2 class="ll-label">About this blog</h2>
      <p class="mt-1 text-ink-2">
        Analysis from {APP_NAME}: what the numbers say, how they are made, and where they have been wrong. Every player number links to his card.
      </p>
      <p class="mt-2"><a class="ll-link" href="/blog/rss.xml" target="_blank" rel="noopener">RSS feed</a></p>
    </div>
    <div class="rounded-lg border border-line bg-surface p-4">
      <h2 class="ll-label">The tools</h2>
      <ul class="mt-1 space-y-1">
        <li><a class="ll-link" href={`/players?league=${league}`}>Every player's numbers</a></li>
        <li><a class="ll-link" href={`/matchups?league=${league}`}>This week's matchups</a></li>
        <li><a class="ll-link" href={`/trade-calc?league=${league}`}>Trade calculator</a></li>
        <li><a class="ll-link" href="/home">Home</a></li>
      </ul>
    </div>
  </aside>
{/snippet}

{#if !slug}
  <!-- the list -->
  <main class="space-y-5 pb-6" data-testid="blog">
    <header class="space-y-1">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h1 class="text-2xl font-extrabold tracking-tight wide:text-3xl">Blog</h1>
        {#if editor.on}<a href="/blog/new" class="inline-flex min-h-11 items-center rounded-md bg-accent px-4 font-semibold text-on-accent" data-testid="blog-write"
            >Write a post</a
          >{/if}<!-- ---- IO-3 -->
      </div>
      <p class="text-base leading-snug text-ink-2">Fantasy football analysis: what the numbers say, and how far to trust them.</p>
    </header>
    <!-- ---- IO-3: the editor's own posts (drafts, published, deleted) -->
    {#if minePosts.length}
      <section class="space-y-2 rounded-lg border border-line bg-surface p-4" data-testid="blog-mine">
        <h2 class="ll-label">Your posts</h2>
        <ul class="divide-y divide-line">
          {#each minePosts as p (p.id)}
            <li class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2" data-testid="blog-mine-item" data-status={p.status}>
              <a class="ll-link min-w-0 font-semibold break-words" href={`/blog/edit/${p.id}`}>{p.title || "Untitled"}</a>
              <span
                class="rounded-sm px-1.5 text-xs font-semibold text-ink {p.status === 'published' ? 'bg-accent-soft' : p.status === 'deleted' ? 'bg-bad-soft' : 'bg-warn-soft'}"
                >{p.status === "published" ? "Published" : p.status === "deleted" ? "Deleted" : "Draft"}</span
              >
              {#if p.date}<span class="text-sm text-ink-3">{longDate(p.date)}</span>{/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}
    <!-- ---- end IO-3 -->
    <div class="grid gap-6 wide:grid-cols-[minmax(0,1fr)_18rem] wide:items-start wide:gap-10">
      <section aria-label="Posts">
        {#if listState === "loading"}
          <div class="space-y-3" aria-label="Loading"><div class="ll-skel h-24"></div><div class="ll-skel h-24"></div></div>
        {:else if listState === "failed"}
          <p class="rounded-lg bg-raised p-4 text-base" data-testid="blog-failed">The posts did not load. Try again in a minute.</p>
        {:else if !posts?.length}
          <p class="rounded-lg bg-raised p-4 text-base" data-testid="blog-empty">No posts yet. The first one is on its way.</p>
        {:else}
          <ol class="space-y-3" data-testid="blog-list">
            {#each posts as p (p.slug)}
              <li>
                <a href={`/blog/${p.slug}`} class="flex gap-3 rounded-lg border border-line bg-surface p-4 hover:border-line-strong wide:gap-5 wide:p-5" data-testid="blog-item" data-slug={p.slug}>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm text-ink-3">{@render postMeta(p)}</div>
                    <h2 class="mt-1 text-xl leading-snug font-bold break-words">{p.title}</h2>
                    {#if p.summary}<p class="mt-1 text-base leading-snug text-ink-2">{p.summary}</p>{/if}
                    {#if p.tags.length}
                      <div class="mt-2 flex flex-wrap gap-1.5">
                        {#each p.tags as t (t)}<span class="rounded-full bg-raised px-2 py-0.5 text-xs text-ink-2">{t}</span>{/each}
                      </div>
                    {/if}
                  </div>
                  {#if coverSrc(p.image)}<!-- ---- IU-6: the cover as the list's thumbnail -->
                    <img src={coverSrc(p.image)} alt="" loading="lazy" decoding="async" class="h-20 w-24 shrink-0 rounded-md bg-raised object-cover wide:h-28 wide:w-44" data-testid="blog-item-cover" />
                  {/if}
                </a>
              </li>
            {/each}
          </ol>
        {/if}
      </section>
      {@render aside()}
    </div>
  </main>
{:else}
  <!-- a post: a readable measure, the rest of the width for the aside -->
  <main class="pb-6" data-testid="blog-post">
    <div class="grid justify-center gap-8 wide:grid-cols-[minmax(0,44rem)_16rem] wide:gap-12">
      <article class="min-w-0" data-testid="post">
        <a href="/blog" class="ll-link inline-block py-1 text-base" data-testid="post-back">‹ Blog</a>
        {#if postState === "loading"}
          <div class="mt-3 space-y-3" aria-label="Loading"><div class="ll-skel h-10 w-3/4"></div><div class="ll-skel h-64"></div></div>
        {:else if postState === "missing"}
          <section class="mt-3 space-y-2 rounded-lg border border-line bg-surface p-5" data-testid="post-missing">
            <h1 class="text-xl font-bold">No post at that address.</h1>
            <p class="text-ink-2">It may have been renamed. <a class="ll-link" href="/blog">See every post</a>.</p>
          </section>
        {:else if postState === "failed" || !post}
          <p class="mt-3 rounded-lg bg-raised p-4 text-base" data-testid="post-failed">The post did not load. Try again in a minute.</p>
        {:else}
          <header class="mt-2 space-y-2 border-b border-line pb-4">
            {#if coverSrc(post.image)}<!-- ---- IU-6: the cover as the post's banner -->
              <img src={coverSrc(post.image)} alt="" decoding="async" fetchpriority="high" class="mb-3 aspect-[1200/630] w-full rounded-lg bg-raised object-cover" data-testid="post-cover" />
            {/if}
            <h1 class="text-3xl leading-tight font-extrabold tracking-tight wide:text-[2.5rem]" data-testid="post-title">{post.title}</h1>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-3">
              <span data-testid="post-meta">By {post.author} · {@render postMeta(post)}</span>
              {#if editOf}<a class="ll-link" href={`/blog/edit/${editOf}`} data-testid="post-edit">Edit</a>{/if}<!-- ---- IO-3 -->
              <button
                type="button"
                class="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-line px-3 font-semibold text-ink hover:bg-raised"
                onclick={copyLink}
                data-testid="post-share">{copied === "copied" ? "Link copied" : "Copy link"}</button
              >
            </div>
            {#if copied === "manual"}
              <label class="block text-sm text-ink-2"
                >Copy this link:
                <input class="ll-input mt-1 w-full py-1.5 text-sm" readonly value={shareUrl} onfocus={(e) => e.currentTarget.select()} data-testid="post-share-url" /></label
              >
            {/if}
            <span class="sr-only" aria-live="polite">{copied === "copied" ? "Link copied" : ""}</span>
          </header>
          <PostBody markdown={post.markdown} {league} />
          {#if post.tags.length}
            <div class="mt-6 flex flex-wrap gap-1.5 border-t border-line pt-4">
              {#each post.tags as t (t)}<span class="rounded-full bg-raised px-2 py-0.5 text-xs text-ink-2">{t}</span>{/each}
            </div>
          {/if}
          {#if others.length}
            <section class="mt-6 space-y-2" data-testid="post-more">
              <h2 class="ll-label">More from the blog</h2>
              <ul class="space-y-2">
                {#each others as p (p.slug)}
                  <li><a class="ll-link text-base" href={`/blog/${p.slug}`}>{p.title}</a> <span class="text-sm text-ink-3">· {longDate(p.date)}</span></li>
                {/each}
              </ul>
            </section>
          {/if}
        {/if}
      </article>
      <div class="hidden wide:block wide:pt-12">{@render aside()}</div>
    </div>
  </main>
{/if}
