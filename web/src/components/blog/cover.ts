// IU-6 (Wave I-U): a post's cover picture — the API's `image` ("/blog/img/<name>" for a file post, "/blog/img/db/<id>"
// for a post written in the editor). Only those two shapes are ever put in a src; anything else is no picture.
const COVER = /^\/blog\/img\/([a-z0-9][a-z0-9_-]{0,79}\.(png|jpe?g|webp)|db\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/;

export function coverSrc(image: string | null | undefined): string | null {
  return typeof image === "string" && COVER.test(image) ? image : null;
}
