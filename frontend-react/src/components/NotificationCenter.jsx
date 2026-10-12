import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { fetchNotifications, readNotification } from "../api";
import { useAuth } from "../contexts/AuthContext";
import StateBlock from "./StateBlock";

function formatWhen(value, locale) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(parsed);
}

function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.6 2H4.4l1.6-2Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinejoin="round"
      />
      <path d="M10 20.5a2.1 2.1 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export default function NotificationCenter({ unreadCount = 0, onChange }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { session } = useAuth();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("idle");
  const [notifications, setNotifications] = useState([]);
  const wrapperRef = useRef(null);

  const loadNotifications = async () => {
    setStatus((current) => (current === "ready" ? current : "loading"));
    try {
      const data = await fetchNotifications({ unread_only: true });
      setNotifications(data.notifications || data || []);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  };

  useEffect(() => {
    if (open) {
      setStatus("loading");
      loadNotifications();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const handleRead = async (id) => {
    try {
      await readNotification(id);
      await loadNotifications();
      onChange?.();
    } catch {
      setStatus("error");
    }
  };

  const handleOpen = async (notification) => {
    try {
      await readNotification(notification.id);
      onChange?.();
    } catch {
      // Opening the destination should still work if marking read fails.
    }
    setOpen(false);
    const payload = notification.payload || {};
    if (payload.investigation_id) {
      navigate(`/investigations/${payload.investigation_id}`);
    } else if (notification.notification_type === "atypical_day_prompt") {
      const indicatorId = payload.indicator_ids?.[0] || payload.indicator_id;
      navigate(indicatorId ? `/dashboard#atypical-day-${indicatorId}` : "/dashboard#atypical-days-prompts");
    } else if (payload.link_id) {
      navigate(`/dashboard#${session?.doctor?.id && !session?.patient?.id ? "pending-link" : "doctor-link"}-${payload.link_id}`);
    } else {
      navigate(session?.doctor?.id && !session?.patient?.id ? "/dashboard#pending-links" : "/dashboard#atypical-days-prompts");
    }
  };

  return (
    <div ref={wrapperRef} className="react-notifications">
      <button
        type="button"
        className={`react-notifications__trigger${open ? " is-open" : ""}`}
        onClick={() => setOpen((current) => !current)}
        aria-label={t("notifications.title")}
        aria-expanded={open}
      >
        <BellIcon />
        {unreadCount > 0 ? (
          <span className="react-badge react-badge--count react-notifications__count" aria-hidden="true">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="react-notifications__panel" role="region" aria-labelledby="notifications-title">
          <div className="react-notifications__header">
            <div>
              <p className="react-eyebrow">{t("notifications.eyebrow")}</p>
              <h3 id="notifications-title">{t("notifications.title")}</h3>
            </div>
            {unreadCount > 0 ? (
              <span className="react-badge react-badge--blue react-badge--compact">{t("notifications.unread", { count: unreadCount })}</span>
            ) : null}
          </div>
          {status === "loading" ? (
            <div role="status">
              <StateBlock title={t("notifications.loading")} tone="info" />
            </div>
          ) : status === "error" ? (
            <div role="alert">
              <StateBlock title={t("notifications.error")} tone="danger" />
            </div>
          ) : notifications.length === 0 ? (
            <StateBlock title={t("notifications.emptyTitle")} description={t("notifications.emptyDescription")} />
          ) : (
            <ul className="react-notifications__list">
              {notifications.map((n) => (
                <li key={n.id} className="react-notifications__item">
                  <span className="react-notifications__dot" aria-hidden="true" />
                  <button type="button" className="react-notifications__open" onClick={() => handleOpen(n)} aria-label={t("notifications.openItem")}>
                    <span className="react-notifications__copy">
                    <p>{t(`notifications.types.${n.notification_type}${session?.patient?.id && n.notification_type.startsWith("investigation_") ? "_patient" : ""}`, { defaultValue: n.notification_type })}</p>
                    {n.created_at ? <small>{formatWhen(n.created_at, i18n.language)}</small> : null}
                    </span>
                  </button>
                  <button type="button" className="react-button react-button--ghost react-button--compact" onClick={() => handleRead(n.id)}>
                    {t("notifications.markRead")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
