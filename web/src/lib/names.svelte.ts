// League names learned from the API's answers (My Week, the player card), so a league opened from a shared link that
// is in neither list (the user's, the house leagues) is shown by its name in the league select, not "This league".
export const leagueNames = $state<Record<string, string>>({});

export function learnLeagueName(id: string | null | undefined, name: string | null | undefined): void {
  if (id && name && leagueNames[id] !== name) leagueNames[id] = name;
}

// ---- IA-1: short names on a phone ("J. Jefferson"). The lineup's names squished on a 375 px screen (Andrew,
// 2026-10-02); the short form keeps the last name whole (suffixes too: "M. Penix Jr.", "A. St. Brown") and the
// first initial, grown one letter at a time only when two players of the same list would read the same.
const INITIALS = /^([A-Z]\.?){1,3}$/; // "DJ", "D.J.", "AJ", "T.J." — already short

/** "Justin Jefferson" → "J. Jefferson". `others`: the names shown with it (a lineup): when two would read the same
 * ("J. Williams" for Jameson and Javonte), the first name grows until they differ ("Jam. Williams" / "Jav. Williams"),
 * up to the whole name. Never shortened: a defense (`position` DEF), a one-word name, a first name that is already
 * initials ("D.J. Moore"). */
export function shortName(name: string | null | undefined, position?: string | null, others: readonly (string | null | undefined)[] = []): string {
  if (!name) return "";
  const parts = name.trim().split(/\s+/);
  if (position === "DEF" || parts.length < 2 || INITIALS.test(parts[0])) return name.trim();
  const first = parts[0];
  const rest = parts.slice(1).join(" ");
  const rivals = others
    .filter((o): o is string => !!o && o.trim() !== name.trim())
    .map((o) => o.trim().split(/\s+/))
    .filter((p) => p.length >= 2 && p.slice(1).join(" ") === rest)
    .map((p) => p[0].toLowerCase());
  for (let k = 1; k < first.length; k++) {
    const head = first.slice(0, k).toLowerCase();
    if (!rivals.some((r) => r.startsWith(head))) return `${first.slice(0, k)}. ${rest}`;
  }
  return name.trim();
}
// ---- end IA-1
