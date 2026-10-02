// League names learned from the API's answers (My Week, the player card), so a league opened from a shared link that
// is in neither list (the user's, the house leagues) is shown by its name in the league select, not "This league".
export const leagueNames = $state<Record<string, string>>({});

export function learnLeagueName(id: string | null | undefined, name: string | null | undefined): void {
  if (id && name && leagueNames[id] !== name) leagueNames[id] = name;
}
