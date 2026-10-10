import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fetchUnreadSummary, fetchNotifications, readNotification } from "../api";
import { Link } from "react-router-dom";

export default function NotificationCenter() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState({ notifications_unread: 0, messages_unread: 0 });
  const [notifications, setNotifications] = useState([]);
  const wrapperRef = useRef(null);

  const loadSummary = async () => {
    try {
      const data = await fetchUnreadSummary();
      setSummary(data);
    } catch(e) {}
  };

  const loadNotifications = async () => {
    try {
      const data = await fetchNotifications({ unread_only: true });
      setNotifications(data.notifications || data || []);
    } catch(e) {}
  };

  useEffect(() => {
    loadSummary();
    const interval = setInterval(loadSummary, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (open) {
      loadNotifications();
    }
  }, [open]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [wrapperRef]);

  const handleRead = async (id) => {
    try {
      await readNotification(id);
      loadNotifications();
      loadSummary();
    } catch(e) {}
  };

  return (
    <div ref={wrapperRef} style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: '1rem' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', position: 'relative' }}
        aria-label={t("notifications.title")}
      >
        <span style={{ fontSize: '1.2rem' }}>🔔</span>
        {summary.notifications_unread > 0 && (
          <span style={{ position: 'absolute', top: '-5px', right: '-10px', background: 'red', color: 'white', borderRadius: '50%', padding: '2px 6px', fontSize: '0.7rem' }}>
            {summary.notifications_unread}
          </span>
        )}
      </button>

      <Link
        to="/dashboard#investigations"
        className="react-investigations-menu"
        aria-label={t("cscw.menuAria", { count: summary.messages_unread || 0 })}
      >
        {t("cscw.investigations")}
        {summary.messages_unread > 0 && <span className="react-unread-badge">{summary.messages_unread}</span>}
      </Link>

      {open && (
        <div style={{ position: 'absolute', top: '100%', right: '0', background: 'white', border: '1px solid #ccc', borderRadius: '4px', width: '300px', maxHeight: '400px', overflowY: 'auto', zIndex: 100, boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}>
          <div style={{ padding: '10px', borderBottom: '1px solid #eee', fontWeight: 'bold' }}>
            {t("notifications.title")}
          </div>
          {notifications.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>{t("notifications.empty")}</div>
          ) : (
            notifications.map(n => (
              <div key={n.id} style={{ padding: '10px', borderBottom: '1px solid #eee', fontSize: '0.9rem' }}>
                <p style={{ margin: '0 0 5px 0' }}>
                  {t(`notifications.types.${n.notification_type}`, { defaultValue: n.notification_type })}
                </p>
                <button onClick={() => handleRead(n.id)} style={{ fontSize: '0.8rem', background: '#eee', border: 'none', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer' }}>
                  {t("notifications.markRead")}
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
