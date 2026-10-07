// IP-4: one import() promise for the card's panels (panels.ts), shared by the player page and the drawer.
let loaded: Promise<typeof import("./panels")> | null = null;
export const panels = () => (loaded ??= import("./panels"));
