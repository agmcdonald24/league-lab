import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import ts from "typescript-eslint";

export default ts.config(
  { ignores: ["dist/", "node_modules/", "test-results/", "playwright-report/", "public/sw.js"] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs.recommended,
  { languageOptions: { globals: { ...globals.browser, ...globals.node } } },
  { files: ["**/*.svelte", "**/*.svelte.ts"], languageOptions: { parserOptions: { parser: ts.parser } } },
  { rules: { "svelte/no-at-html-tags": "off" } },   // markdown from the API is escaped before {@html} (src/lib/md.ts)
);
