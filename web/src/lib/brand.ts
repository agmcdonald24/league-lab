// The product's name and mark, in one place (renamed from League Lab to isuckatfantasy on 2026-10-04 — Andrew:
// "rename the app effective immediately"). The codebase, the package (`league_lab`), the environment variables
// (`LEAGUE_LAB_*`), the repository and the research console keep the old name; only what a manager sees changed.
export const APP_NAME = "isuckatfantasy";
export const APP_MARK = "isaf"; // the chip in the top bar and on the sign-in screen, and the home-screen icon
// ---- INF-1 (Wave I-I): Google Analytics 4 — the property's web stream "isuckatfantasy web" (https://isuckatfantasy.io).
// src/lib/analytics.ts loads it; LEAGUE_LAB_GA (build time) switches it off; unset, it sends only from these hosts.
export const GA_MEASUREMENT_ID = "G-HJWGHZ79BG";
export const GA_HOSTS = ["isuckatfantasy.io", "www.isuckatfantasy.io"];
// ---- end INF-1
