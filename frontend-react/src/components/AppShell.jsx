import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "./LanguageSwitcher";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

export default function AppShell({ children }) {
  const { t } = useTranslation();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const navigation = [{ to: "/", label: t("appShell.nav.overview") }];

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!menuOpen || typeof document === "undefined") {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    window.addEventListener("keydown", handleEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

  return (
    <div className="react-shell">
      <div className="react-shell__backdrop" aria-hidden="true" />
      <button
        type="button"
        className={`react-drawer__overlay${menuOpen ? " is-open" : ""}`}
        aria-label={t("appShell.closeMenu")}
        aria-hidden={!menuOpen}
        tabIndex={menuOpen ? 0 : -1}
        onClick={() => setMenuOpen(false)}
      />
      <aside className={`react-drawer${menuOpen ? " is-open" : ""}`} aria-hidden={!menuOpen}>
        <div className="react-drawer__header">
          <strong>{t("appShell.menu")}</strong>
          <button
            type="button"
            className="react-drawer__close"
            aria-label={t("appShell.closeMenu")}
            onClick={() => setMenuOpen(false)}
          >
            ×
          </button>
        </div>
        <nav className="react-drawer__nav" aria-label={t("appShell.mobileNavLabel")}>
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `react-drawer__link${isActive ? " is-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="react-drawer__actions">
          <LanguageSwitcher />
        </div>
      </aside>
      <div className="react-shell__container">
        <header className="react-topbar">
          <Link className="react-brand" to="/">
            <span className="react-brand__mark">
              <img src={assetUrl("img/myglico-mark.svg")} alt="" />
            </span>
            <span>
              <strong>MyGlico</strong>
              <small>{t("appShell.brandTagline")}</small>
            </span>
          </Link>
          <button
            type="button"
            className="react-topbar__menu-button"
            aria-label={t("appShell.openMenu")}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(true)}
          >
            <span />
            <span />
            <span />
          </button>
          <div className="react-topbar__content">
            <nav className="react-nav" aria-label={t("appShell.navLabel")}>
              {navigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => `react-nav__link${isActive ? " is-active" : ""}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="react-topbar__actions">
              <LanguageSwitcher />
            </div>
          </div>
        </header>
        <main className="react-main">{children}</main>
        <footer className="react-footer">
          <div>
            <strong>MyGlico</strong>
            <p>{t("appShell.footerText")}</p>
          </div>
        </footer>
      </div>
    </div>
  );
}
