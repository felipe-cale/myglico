import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import InvestigationOrigin from "../components/InvestigationOrigin";
import { fetchInvestigationDetail, sendInvestigationMessage, closeInvestigation, readInvestigation } from "../api";

function formatDateTime(value, locale) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(parsed);
}

export default function InvestigationPage() {
  const { id } = useParams();
  const { t, i18n } = useTranslation();
  const [inv, setInv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMsg, setNewMsg] = useState("");
  const [loadError, setLoadError] = useState(false);
  const [actionError, setActionError] = useState("");
  const [closing, setClosing] = useState(false);
  const [observation, setObservation] = useState("");
  const [newMessageIds, setNewMessageIds] = useState(() => new Set());
  const lastReadSequence = useRef(0);
  const seenMessageIds = useRef(null);

  const loadData = async () => {
    try {
      const data = await fetchInvestigationDetail(id);
      const investigation = data.investigation || data;
      const items = data.messages || data.items || [];
      const ownRole = investigation.counterpart?.role === "doctor" ? "patient" : "doctor";
      if (seenMessageIds.current === null) {
        const fromCounterpart = items.filter((m) => m.author_role !== ownRole);
        const unread = data.unread_count || 0;
        const fresh = unread > 0 ? fromCounterpart.slice(-unread) : [];
        setNewMessageIds(new Set(fresh.map((m) => m.id)));
        seenMessageIds.current = new Set(items.map((m) => m.id));
      } else {
        const incoming = items.filter((m) => !seenMessageIds.current.has(m.id) && m.author_role !== ownRole);
        if (incoming.length) {
          setNewMessageIds((current) => new Set([...current, ...incoming.map((m) => m.id)]));
        }
        items.forEach((m) => seenMessageIds.current.add(m.id));
      }
      setInv(investigation);
      setMessages(items);
      setLoadError(false);
    } catch(e) {
      setLoadError(true);
    }
  };

  useEffect(() => {
    seenMessageIds.current = null;
    lastReadSequence.current = 0;
    setInv(null);
    loadData();
    const interval = setInterval(loadData, 10000); // Polling for messages
    return () => clearInterval(interval);
  }, [id]);

  useEffect(() => {
    const sequence = messages.at(-1)?.sequence || 0;
    if (!sequence || sequence <= lastReadSequence.current) return undefined;
    const frame = requestAnimationFrame(async () => {
      try {
        await readInvestigation(id, sequence);
        lastReadSequence.current = sequence;
      } catch (error) {
        // A later refresh retries after the messages are available again.
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [id, messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!newMsg.trim()) return;
    try {
      await sendInvestigationMessage(id, { content: newMsg });
      setNewMsg("");
      setActionError("");
      loadData();
    } catch(e) {
      setActionError(t("cscw.sendFailed"));
    }
  };

  const handleClose = async (e) => {
    e.preventDefault();
    try {
      const payload = { version: inv?.version };
      if (observation.trim()) payload.observation = observation.trim();
      await closeInvestigation(id, payload);
      setClosing(false);
      setObservation("");
      setActionError("");
      loadData();
    } catch(e) {
      setActionError(t("cscw.closeFailed"));
    }
  };

  if (!inv) {
    return loadError
      ? <div className="react-page" role="alert">{t("cscw.loadFailed")}</div>
      : <div className="react-page" role="status">{t("cscw.loading")}</div>;
  }

  const roleLabel = (role) => (role ? t(`cscw.roles.${role}`, { defaultValue: role }) : t("cscw.nobody"));
  const counterpartName = inv.counterpart?.name || inv.counterpart?.display_name || inv.counterpart?.short_id;

  return (
    <div className="react-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>{inv.title}</h2>
        <Link to="/dashboard#investigations">{t("common.back")}</Link>
      </div>
      {counterpartName && (
        <p>{t(inv.counterpart?.role === "doctor" ? "cscw.counterpartDoctor" : "cscw.counterpartPatient")}: {counterpartName}</p>
      )}
      <p>{t("cscw.statusLabel")}: {t(`cscw.status.${inv.status}`, { defaultValue: inv.status })} | {t("cscw.awaiting")}: {roleLabel(inv.awaiting_role)}</p>
      <InvestigationOrigin investigation={inv} />
      {inv.status === "closed" && (
        <p className="react-investigation-closed" role="status">
          {t(`cscw.closedReason.${inv.closed_reason}`, { defaultValue: t("cscw.closedReason.default") })}
          {inv.closed_at ? ` · ${formatDateTime(inv.closed_at, i18n.language)}` : ""}
        </p>
      )}

      <ol className="react-message-list" aria-label={t("cscw.messagesLabel")}>
        {messages.map((m) => {
          const isNew = newMessageIds.has(m.id);
          return (
            <li key={m.id} className={`react-message${isNew ? " is-new" : ""}`}>
              <div className="react-message__meta">
                <strong>{roleLabel(m.author_role)}</strong>
                <small>{formatDateTime(m.created_at, i18n.language)}</small>
                {isNew && <span className="react-unread-badge">{t("cscw.newMessage")}</span>}
              </div>
              <p>{m.content}</p>
            </li>
          );
        })}
      </ol>

      {actionError && <p role="alert">{actionError}</p>}

      {inv.status === 'open' && !closing && (
        <form onSubmit={handleSend} style={{ display: 'flex', gap: '10px', marginTop: '1rem' }}>
          <input type="text" value={newMsg} onChange={e => setNewMsg(e.target.value)} style={{ flex: 1, padding: '10px' }} aria-label={t("cscw.message")} />
          <button type="submit" className="react-button" style={{ background: '#005fcc', color: '#fff', border: 'none' }}>{t("cscw.send")}</button>
          <button type="button" onClick={() => setClosing(true)} className="react-button">{t("cscw.close")}</button>
        </form>
      )}

      {inv.status === 'open' && closing && (
        <form onSubmit={handleClose} style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '1rem' }}>
          <label className="react-select-field">
            <span>{t("cscw.closingObservation")}</span>
            <textarea value={observation} onChange={e => setObservation(e.target.value)} rows={3} maxLength={2000} />
          </label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button type="submit" className="react-button">{t("cscw.confirmClose")}</button>
            <button type="button" className="react-button react-button--ghost" onClick={() => setClosing(false)}>{t("dashboard.cancel")}</button>
          </div>
        </form>
      )}
    </div>
  );
}
