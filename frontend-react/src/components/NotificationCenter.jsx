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
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  const [retryMore, setRetryMore] = useState(0);
  const wrapperRef = useRef(null);
  const panelRef = useRef(null);
  const triggerRef = useRef(null);
  const titleRef = useRef(null);
  const sentinelRef = useRef(null);
  const loadingPageRef = useRef(false);

  useEffect(() => {
    if (!open) return undefined;

    let cancelled = false;
    loadingPageRef.current = true;
    setLoadMoreError(false);
    if (page === 1) setStatus("loading");
    else setLoadingMore(true);

    fetchNotifications({ unread_only: true, page, page_size: 10 })
      .then((data) => {
        if (cancelled) return;
        const rows = data.notifications || data || [];
        setNotifications((current) => {
          if (page === 1) return rows;
          const currentIds = new Set(current.map((item) => item.id));
          return [...current, ...rows.filter((item) => !currentIds.has(item.id))];
        });
        setHasMore(Boolean(data.pagination && data.pagination.page < data.pagination.pages));
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        if (page === 1) setStatus("error");
        else setLoadMoreError(true);
      })
      .finally(() => {
        if (cancelled) return;
        loadingPageRef.current = false;
        setLoadingMore(false);
      });

    return () => {
      cancelled = true;
      loadingPageRef.current = false;
    };
  }, [open, page, retryMore]);

  useEffect(() => {
    if (!open || !hasMore || loadMoreError) return undefined;
    const sentinel = sentinelRef.current;
    const panel = panelRef.current;
    if (!sentinel || !panel || typeof IntersectionObserver === "undefined") return undefined;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !loadingPageRef.current) {
        loadingPageRef.current = true;
        setPage((current) => current + 1);
      }
    }, { root: panel, rootMargin: "80px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [open, hasMore, loadMoreError, notifications.length]);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    titleRef.current?.focus();
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
      setNotifications((current) => current.filter((item) => item.id !== id));
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
        ref={triggerRef}
        className={`react-notifications__trigger${open ? " is-open" : ""}`}
        onClick={() => {
          if (!open) {
            setPage(1);
            setNotifications([]);
            setHasMore(false);
            setLoadMoreError(false);
          }
          setOpen((current) => !current);
        }}
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
        <div ref={panelRef} className="react-notifications__panel" role="region" aria-labelledby="notifications-title">
          <div className="react-notifications__header">
            <div>
              <h3 id="notifications-title" ref={titleRef} tabIndex={-1}>{t("notifications.title")}</h3>
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
                  <button type="button" className="react-notifications__open" onClick={() => handleOpen(n)}>
                    <span className="react-notifications__copy">
                    <span className="react-notifications__label">{t(`notifications.types.${n.notification_type}${session?.patient?.id && n.notification_type.startsWith("investigation_") ? "_patient" : ""}`, { defaultValue: n.notification_type })}</span>
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
          {status === "ready" && hasMore ? (
            <div ref={sentinelRef} className="react-notifications__feed-end" aria-live="polite">
              {loadingMore ? t("notifications.loadingMore") : null}
              {loadMoreError ? (
                <button type="button" className="react-button react-button--text" onClick={() => {
                  setLoadMoreError(false);
                  setRetryMore((current) => current + 1);
                }}>
                  {t("notifications.retryMore")}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
