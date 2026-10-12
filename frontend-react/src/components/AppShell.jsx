import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "./LanguageSwitcher";
import { useAuth } from "../contexts/AuthContext";
import { fetchUnreadSummary, logout } from "../api";
import NotificationCenter from "./NotificationCenter";
import CloseIcon from "./CloseIcon";
import useFocusTrap from "../hooks/useFocusTrap";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;
const EMPTY_SUMMARY = { notifications_unread: 0, messages_unread: 0 };

export default function AppShell({ children }) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unread, setUnread] = useState(EMPTY_SUMMARY);
  const drawerRef = useRef(null);
  const drawerCloseRef = useRef(null);

  const { session, refreshSession } = useAuth();
  const authenticated = Boolean(session?.authenticated);

  const loadUnread = useCallback(async () => {
    try {
      const data = await fetchUnreadSummary();
      setUnread({ ...EMPTY_SUMMARY, ...data });
    } catch {
      // The next poll recovers the counters from the server.
    }
  }, []);

  useEffect(() => {
    if (!authenticated) {
      setUnread(EMPTY_SUMMARY);
      return undefined;
    }
    loadUnread();
    const interval = setInterval(loadUnread, 60000);
    return () => clearInterval(interval);
  }, [authenticated, loadUnread]);

  useEffect(() => {
    if (authenticated) loadUnread();
  }, [authenticated, loadUnread, location.pathname]);

  const handleLogout = async () => {
    await logout();
    await refreshSession();
    navigate("/");
  };

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!menuOpen || typeof document === "undefined") {
      return undefined;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [menuOpen]);

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return;
    if (menuOpen) drawer.removeAttribute("inert");
    else drawer.setAttribute("inert", "");
  }, [menuOpen]);

  useFocusTrap(menuOpen, drawerRef, { initialFocusRef: drawerCloseRef, onEscape: () => setMenuOpen(false) });

  const messagesUnread = unread.messages_unread || 0;
  const investigationsActive = location.pathname.startsWith("/investigations");
  const patientInvestigations = Boolean(session?.patient?.id);
  const investigationsLabel = t(patientInvestigations ? "cscw.myInvestigations" : "cscw.investigations");

  const renderNavigation = (linkClass) => {
    if (!authenticated) return null;
    return (
      <>
        <NavLink
          to="/dashboard"
          end
          className={({ isActive }) => `${linkClass}${isActive && !location.hash ? " is-active" : ""}`}
        >
          {t("appShell.nav.overview")}
        </NavLink>
        {session?.patient?.id ? (
          <NavLink to={`/patients/${session.patient.id}`} className={({ isActive }) => `${linkClass}${isActive ? " is-active" : ""}`}>
            {t("appShell.nav.myPanel")}
          </NavLink>
        ) : null}
        <Link
          to="/dashboard#investigations"
          className={`${linkClass}${investigationsActive || location.hash === "#investigations" ? " is-active" : ""}`}
          aria-label={t("cscw.menuAria", { label: investigationsLabel, count: messagesUnread })}
          aria-current={investigationsActive || location.hash === "#investigations" ? "page" : undefined}
        >
          <span>{investigationsLabel}</span>
          {messagesUnread > 0 ? (
            <span className="react-badge react-badge--count" aria-hidden="true">
              {messagesUnread}
            </span>
          ) : null}
        </Link>
      </>
    );
  };

  return (
    <div className="react-shell">
      <div className="react-shell__backdrop" aria-hidden="true" />
      <button
        type="button"
        className={`react-drawer__overlay${menuOpen ? " is-open" : ""}`}
        aria-label={t("appShell.closeMenu")}
        aria-hidden="true"
        tabIndex={-1}
        onClick={() => setMenuOpen(false)}
      />
      <aside
        ref={drawerRef}
        className={`react-drawer${menuOpen ? " is-open" : ""}`}
        aria-hidden={!menuOpen}
        aria-label={t("appShell.menu")}
      >
        <div className="react-drawer__header">
          <strong>{t("appShell.menu")}</strong>
          <button
            type="button"
            className="react-drawer__close"
            onClick={() => setMenuOpen(false)}
            aria-label={t("appShell.closeMenu")}
            ref={drawerCloseRef}
          >
            <CloseIcon />
          </button>
        </div>
        <nav className="react-drawer__nav" aria-label={t("appShell.mobileNavLabel")}>
          {renderNavigation("react-drawer__link")}
        </nav>
        <div className="react-drawer__actions">
          {authenticated ? (
            <button type="button" className="react-drawer__link react-drawer__link--button" onClick={handleLogout}>
              {t("auth.logout")}
            </button>
          ) : null}
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
          <div className="react-topbar__content">
            <nav className="react-nav" aria-label={t("appShell.navLabel")}>
              {renderNavigation("react-nav__link")}
            </nav>
          </div>
          <div className="react-topbar__actions">
            {authenticated ? <NotificationCenter unreadCount={unread.notifications_unread || 0} onChange={loadUnread} /> : null}
            <div className="react-topbar__desktop-actions">
              <LanguageSwitcher />
              {authenticated ? (
                <button type="button" className="react-nav__link react-nav__link--button" onClick={handleLogout}>
                  {t("auth.logout")}
                </button>
              ) : null}
            </div>
            <button
              type="button"
              className="react-topbar__menu-button"
              aria-expanded={menuOpen}
              aria-label={t("appShell.openMenu")}
              onClick={() => setMenuOpen(true)}
            >
              <span />
              <span />
              <span />
            </button>
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
