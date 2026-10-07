// ---- IO-3 (Wave I-O): the blog editor's calls and state (api/league_lab_api/blog_store.py; docs/BLOG.md § "The editor").
// * Who may write is the server's answer: GET /api/blog/mine answers an editor (an account listed in LEAGUE_LAB_EDITORS)
//   and 401 / 403 / 404 everyone else — so nothing about writing shows unless the server says this account writes.
// * Writes are same-origin JSON with the session cookie (HttpOnly); a stale revision comes back 409 with the newer post.
// * The unsent text is also kept on this device (localStorage, in a try / catch): a dropped connection loses nothing.
import { account } from "../../lib/account.svelte";

export type PostStatus = "draft" | "published" | "deleted";

export interface EditorPost {
  id: string;
  slug: string;
  title: string;
  summary: string;
  tags: string[];
  author: string;
  status: PostStatus;
  revision: number;
  created_at: string | null;
  updated_at: string | null;
  published_at: string | null;
  deleted_at: string | null;
  minutes: number;
  bytes: number;
  date: string | null;
  body?: string;
  revisions?: { id: number; revision: number; saved_at: string | null; bytes: number }[];
  slug_problem?: string;
  slug_words?: string;
}

export interface EditorImage {
  id: string;
  url: string; // "/blog/img/db/<id>"
  kind: "png" | "jpg" | "webp";
  size: number;
  created_at: string | null;
}

export interface Mine {
  account_id: string;
  author: string;
  posts: EditorPost[];
  images?: EditorImage[];
  limits: { body_kb: number; posts: number; title: number; summary: number; tags: number; tag: number; slug: number; restore_days: number; revisions: number; image_kb?: number; images?: number };
}

export interface Draft {
  title: string;
  summary: string;
  tags: string[];
  author: string;
  body: string;
  slug: string | null;
}

/** An answer that is not OK: the API's words, its code, and (409 conflict) the newer post. */
export class EditorError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string,
    public post: EditorPost | null = null,
    public retryAfter: number | null = null, // ---- fix round (L1): seconds, from a 429's Retry-After
  ) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new EditorError(0, "offline", "No connection. Your text is kept on this device.");
  }
  let data: { code?: string; error?: string; detail?: string; post?: EditorPost } | null = null;
  try {
    data = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    const words = res.status === 413 && !data?.code ? "The post is too big to send. Split it in two." : (data?.error ?? data?.detail ?? res.statusText);
    const ra = Number(res.headers.get("Retry-After"));
    throw new EditorError(res.status, data?.code ?? null, typeof words === "string" ? words : "Something went wrong.", data?.post ?? null, Number.isFinite(ra) && ra > 0 ? ra : null);
  }
  return data as T;
}

export const editorApi = {
  mine: () => call<Mine>("GET", "/api/blog/mine"),
  post: (id: string) => call<EditorPost>("GET", `/api/blog/posts/${encodeURIComponent(id)}`),
  revision: (id: string, rid: number) => call<{ revision: number; title: string; body: string; saved_at: string | null }>("GET", `/api/blog/posts/${encodeURIComponent(id)}/revisions/${rid}`),
  create: (d: Draft) => call<EditorPost>("POST", "/api/blog/posts", d),
  save: (id: string, d: Draft, revision: number, autosave: boolean, slugAuto = false) =>
    call<EditorPost>("PUT", `/api/blog/posts/${encodeURIComponent(id)}`, { ...d, revision, autosave, slug_auto: slugAuto }),
  publish: (id: string, revision: number) => call<EditorPost>("POST", `/api/blog/posts/${encodeURIComponent(id)}/publish`, { revision }),
  unpublish: (id: string) => call<EditorPost>("POST", `/api/blog/posts/${encodeURIComponent(id)}/unpublish`),
  remove: (id: string) => call<EditorPost>("DELETE", `/api/blog/posts/${encodeURIComponent(id)}`),
  restore: (id: string) => call<EditorPost>("POST", `/api/blog/posts/${encodeURIComponent(id)}/restore`),
  removeImage: (id: string) => call<{ ok: boolean }>("DELETE", `/api/blog/images/${encodeURIComponent(id)}`),
};

/** A picture as it is (the server checks its first bytes: PNG, JPEG or WebP, ≤ 300 KB). */
export async function uploadImage(file: Blob): Promise<EditorImage> {
  let res: Response;
  try {
    res = await fetch("/api/blog/images", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/octet-stream", Accept: "application/json" }, body: file });
  } catch {
    throw new EditorError(0, "offline", "No connection. Try again in a minute.");
  }
  let data: { code?: string; error?: string } & Partial<EditorImage> = {};
  try {
    data = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) throw new EditorError(res.status, data.code ?? null, res.status === 413 && !data.code ? "A picture is 300 KB at most. Make it smaller first." : (data.error ?? "The picture did not upload."));
  return data as EditorImage;
}
export const EXPORT_PATH = "/api/blog/export";

/** Is the signed-in account an editor (asked once per sign-in; quiet: any failure is "no"). */
export const editor = $state<{ checked: boolean; on: boolean; mine: Mine | null }>({ checked: false, on: false, mine: null });
let asked: Promise<boolean> | null = null;
let askedFor = "";

export function checkEditor(force = false): Promise<boolean> {
  const who = account.status?.signed_in ? (account.me as { id?: string } | null)?.id ?? "signed-in" : "";
  if (!who) {
    editor.checked = true;
    editor.on = false;
    editor.mine = null;
    return Promise.resolve(false);
  }
  if (asked && !force && askedFor === who) return asked;
  askedFor = who;
  asked = editorApi
    .mine()
    .then((m) => {
      editor.mine = m;
      editor.on = true;
      return true;
    })
    .catch(() => {
      editor.mine = null;
      editor.on = false;
      return false;
    })
    .finally(() => (editor.checked = true));
  return asked;
}

// ---- the copy on this device (a dropped connection, a closed tab): one entry per post ("new" before the first save).
// Fix round (the review's note): the entries belong to the signed-in account (its id in the key: another account on
// this device never sees them), none is written for a signed-out visitor, and signing out clears them all
// (`forgetDrafts`, called by the Account screen's Sign out / Sign out everywhere / Delete my account).
const PREFIX = "ll.blog.draft.";
const owner = (): string | null => (account.status?.signed_in ? ((account.me as { id?: string } | null)?.id ?? null) : null);
const KEY = (id: string) => `${PREFIX}${owner()}.${id}`;
export interface LocalCopy extends Draft {
  revision: number;
  at: number;
}
export function keepLocal(id: string, d: Draft, revision: number): void {
  if (!owner()) return; // never for a signed-out visitor
  try {
    localStorage.setItem(KEY(id), JSON.stringify({ ...d, revision, at: Date.now() } satisfies LocalCopy));
  } catch {
    /* private mode, full storage: the server's copy is the one */
  }
}
export function readLocal(id: string): LocalCopy | null {
  if (!owner()) return null;
  try {
    const raw = localStorage.getItem(KEY(id));
    if (!raw) return null;
    const v = JSON.parse(raw) as LocalCopy;
    return typeof v?.body === "string" && typeof v?.title === "string" ? v : null;
  } catch {
    return null;
  }
}
export function dropLocal(id: string): void {
  if (!owner()) return;
  try {
    localStorage.removeItem(KEY(id));
  } catch {
    /* nothing kept */
  }
}
/** Every unsent draft on this device, whoever's: signing out leaves none behind. */
export function forgetDrafts(): void {
  try {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k?.startsWith(PREFIX)) localStorage.removeItem(k);
    }
  } catch {
    /* no storage: nothing kept */
  }
  editor.on = false;
  editor.mine = null;
  asked = null;
}

// ---- small text helpers the editor and its tests share
export function slugFrom(title: string): string {
  return (
    title
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60)
      .replace(/-+$/, "") || "post"
  );
}
export function tagsFrom(text: string): string[] {
  const out: string[] = [];
  for (const t of text.split(",")) {
    const v = t.trim().toLowerCase().replace(/\s+/g, " ");
    if (v && !out.includes(v)) out.push(v);
  }
  return out;
}
export function bytesOf(s: string): number {
  return new TextEncoder().encode(s).length;
}
// ---- end IO-3
