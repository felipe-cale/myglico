// Reads the app's own locale files so UI assertions use the real translated
// strings instead of hard-coded copies that drift (REVISAO-FINAL.md, A16).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const localesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "src", "locales");
const cache = new Map();

function load(lang) {
  if (!cache.has(lang)) {
    cache.set(lang, JSON.parse(fs.readFileSync(path.join(localesDir, `${lang}.json`), "utf-8")));
  }
  return cache.get(lang);
}

export const LANGS = ["pt-BR", "en-US", "es"];

export function t(key, lang = "pt-BR", vars = {}) {
  const value = key.split(".").reduce((node, part) => (node == null ? undefined : node[part]), load(lang));
  if (typeof value !== "string") throw new Error(`Missing translation ${lang}:${key}`);
  return value.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, name) => String(vars[name] ?? ""));
}

export function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Exact (anchored, whitespace-tolerant) regex for an accessible name.
export function tx(key, lang = "pt-BR", vars = {}) {
  return new RegExp(`^\\s*${escapeRegex(t(key, lang, vars))}\\s*$`, "i");
}
