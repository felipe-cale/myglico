import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import InvestigationOrigin from "../components/InvestigationOrigin";
import ConfirmDialog from "../components/ConfirmDialog";
import StateBlock from "../components/StateBlock";
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

  const handleClose = async () => {
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
    return loadError ? (
      <div className="react-page" role="alert">
        <StateBlock title={t("cscw.loadFailed")} tone="danger" />
      </div>
    ) : (
      <div className="react-page" role="status">
        <StateBlock title={t("cscw.loading")} tone="info" />
      </div>
    );
  }

  const roleLabel = (role) => (role ? t(`cscw.roles.${role}`, { defaultValue: role }) : t("cscw.nobody"));
  const isPatient = inv.counterpart?.role === "doctor";
  const counterpartName = inv.counterpart?.name || inv.counterpart?.display_name || inv.counterpart?.short_id;
  const ownRole = inv.counterpart?.role === "doctor" ? "patient" : "doctor";

  return (
    <div className="react-page react-conversation">
      <section className="react-panel react-conversation__header">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <p className="react-eyebrow">{t(isPatient ? "cscw.conversationEyebrowPatient" : "cscw.conversationEyebrowDoctor")}</p>
            <h2>{inv.title}</h2>
            {counterpartName && (
              <p>{t(inv.counterpart?.role === "doctor" ? "cscw.counterpartDoctor" : "cscw.counterpartPatient")}: <strong>{counterpartName}</strong></p>
            )}
          </div>
          <Link to="/dashboard#investigations" className="react-button react-button--ghost">{t("common.back")}</Link>
        </div>
        <div className="react-chip-row react-conversation__chips">
          <span className={`react-status-chip react-status-chip--${inv.status}`}>{t(`cscw.status.${inv.status}`, { defaultValue: inv.status })}</span>
          {inv.status === "open" ? (
            <span className="react-badge react-badge--soft react-badge--compact">{t("cscw.awaitingChip", { role: roleLabel(inv.awaiting_role) })}</span>
          ) : null}
          <InvestigationOrigin investigation={inv} variant="chip" />
        </div>
        {inv.status === "closed" && (
          <p className="react-investigation-closed" role="status">
            {t(`cscw.closedReason.${inv.closed_reason}`, { defaultValue: t("cscw.closedReason.default") })}
            {inv.closed_at ? ` · ${formatDateTime(inv.closed_at, i18n.language)}` : ""}
          </p>
        )}
      </section>

      <section className="react-panel react-conversation__body" aria-labelledby="conversation-messages-title">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <p className="react-eyebrow">{t("cscw.messagesEyebrow")}</p>
            <h2 id="conversation-messages-title">{t("cscw.messagesTitle")}</h2>
          </div>
        </div>
        <ol className="react-message-list" aria-label={t("cscw.messagesLabel")}>
          {messages.map((m) => {
            const isNew = newMessageIds.has(m.id);
            const isOwn = m.author_role === ownRole;
            return (
              <li key={m.id} className={`react-message${isOwn ? " is-own" : ""}${m.author_role === "system" ? " is-system" : ""}${isNew ? " is-new" : ""}`}>
                <div className="react-message__meta">
                  <strong>{isOwn ? t("cscw.you") : roleLabel(m.author_role)}</strong>
                  <small>{formatDateTime(m.created_at, i18n.language)}</small>
                  {isNew && <span className="react-badge react-badge--count">{t("cscw.newMessage")}</span>}
                </div>
                <p>{m.content}</p>
              </li>
            );
          })}
        </ol>

        {actionError && !closing && <p className="react-form-message is-error" role="alert">{actionError}</p>}

        {inv.status === "open" && (
          <form onSubmit={handleSend} className="react-composer">
            <label className="react-field react-composer__field">
              <span>{t("cscw.message")}</span>
              <textarea
                value={newMsg}
                onChange={e => setNewMsg(e.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                rows={3}
                placeholder={t("cscw.messagePlaceholder")}
              />
            </label>
            <div className="react-composer__actions">
              <small>{t("cscw.composerHint")}</small>
              <button type="button" onClick={() => { setActionError(""); setClosing(true); }} className="react-button react-button--danger">{t("cscw.close")}</button>
              <button type="submit" className="react-button">{t("cscw.send")}</button>
            </div>
          </form>
        )}
      </section>

      <ConfirmDialog
        open={inv.status === "open" && closing}
        eyebrow={t(isPatient ? "cscw.conversationEyebrowPatient" : "cscw.conversationEyebrowDoctor")}
        title={t("cscw.closeDialogTitle")}
        description={t("cscw.closeDialogBody")}
        confirmLabel={t("cscw.confirmClose")}
        cancelLabel={t("cscw.keepOpen")}
        error={actionError}
        onConfirm={handleClose}
        onCancel={() => setClosing(false)}
      >
        <label className="react-field">
          <span>{t("cscw.closingObservation")}</span>
          <textarea value={observation} onChange={e => setObservation(e.target.value)} rows={3} maxLength={2000} />
        </label>
      </ConfirmDialog>
    </div>
  );
}
