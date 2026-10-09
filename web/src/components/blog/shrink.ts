// IU-6 (Wave I-U): a picture over the server's bound is made smaller in the editor's browser before it is sent, so
// the server's checks stay as they are (PNG / JPEG / WebP by the first bytes, 300 KB at most: blog_store.upload).
// A picture already under the bound is sent as it is (a crisp PNG chart stays a PNG, and the server still judges it).
// Over the bound: drawn on a canvas with its longest side at most 1600 px, written as WebP (JPEG where the browser
// cannot write WebP), the quality stepped down until it fits; then the size itself stepped down. Nothing fits → the
// words say so, and nothing is sent.

export const MAX_BYTES = 300 * 1024;
export const MAX_SIDE = 1600;
const QUALITIES = [0.85, 0.75, 0.65, 0.55, 0.45];
const SCALES = [1, 0.75, 0.5];

export const NOT_A_PICTURE = "A picture is a PNG, JPEG or WebP file.";
export const TOO_BIG = "That picture could not be made small enough. Try a smaller one.";

/** The size to draw at: the longest side at most `maxSide`, never larger than the picture itself. */
export function fitSize(w: number, h: number, maxSide = MAX_SIDE): { w: number; h: number } {
  if (!(w > 0) || !(h > 0)) return { w: 0, h: 0 };
  const k = Math.min(1, maxSide / Math.max(w, h));
  return { w: Math.max(1, Math.round(w * k)), h: Math.max(1, Math.round(h * k)) };
}

function toBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), type, quality));
}

/** The picture to upload: the file itself when it is under the bound, else a smaller WebP / JPEG. Throws an Error
 * whose message is the editor's words when the file cannot be read as a picture or cannot be made small enough. */
export async function shrinkPicture(file: Blob, maxBytes = MAX_BYTES, maxSide = MAX_SIDE): Promise<Blob> {
  if (file.size <= maxBytes) return file;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new Error(NOT_A_PICTURE);
  }
  try {
    const first = fitSize(bitmap.width, bitmap.height, maxSide);
    if (!first.w) throw new Error(NOT_A_PICTURE);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error(TOO_BIG);
    let type = "image/webp";
    for (const s of SCALES) {
      canvas.width = Math.max(1, Math.round(first.w * s));
      canvas.height = Math.max(1, Math.round(first.h * s));
      ctx.fillStyle = "#ffffff"; // a transparent PNG becomes a picture on white, not on black, once it is a JPEG
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      for (const q of QUALITIES) {
        let b = await toBlob(canvas, type, q);
        if (b && b.type !== type) {
          type = "image/jpeg"; // this browser writes no WebP (it handed back a PNG): JPEG from here on
          b = await toBlob(canvas, type, q);
        }
        if (b && b.size <= maxBytes && b.size > 0) return b;
      }
    }
    throw new Error(TOO_BIG);
  } finally {
    bitmap.close();
  }
}
