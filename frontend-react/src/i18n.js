import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ptBR from "./locales/pt-BR.json";
import enUS from "./locales/en-US.json";
import es from "./locales/es.json";

export const SUPPORTED_LANGUAGES = [
  { code: "pt-BR", label: "Português", flag: "pt-br" },
  { code: "en-US", label: "English", flag: "en" },
  { code: "es", label: "Español", flag: "es" }
];

const STORAGE_KEY = "myglico.language";

// Storage can be unavailable (private mode, blocked site data); the language then just isn't remembered.
function readStoredLanguage() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeLanguage(lang) {
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // Not persisted; the next visit falls back to the browser language.
  }
}

function resolveInitialLanguage() {
  if (typeof window === "undefined") {
    return "pt-BR";
  }
  const stored = readStoredLanguage();
  if (stored && SUPPORTED_LANGUAGES.some((lang) => lang.code === stored)) {
    return stored;
  }
  const browserLang = window.navigator.language || "";
  const matched = SUPPORTED_LANGUAGES.find((lang) => lang.code === browserLang || lang.code.split("-")[0] === browserLang.split("-")[0]);
  return matched ? matched.code : "pt-BR";
}

i18n.use(initReactI18next).init({
  resources: {
    "pt-BR": { translation: ptBR },
    "en-US": { translation: enUS },
    es: { translation: es }
  },
  lng: resolveInitialLanguage(),
  fallbackLng: "pt-BR",
  interpolation: {
    escapeValue: false
  }
});

i18n.on("languageChanged", (lang) => {
  if (typeof window !== "undefined") {
    storeLanguage(lang);
    document.documentElement.lang = lang;
  }
});

if (typeof document !== "undefined") {
  document.documentElement.lang = i18n.language;
}

export default i18n;
