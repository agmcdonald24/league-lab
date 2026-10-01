import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The API (api/, port 8581) serves the built files in production; in dev, vite proxies /api to it.
const api = process.env.LEAGUE_LAB_API ?? "http://localhost:8581";

export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  server: { port: 8582, proxy: { "/api": { target: api, changeOrigin: true } } },
  preview: { port: 8582, proxy: { "/api": { target: api, changeOrigin: true } } },
  build: { target: "es2022", sourcemap: false, assetsInlineLimit: 0 },
});
