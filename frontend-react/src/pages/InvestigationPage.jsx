import { Fragment, useState, useEffect, useLayoutEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import InvestigationOrigin from "../components/InvestigationOrigin";
import ConfirmDialog from "../components/ConfirmDialog";
import StateBlock from "../components/StateBlock";
import Pagination from "../components/Pagination";
import { ArrowLeftIcon } from "../components/Icons";
import usePrefersReducedMotion from "../hooks/usePrefersReducedMotion";
import useVisibleInterval from "../hooks/useVisibleInterval";
import useDocumentTitle from "../hooks/useDocumentTitle";
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
  const reducedMotion = usePrefersReducedMotion();
  const [inv, setInv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, pages: 1 });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [newMsg, setNewMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [actionError, setActionError] = useState("");
  const [closing, setClosing] = useState(false);
  const [observation, setObservation] = useState("");
  const [newMessageIds, setNewMessageIds] = useState(() => new Set());
  const messageListRef = useRef(null);
  const lastReadSequence = useRef(0);
  const seenMessageIds = useRef(null);
  const followLatestRef = useRef(true);
  const scrollAfterSendRef = useRef(false);
  // Frozen on the first load: where the unread messages started and how many there were.
  const [unreadMarker, setUnreadMarker] = useState(null);
  // "landing" puts the list on the first unread message (or the end); "page" does the same after paging.
  const pendingScrollRef = useRef("landing");
  const redirectingRef = useRef(false);
  const backgroundNextLoadRef = useRef(false);
  const dividerRef = useRef(null);

  const loadData = async ({ background = false } = {}) => {
    try {
      const requestedPage = Number.isInteger(page) && page > 0 ? page : 1;
      const data = await fetchInvestigationDetail(id, { page: requestedPage, page_size: pageSize }, { background });
      const investigation = data.investigation || data;
      const items = data.messages || data.items || [];
      const ownRole = investigation.counterpart?.role === "doctor" ? "patient" : "doctor";
      let firstUnreadPage = null;
      if (seenMessageIds.current === null) {
        const fromCounterpart = items.filter((m) => m.author_role !== ownRole);
        const unread = data.unread_count || 0;
        // Sequences are contiguous per conversation, so the server marker is total - unread.
        const total = data.pagination?.total ?? items.length;
        lastReadSequence.current = Math.max(0, total - unread);
        if (unread > 0 && data.pagination?.page_size) {
          followLatestRef.current = false;
          firstUnreadPage = Math.floor(lastReadSequence.current / data.pagination.page_size) + 1;
        }
        const fresh = unread > 0 ? fromCounterpart.slice(-unread) : [];
        setNewMessageIds(new Set(fresh.map((m) => m.id)));
        setUnreadMarker(unread > 0 ? { afterSequence: lastReadSequence.current, count: unread } : null);
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
      redirectingRef.current = false;
      if (data.pagination) {
        const pages = data.pagination.pages ?? Math.max(1, Math.ceil(data.pagination.total / data.pagination.page_size));
        const currentPage = data.pagination.page ?? requestedPage;
        setPagination({ ...data.pagination, page: currentPage, pages });
        let nextPage = null;
        if (firstUnreadPage && firstUnreadPage !== currentPage) nextPage = Math.min(firstUnreadPage, pages);
        else if (followLatestRef.current && currentPage !== pages) nextPage = pages;
        else if (currentPage !== requestedPage) nextPage = currentPage;
        if (nextPage !== null && nextPage !== page) {
          // The follow-up load of the page this load picked rides on the same feedback.
          redirectingRef.current = true;
          backgroundNextLoadRef.current = true;
          setPage(nextPage);
        }
      }
      setLoadError(false);
    } catch(e) {
      setLoadError(true);
    }
  };

  useEffect(() => {
    seenMessageIds.current = null;
    lastReadSequence.current = 0;
    followLatestRef.current = true;
    pendingScrollRef.current = "landing";
    setUnreadMarker(null);
    setPage(1);
    setPageSize(10);
    setInv(null);
  }, [id]);

  useEffect(() => {
    const background = backgroundNextLoadRef.current;
    backgroundNextLoadRef.current = false;
    loadData({ background });
  }, [id, page, pageSize]);

  // Polling for messages, paused while the tab is hidden.
  useVisibleInterval(() => loadData({ background: true }), 10000);

  // Generic on purpose: conversation titles stay out of tab titles and browser history.
  useDocumentTitle(t("documentTitle.conversation"));

  useLayoutEffect(() => {
    const mode = pendingScrollRef.current;
    const list = messageListRef.current;
    if (!mode || !list || !messages.length || redirectingRef.current) return;
    pendingScrollRef.current = null;
    // Only the inner scroller moves; the page keeps its position.
    if (dividerRef.current) {
      list.scrollTop += dividerRef.current.getBoundingClientRect().top - list.getBoundingClientRect().top - 8;
    } else if (mode === "landing" || pagination.page === pagination.pages) {
      list.scrollTop = list.scrollHeight;
    } else {
      list.scrollTop = 0;
    }
  }, [messages, pagination]);

  useEffect(() => {
    const sequence = messages.at(-1)?.sequence || 0;
    if (!sequence || sequence <= lastReadSequence.current) return undefined;
    // The marker is cumulative: advance it only from a page contiguous with what was already read.
    if ((messages[0]?.sequence || 0) > lastReadSequence.current + 1) return undefined;
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

  useEffect(() => {
    if (!scrollAfterSendRef.current || pagination.page !== pagination.pages) return;
    scrollAfterSendRef.current = false;
    const frame = requestAnimationFrame(() => {
      const list = messageListRef.current;
      if (list) list.scrollTo({ top: list.scrollHeight, behavior: reducedMotion ? "auto" : "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, pagination, reducedMotion]);

  const handleSend = async (e) => {
    e.preventDefault();
    const content = newMsg.trim();
    if (!content || sending) return;
    setSending(true);
    try {
      await sendInvestigationMessage(id, { content });
      setNewMsg("");
      setActionError("");
      followLatestRef.current = true;
      scrollAfterSendRef.current = true;
      await loadData({ background: true });
    } catch(e) {
      setActionError(t("cscw.sendFailed"));
    } finally {
      setSending(false);
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
  const counterpartDisplayName = inv.counterpart?.name || inv.counterpart?.display_name;
  const ownRole = inv.counterpart?.role === "doctor" ? "patient" : "doctor";

  return (
    <div className="react-page react-conversation">
      <section className="react-panel react-conversation__header">
        <div className="react-conversation__topline">
          <Link to="/dashboard#investigations" className="react-back-link">
            <ArrowLeftIcon />
            {t("common.back")}
          </Link>
        </div>
        <div className="react-panel__header-copy">
          <p className="react-eyebrow">{t(isPatient ? "cscw.conversationEyebrowPatient" : "cscw.conversationEyebrowDoctor")}</p>
          <h1>{inv.title}</h1>
          {counterpartName && (
            <p>{t(inv.counterpart?.role === "doctor" ? "cscw.counterpartDoctor" : "cscw.counterpartPatient")}: <strong>{counterpartName}</strong></p>
          )}
        </div>
        <div className="react-chip-row react-conversation__chips">
          <span className={`react-status-chip react-status-chip--${inv.status}`}>{t(`cscw.status.${inv.status}`, { defaultValue: inv.status })}</span>
          {inv.status === "open" ? (
            <span className="react-badge react-badge--soft react-badge--compact">{inv.awaiting_role === ownRole ? t("cscw.awaitingYou") : t("cscw.awaitingChip", { role: roleLabel(inv.awaiting_role) })}</span>
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
            <h2 id="conversation-messages-title">{t("cscw.messagesTitle")}</h2>
          </div>
        </div>
        {(pagination.pages > 1 || pagination.total > 10) && (
          <div className="react-conversation__pager">
            <Pagination
              page={pagination.page}
              pages={pagination.pages}
              count={pagination.total}
              pageSize={pageSize}
              onPageChange={(nextPage) => { followLatestRef.current = false; pendingScrollRef.current = "page"; setPage(nextPage); }}
              onPageSizeChange={(size) => { followLatestRef.current = false; pendingScrollRef.current = "page"; setPageSize(size); setPage(1); }}
            />
          </div>
        )}
        <ol ref={messageListRef} className="react-message-list" aria-label={t("cscw.messagesLabel")}>
          {messages.map((m) => {
            const isNew = newMessageIds.has(m.id);
            const isOwn = m.author_role === ownRole;
            const isCounterpart = !isOwn && m.author_role === inv.counterpart?.role;
            // Sequences are contiguous, so the first unread message is the one right after the marker.
            const startsUnread = Boolean(unreadMarker) && m.sequence === unreadMarker.afterSequence + 1;
            const author = isOwn ? t("cscw.you") : isCounterpart && counterpartDisplayName ? counterpartDisplayName : roleLabel(m.author_role);
            return (
              <Fragment key={m.id}>
              {startsUnread ? (
                <li ref={dividerRef} className="react-message-divider" role="separator" aria-label={t("cscw.newMessagesDivider", { count: unreadMarker.count })}>
                  <span aria-hidden="true">{t("cscw.newMessagesDivider", { count: unreadMarker.count })}</span>
                </li>
              ) : null}
              <li className={`react-message${isOwn ? " is-own" : ""}${m.author_role === "system" ? " is-system" : ""}${isNew ? " is-new" : ""}`}>
                <div className="react-message__meta">
                  <strong>{author}</strong>
                  <small>{formatDateTime(m.created_at, i18n.language)}</small>
                  {isNew && <span className="react-badge react-badge--count">{t("cscw.newMessage")}</span>}
                </div>
                <p>{m.content}</p>
              </li>
              </Fragment>
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
              <small id="composer-hint" className={`react-composer__hint${newMsg.trim() ? "" : " is-requirement"}`}>
                {newMsg.trim() ? t("cscw.composerHint") : t("cscw.sendEmptyHint")}
              </small>
              <button
                type="submit"
                disabled={sending || !newMsg.trim()}
                aria-busy={sending}
                aria-describedby="composer-hint"
                className="react-button"
              >
                {t("cscw.send")}
              </button>
            </div>
          </form>
        )}

        {inv.status === "open" && (
          <div className="react-conversation__close">
            <p id="conversation-close-hint">{t("cscw.closeHint")}</p>
            <button
              type="button"
              disabled={sending}
              onClick={() => { setActionError(""); setClosing(true); }}
              aria-describedby="conversation-close-hint"
              className="react-button react-button--text react-button--danger-text"
            >
              {t("cscw.close")}
            </button>
          </div>
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
