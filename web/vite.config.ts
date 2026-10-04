import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The API (api/, port 8581) serves the built files in production; in dev, vite proxies /api to it.
const api = process.env.LEAGUE_LAB_API ?? "http://localhost:8581";
// ---- INF-1: Google Analytics' build-time switch (src/lib/analytics.ts): LEAGUE_LAB_GA=off → never loads (the code is
// dropped), on → always, unset → only on the production host. Only this one value reaches the bundle (`define`).
const ga = (process.env.LEAGUE_LAB_GA ?? "").trim().toLowerCase();

export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  define: { __LL_GA__: JSON.stringify(ga === "off" || ga === "on" ? ga : "auto") }, // ---- INF-1
  server: { port: 8582, proxy: { "/api": { target: api, changeOrigin: true } } },
  preview: { port: 8582, proxy: { "/api": { target: api, changeOrigin: true } } },
  build: { target: "es2022", sourcemap: false, assetsInlineLimit: 0 },
});
