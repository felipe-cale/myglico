import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES } from "../i18n";

const flagUrl = (flag) => new URL(`../assets/flags/${flag}.svg`, import.meta.url).href;

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const current = SUPPORTED_LANGUAGES.find((lang) => lang.code === i18n.language) || SUPPORTED_LANGUAGES[0];

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handlePointerDown = (event) => {
      if (!containerRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  function handleSelect(code) {
    i18n.changeLanguage(code);
    setOpen(false);
  }

  return (
    <div className="react-language-switcher" ref={containerRef}>
      <button
        type="button"
        className="react-language-switcher__trigger"
        aria-label={t("languageSwitcher.label")}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <img src={flagUrl(current.flag)} alt="" width="20" height="20" />
        <span className="react-language-switcher__code">{current.code.split("-")[0].toUpperCase()}</span>
      </button>
      {open ? (
        <div className="react-language-switcher__menu" role="menu">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              role="menuitemradio"
              aria-checked={lang.code === current.code}
              className={`react-language-switcher__item${lang.code === current.code ? " is-active" : ""}`}
              onClick={() => handleSelect(lang.code)}
            >
              <img src={flagUrl(lang.flag)} alt="" width="20" height="20" />
              <span>{lang.label}</span>
              <small>{lang.code.toUpperCase()}</small>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
