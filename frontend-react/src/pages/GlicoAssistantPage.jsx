import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../contexts/AuthContext";
import GlicoMediaCapture from "../components/GlicoMediaCapture";
import GlicoProposalCard from "../components/GlicoProposalCard";
import useDocumentTitle from "../hooks/useDocumentTitle";
import "../glico.css";
import {
  cancelGlicoProposal,
  createGlicoCollaborationProposal,
  confirmGlicoProposal,
  createGlicoConversation,
  editGlicoProposal,
  extractGlicoMedia,
  fetchGlicoCapabilities,
  fetchGlicoConversation,
  fetchPatients,
  sendGlicoMessage,
  updateGlicoContext,
  patientReportPdfUrl
} from "../api";

const FAQ_ITEMS = ["howLog", "privacy", "where", "advice"];
const FAQ_NAVIGATE = { where: true };
const KNOWN_ANSWERS = {
  "glico.help.try_manual": "helpManual",
  "glico.reading.unsupported_signal": "clarifySignal",
  "glico.reading.multiple_values": "clarifyMultiple",
  "glico.reading.ambiguous_image": "clarifyImage"
};

function formatDate(iso, locale) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(date);
}

function requestId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Maps an API failure to a localized message key; the server's own text is never shown.
function errorKey(error) {
  if (!error) return "genericError";
  if (error.code === "timeout") return "timeout";
  if (error.code === "aborted") return null;
  const detail = error.detail;
  switch (error.status) {
    case 401: return "sessionError";
    case 403: return detail === "csrf_failed" ? "sessionError" : "notAllowed";
    case 404: return "notFound";
    case 409:
      if (detail === "idempotency_conflict") return "idempotency";
      if (detail === "proposal_version_conflict") return "versionConflict";
      return "contextChanged";
    case 410: return "expired";
    case 413: return "tooLarge";
    case 415: return "unsupported";
    case 422: return detail === "ambiguous_reading" ? "ambiguous" : "invalidFields";
    case 429: return "limit";
    case 503: return "unavailable";
    case 504: return "timeout";
    default:
      if (error.message === "Unauthorized") return "sessionError";
      if (error instanceof TypeError) return "offline";
      return "genericError";
  }
}

function withProposal(conversation, proposal) {
  const others = (conversation?.cards || []).filter((card) => card.type !== "proposal");
  return { ...conversation, cards: [{ type: "proposal", proposal }, ...others] };
}

export default function GlicoAssistantPage() {
  const { t, i18n } = useTranslation();
  const { session } = useAuth();
  useDocumentTitle(t("glicoAssistant.title"));
  const [capabilities, setCapabilities] = useState(null);
  const [conversation, setConversation] = useState(null);
  const [patients, setPatients] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [processing, setProcessing] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [collaborationKind, setCollaborationKind] = useState("investigation_open");
  const [investigationId, setInvestigationId] = useState("");
  const [collaborationTitle, setCollaborationTitle] = useState("");
  const [collaborationText, setCollaborationText] = useState("");
  const [dictating, setDictating] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const abortRef = useRef(null);
  const recognitionRef = useRef(null);
  const activeConversationId = useRef(null);
  const conversationOwner = useRef(null);
  const confirmKeys = useRef(new Map());
  const proposalWrap = useRef(null);

  const isPatient = conversation?.role === "patient";
  const isDoctor = conversation?.role === "doctor";
  const proposal = useMemo(
    () => conversation?.cards?.find((card) => card.type === "proposal")?.proposal || null,
    [conversation]
  );
  const storedReceipt = useMemo(
    () => conversation?.cards?.find((card) => card.type === "receipt")?.receipt || null,
    [conversation]
  );
  const shownReceipt = receipt || (proposal ? null : storedReceipt);
  const hasPatientContext = Boolean(conversation?.context?.patient_id) && (isPatient || Boolean(selectedPatient));
  const textOn = Boolean(capabilities?.text);
  const maxChars = capabilities?.limits?.text_chars || 2000;
  const sessionKey = session?.authenticated ? `${session.account?.id || ""}:${i18n.language}` : null;
  activeConversationId.current = sessionKey && conversationOwner.current === sessionKey ? (conversation?.id || null) : null;

  // Reset volatile patient data immediately when the authenticated identity changes.
  useEffect(() => {
    setCapabilities(null);
    setConversation(null);
    setPatients([]);
    setSelectedPatient("");
    setPeriodStart("");
    setPeriodEnd("");
    setMessages([]);
    setDraft("");
    setBusy(false);
    setProcessing(null);
    setReceipt(null);
    setNotice("");
    setError(null);
    setCollaborationText("");
    setCollaborationTitle("");
    conversationOwner.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    recognitionRef.current?.stop();
    if (!session?.authenticated) {
      confirmKeys.current.clear();
    }
  }, [session?.authenticated, session?.account?.id]);

  const fail = useCallback((reason, extra = {}) => {
    const key = errorKey(reason);
    if (key) setError({ key, retryAfter: reason?.retryAfter, ...extra });
  }, []);

  const addAssistant = useCallback((entry) => {
    setMessages((current) => [...current, { id: requestId(), role: "assistant", ...entry }]);
  }, []);

  const formatDate = (iso) => {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(date);
  };

  const refreshConversation = useCallback(async (id) => {
    const latest = await fetchGlicoConversation(id);
    setConversation((current) => current?.id === id ? ({ ...current, ...latest }) : current);
    return latest;
  }, []);

  useEffect(() => {
    if (!session?.authenticated) return;
    let mounted = true;
    const switchedLanguage = conversation && conversation.locale !== i18n.language;
    setCapabilities(null);
    setConversation(null);
    setMessages([]);
    setReceipt(null);
    setSelectedPatient("");
    setPeriodStart("");
    setPeriodEnd("");
    setCollaborationText("");
    setCollaborationTitle("");
    recognitionRef.current?.stop();
    setNotice(switchedLanguage ? "conversationReset" : "");
    (async () => {
      setBusy(true);
      try {
        const [flags, created] = await Promise.all([
          fetchGlicoCapabilities(i18n.language),
          createGlicoConversation(i18n.language, requestId())
        ]);
        if (!mounted) return;
        conversationOwner.current = sessionKey;
        setCapabilities(flags);
        setConversation(created);
        setMessages([]);
        setReceipt(null);
        setSelectedPatient("");
        setPeriodStart("");
        setPeriodEnd("");
        if (created.role === "doctor") {
          const rows = await fetchPatients({ page: 1, pageSize: 50 }, { background: true });
          if (mounted) setPatients(rows?.items || rows?.patients || rows?.results || []);
        } else {
          const latest = await fetchGlicoConversation(created.id);
          if (mounted) setConversation((current) => current?.id === created.id ? ({ ...current, ...latest }) : current);
        }
      } catch (reason) {
        if (mounted) fail(reason);
      } finally {
        if (mounted) setBusy(false);
      }
    })();
    return () => {
      mounted = false;
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i18n.language, session?.authenticated, session?.account?.id]);

  useEffect(() => {
    if (proposal?.id) proposalWrap.current?.focus();
  }, [proposal?.id]);

  const clearFeedback = () => {
    setError(null);
    setNotice("");
  };

  const choosePatient = async (event) => {
    const patientId = event.target.value;
    setSelectedPatient(patientId);
    setMessages([]);
    setReceipt(null);
    clearFeedback();
    if (!patientId || !conversation) return;
    setBusy(true);
    try {
      const next = await updateGlicoContext(conversation.id, { version: conversation.context_version, patient_id: patientId });
      if (activeConversationId.current === conversation.id) setConversation(next);
    } catch (reason) {
      if (activeConversationId.current !== conversation?.id) return;
      setSelectedPatient("");
      fail(reason);
      if (reason?.status === 409) refreshConversation(conversation.id).catch(() => {});
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const updatePeriod = async (event, clear = false) => {
    event.preventDefault();
    if (!conversation || busy) return;
    const start = clear ? undefined : (periodStart || undefined);
    const end = clear ? undefined : (periodEnd || undefined);
    if (start && end && new Date(start) > new Date(end)) {
      setError({ key: "invalidRange" });
      return;
    }
    if (start && end) {
      const diffDays = (new Date(end) - new Date(start)) / (1000 * 60 * 60 * 24);
      if (diffDays > 366) {
        setError({ key: "maxRange" });
        return;
      }
    }
    clearFeedback();
    setBusy(true);
    try {
      const next = await updateGlicoContext(conversation.id, {
        version: conversation.context_version,
        period_start: start,
        period_end: end
      });
      if (activeConversationId.current === conversation.id) setConversation(next);
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      fail(reason);
      if (reason?.status === 409) refreshConversation(conversation.id).catch(() => {});
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const clearPeriod = async () => {
    if (!conversation || busy) return;
    setPeriodStart("");
    setPeriodEnd("");
    await updatePeriod({ preventDefault: () => {} }, true);
  };

  const showProposal = (next) => {
    setReceipt(null);
    setConversation((current) => withProposal(current, next));
    addAssistant({ text: t("glicoAssistant.reviewPrompt") });
  };

  const handleResult = (result) => {
    if (result?.type === "proposal" && result.proposal) {
      showProposal(result.proposal);
      return;
    }
    if (result?.answer_key === "glico.query.readings" && Array.isArray(result.items) && result.items.length) {
      addAssistant({
        type: "list",
        title: t("glicoAssistant.query.readingsTitle"),
        items: result.items.map((item) => ({
          value: item.glucose_mg_dl,
          date: formatDate(item.measured_at),
          timestamp: item.measured_at,
          context: item.context_label
        })),
        itemType: "reading"
      });
      return;
    }
    if (result?.answer_key === "glico.query.readings") {
      addAssistant({ text: t("glicoAssistant.query.readingsEmpty") });
      return;
    }
    if (result?.answer_key === "glico.query.linked_patients" && Array.isArray(result.items) && result.items.length) {
      addAssistant({
        type: "list",
        title: t("glicoAssistant.query.linkedPatientsTitle"),
        items: result.items.map((item) => ({
          id: item.patient_id,
          name: item.name,
          short_id: item.short_id
        })),
        itemType: "patient"
      });
      return;
    }
    if (result?.answer_key === "glico.query.linked_patients") {
      addAssistant({ text: t("glicoAssistant.query.linkedPatientsEmpty") });
      return;
    }
    if (result?.answer_key === "glico.query.metrics" && Array.isArray(result.items) && result.items.length) {
      addAssistant({
        type: "list",
        title: t("glicoAssistant.query.metricsTitle"),
        items: result.items.map((item) => ({
          date: item.date,
          avg: item.avg_glucose,
          count: item.count,
          min: item.min_glucose,
          max: item.max_glucose,
          freshness: item.freshness
        })),
        itemType: "metric"
      });
      return;
    }
    if (result?.answer_key === "glico.query.metrics") {
      addAssistant({ text: t("glicoAssistant.query.metricsEmpty") });
      return;
    }
    if (result?.answer_key === "glico.query.investigations" && Array.isArray(result.items) && result.items.length) {
      addAssistant({
        type: "list",
        title: t("glicoAssistant.query.investigationsTitle"),
        items: result.items.map((item) => ({
          id: item.id,
          status: item.status,
          date: formatDate(item.opened_at)
        })),
        itemType: "investigation"
      });
      return;
    }
    if (result?.answer_key === "glico.query.investigations") {
      addAssistant({ text: t("glicoAssistant.query.investigationsEmpty") });
      return;
    }
    if (result?.answer_key === "glico.query.atypical_days" && Array.isArray(result.items) && result.items.length) {
      addAssistant({
        type: "list",
        title: t("glicoAssistant.query.atypicalDaysTitle"),
        items: result.items.map((item) => ({
          date: item.date,
          score: item.score,
          indicator_id: item.indicator_id
        })),
        itemType: "atypicalDay"
      });
      return;
    }
    if (result?.answer_key === "glico.query.atypical_days") {
      addAssistant({ text: t("glicoAssistant.query.atypicalDaysEmpty") });
      return;
    }
    if (result?.answer_key === "glico.query.no_current_classification") {
      addAssistant({ text: t("glicoAssistant.query.noCurrentClassification") });
      return;
    }
    if (result?.answer_key === "glico.query.pdf" && conversation?.context?.patient_id) {
      const start = conversation.context.period_start || "";
      const end = conversation.context.period_end || "";
      const url = patientReportPdfUrl(conversation.context.patient_id, { startDate: start, endDate: end, lang: i18n.language });
      if (!start || !end || !url) {
        addAssistant({ text: t("glicoAssistant.query.pdfNeedsPeriod") });
        return;
      }
      addAssistant({
        type: "pdf",
        title: t("glicoAssistant.query.pdfTitle"),
        message: t("glicoAssistant.query.pdfGenerated"),
        url,
        downloadText: t("glicoAssistant.query.pdfDownload")
      });
      return;
    }
    const known = KNOWN_ANSWERS[result?.answer_key];
    const links = (result?.links || []).includes("/") ? ["/dashboard"] : [];
    addAssistant({ text: t(`glicoAssistant.${known || "helpDefault"}`), links });
  };

  const submitMessage = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || !conversation || busy || !hasPatientContext || !textOn) return;
    setDraft("");
    clearFeedback();
    setMessages((current) => [...current, { id: requestId(), role: "user", text }]);
    setBusy(true);
    try {
      const result = await sendGlicoMessage(conversation.id, {
        text,
        context_version: conversation.context_version,
        client_request_id: requestId()
      });
      if (activeConversationId.current === conversation.id) handleResult(result);
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      setDraft(text);
      fail(reason);
      if (reason?.status === 409) refreshConversation(conversation.id).catch(() => {});
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const submitMedia = async (kind, blob) => {
    if (!conversation || busy) return;
    clearFeedback();
    const controller = new AbortController();
    abortRef.current = controller;
    setProcessing(kind);
    setBusy(true);
    try {
      const result = await extractGlicoMedia(conversation.id, kind, blob, {
        contextVersion: conversation.context_version,
        clientRequestId: requestId(),
        signal: controller.signal
      });
      if (activeConversationId.current === conversation.id) handleResult(result);
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      if (reason?.code === "aborted") setNotice("media.discarded");
      else fail(reason);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      if (activeConversationId.current === conversation?.id) {
        setProcessing(null);
        setBusy(false);
      }
    }
  };

  const cancelMedia = () => abortRef.current?.abort();

  const recoverFrom = async (reason) => {
    fail(reason);
    if (reason?.status === 409 || reason?.status === 410) await refreshConversation(conversation.id).catch(() => {});
  };

  const saveProposal = async (fields) => {
    if (!proposal || !conversation) return;
    clearFeedback();
    setBusy(true);
    try {
      const result = await editGlicoProposal(proposal.id, {
        version: proposal.version,
        context_version: conversation.context_version,
        fields
      });
      if (activeConversationId.current === conversation.id) setConversation((current) => current?.id === conversation.id ? withProposal(current, result.proposal) : current);
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      await recoverFrom(reason);
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const confirmProposal = async () => {
    if (!proposal || proposal.state !== "READY" || !conversation) return;
    clearFeedback();
    setBusy(true);
    const slot = `${proposal.id}:${proposal.version}`;
    if (!confirmKeys.current.has(slot)) confirmKeys.current.set(slot, requestId());
    try {
      const result = await confirmGlicoProposal(proposal.id, {
        version: proposal.version,
        context_version: conversation.context_version,
        idempotency_key: confirmKeys.current.get(slot)
      });
      if (activeConversationId.current !== conversation.id) return;
      setReceipt(result?.receipt || null);
      setNotice("confirmed");
      setConversation((current) => ({ ...current, cards: (current?.cards || []).filter((card) => card.type !== "proposal") }));
      refreshConversation(conversation.id).catch(() => {});
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      await recoverFrom(reason);
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const discardProposal = async () => {
    if (!proposal || !conversation) return;
    clearFeedback();
    setBusy(true);
    try {
      await cancelGlicoProposal(proposal.id, proposal.version);
      if (activeConversationId.current !== conversation.id) return;
      setConversation((current) => ({ ...current, cards: (current?.cards || []).filter((card) => card.type !== "proposal") }));
      setNotice("cancelled");
      refreshConversation(conversation.id).catch(() => {});
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      await recoverFrom(reason);
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const askFaq = (item) => {
    clearFeedback();
    setMessages((current) => [
      ...current,
      { id: requestId(), role: "user", text: t(`glicoAssistant.faq.${item}.q`) },
      { id: requestId(), role: "assistant", text: t(`glicoAssistant.faq.${item}.a`), links: FAQ_NAVIGATE[item] ? ["/dashboard"] : [] }
    ]);
  };

  const prepareCollaboration = async (event) => {
    event.preventDefault();
    if (!conversation || busy || !collaborationText.trim()) return;
    setBusy(true);
    clearFeedback();
    try {
      const result = await createGlicoCollaborationProposal(conversation.id, {
        kind: collaborationKind,
        ...(collaborationKind === "investigation_open" ? { title: collaborationTitle.trim() } : { investigation_id: investigationId }),
        content: collaborationText.trim()
      });
      setCollaborationText("");
      setCollaborationTitle("");
      showProposal(result.proposal);
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      fail(reason);
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const investigations = messages.flatMap((message) => message.itemType === "investigation" ? message.items : []);

  const startDictation = () => {
    if (dictating) {
      recognitionRef.current?.stop();
      return;
    }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setError({ key: "dictationUnavailable" });
      return;
    }
    const recognition = new Recognition();
    recognition.lang = i18n.language;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((entry) => entry[0]?.transcript || "").join(" ").trim();
      if (transcript) setCollaborationText((current) => `${current}${current ? " " : ""}${transcript}`);
    };
    recognition.onerror = () => setError({ key: "dictationError" });
    recognition.onend = () => {
      recognitionRef.current = null;
      setDictating(false);
    };
    recognitionRef.current = recognition;
    setDictating(true);
    recognition.start();
  };

  const errorText = error
    ? error.key === "limit" && error.retryAfter
      ? t("glicoAssistant.errors.limitRetry", { seconds: error.retryAfter })
      : t(`glicoAssistant.errors.${error.key}`)
    : "";
  const receiptTime = shownReceipt?.committed_at
    ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(shownReceipt.committed_at))
    : "";
  const analyticsLabel = shownReceipt
    ? t(`glicoAssistant.analytics.${shownReceipt.analytics_status}`, { defaultValue: t("glicoAssistant.analytics.unknown") })
    : "";

  return (
    <section className="react-page glico" aria-labelledby="glico-title">
      <header className="react-page-header glico__header">
        <h1 id="glico-title">{t("glicoAssistant.title")}</h1>
        <p>{t("glicoAssistant.intro")}</p>
      </header>

      {isDoctor ? (
        <section className="react-panel glico__context">
          <label htmlFor="glico-patient">{t("glicoAssistant.selectPatient")}</label>
          <select id="glico-patient" className="react-field" value={selectedPatient} onChange={choosePatient} disabled={busy}>
            <option value="">{t("glicoAssistant.selectPatientPlaceholder")}</option>
            {patients.map((patient) => (
              <option key={patient.id} value={patient.id}>{patient.display_name}</option>
            ))}
          </select>
          <p className="glico-hint">{patients.length || busy ? t("glicoAssistant.patientContextPrivacy") : t("glicoAssistant.noPatients")}</p>
        </section>
      ) : null}

      {hasPatientContext && (
        <section className="react-panel glico__context">
          <h3>{t("glicoAssistant.period.label")}</h3>
          <form onSubmit={updatePeriod} className="glico__period-form">
            <div className="glico__period-fields">
              <label htmlFor="glico-period-start">{t("glicoAssistant.period.startLabel")}</label>
              <input id="glico-period-start" className="react-field" type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} disabled={busy} />
              <label htmlFor="glico-period-end">{t("glicoAssistant.period.endLabel")}</label>
              <input id="glico-period-end" className="react-field" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} disabled={busy} />
            </div>
            <p className="glico-hint">{t("glicoAssistant.period.maxRange")}</p>
            {error?.key === "invalidRange" && <p className="glico-hint" role="alert">{t("glicoAssistant.period.invalidRange")}</p>}
            {error?.key === "maxRange" && <p className="glico-hint" role="alert">{t("glicoAssistant.period.maxRange")}</p>}
            <div className="glico__period-actions">
              <button type="submit" className="react-button react-button--primary" disabled={busy}>
                {t("glicoAssistant.period.apply")}
              </button>
              {(periodStart || periodEnd) && (
                <button type="button" className="react-button react-button--quiet" onClick={clearPeriod} disabled={busy}>
                  {t("glicoAssistant.period.clear")}
                </button>
              )}
            </div>
          </form>
        </section>
      )}

      <div className="glico__status" aria-live="polite">
        {error ? <div className="glico-alert glico-alert--error" role="alert" data-testid="glico-error">{errorText}</div> : null}
        {notice ? <div className="glico-alert glico-alert--success" role="status">{t(`glicoAssistant.${notice}`)}</div> : null}
      </div>

      {capabilities && !textOn ? (
        <section className="react-panel glico__disabled" role="status">
          <h2>{t("glicoAssistant.unavailableTitle")}</h2>
          <p>{t("glicoAssistant.unavailableBody")}</p>
          <Link className="react-button react-button--ghost" to="/dashboard">{t("glicoAssistant.goDashboard")}</Link>
        </section>
      ) : null}

      {textOn ? (
        <section className="react-panel glico__chat" aria-label={t("glicoAssistant.chatLabel")}>
          <ul className="glico__capabilities" aria-label={t("glicoAssistant.chatLabel")}>
            <li className="react-badge react-badge--pending">{t("glicoAssistant.textAvailable")}</li>
            <li className="react-badge">{capabilities.photo ? t("glicoAssistant.photoAvailable") : t("glicoAssistant.photoUnavailable")}</li>
            <li className="react-badge">{capabilities.audio ? t("glicoAssistant.audioAvailable") : t("glicoAssistant.audioUnavailable")}</li>
          </ul>

          <div className="glico__thread" role="log" aria-live="polite" aria-relevant="additions" data-testid="glico-thread">
            {!messages.length ? <p className="glico__empty">{t("glicoAssistant.empty")}</p> : null}
            {messages.map((message) => (
              <article key={message.id} className={`glico__message glico__message--${message.role}`}>
                <span className="glico__author">{t(message.role === "user" ? "glicoAssistant.userSaid" : "glicoAssistant.glicoSaid")}</span>
                {message.type === "list" ? (
                  <div className="glico__list" aria-label={message.title}>
                    <h3>{message.title}</h3>
                    <ul>
                      {message.items.map((item, idx) => (
                        <li key={`${message.id}-${idx}`}>
                          {message.itemType === "reading" && (
                            <>
                              <strong>{item.value} mg/dL</strong>
                              <time dateTime={item.timestamp}>{item.date}</time>
                              {item.context && <span className="glico__context-label">{item.context}</span>}
                            </>
                          )}
                          {message.itemType === "patient" && (
                            <>
                              <strong>{item.name}</strong>
                              <span>({item.short_id})</span>
                            </>
                          )}
                          {message.itemType === "metric" && (
                            <>
                              <time dateTime={item.date}>{item.date}</time>
                              <span>{t("glicoAssistant.query.metricAverage")}: {item.avg} mg/dL</span>
                              <span>{t("glicoAssistant.query.metricReadings")}: {item.count}</span>
                              <span>{t("glicoAssistant.query.metricMinMax")}: {item.min}/{item.max} mg/dL</span>
                              <span>{t("glicoAssistant.query.metricFreshness")}: {t(`glicoAssistant.analytics.${item.freshness}`, { defaultValue: item.freshness })}</span>
                            </>
                          )}
                          {message.itemType === "investigation" && (
                            <>
                              <strong>{item.id}</strong>
                              <span>{t("glicoAssistant.query.status")}: {t(`investigation.status.${String(item.status).toLowerCase()}`, { defaultValue: t("glicoAssistant.query.statusUnknown") })}</span>
                              <time dateTime={item.date}>{item.date}</time>
                            </>
                          )}
                          {message.itemType === "atypicalDay" && (
                            <>
                              <time dateTime={item.date}>{item.date}</time>
                              <span>{t("glicoAssistant.query.score")}: {item.score}</span>
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : message.type === "pdf" ? (
                  <div className="glico__pdf">
                    <h3>{message.title}</h3>
                    <p>{message.message}</p>
                    {message.url && (
                      <a href={message.url} className="react-button react-button--primary" download>
                        {message.downloadText}
                      </a>
                    )}
                  </div>
                ) : (
                  <p>{message.text}</p>
                )}
                {message.links?.map((to) => (
                  <Link key={to} to={to} className="glico__link">{t("glicoAssistant.goDashboard")}</Link>
                ))}
              </article>
            ))}
          </div>

          {shownReceipt ? (
            <div className="glico-alert glico-alert--success glico__receipt" role="status" data-testid="glico-receipt">
              <strong>{t("glicoAssistant.receiptTitle")}</strong>
              <p>{t("glicoAssistant.receiptBody", { time: receiptTime, status: analyticsLabel })}</p>
              {isPatient && session_panel_link(conversation) ? (
                <Link to={session_panel_link(conversation)} className="glico__link">{t("glicoAssistant.viewPatientPanel")}</Link>
              ) : null}
            </div>
          ) : null}

          {proposal ? (
            <div ref={proposalWrap} tabIndex={-1} className="glico__proposal-wrap">
              <GlicoProposalCard
                proposal={proposal}
                role={conversation?.role}
                busy={busy}
                onSave={saveProposal}
                onConfirm={confirmProposal}
                onDiscard={discardProposal}
              />
            </div>
          ) : null}

          <section className="glico__faq" aria-labelledby="glico-faq-title">
            <h2 id="glico-faq-title">{t("glicoAssistant.faq.title")}</h2>
            <ul>
              {FAQ_ITEMS.map((item) => (
                <li key={item}>
                  <button type="button" className="react-button react-button--quiet react-button--compact" onClick={() => askFaq(item)}>
                    {t(`glicoAssistant.faq.${item}.q`)}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {hasPatientContext ? (
            <section className="glico__collaboration" aria-labelledby="glico-collaboration-title">
              <h2 id="glico-collaboration-title">{t("glicoAssistant.investigation.sectionTitle")}</h2>
              <form onSubmit={prepareCollaboration} className="glico__collaboration-form">
                <label htmlFor="glico-collaboration-kind">{t("glicoAssistant.investigation.actionLabel")}</label>
                <select id="glico-collaboration-kind" className="react-field" value={collaborationKind} onChange={(event) => setCollaborationKind(event.target.value)} disabled={busy}>
                  <option value="investigation_open">{t("glicoAssistant.investigation.openAction")}</option>
                  <option value="investigation_message">{t("glicoAssistant.investigation.replyAction")}</option>
                </select>
                {collaborationKind === "investigation_open" ? (
                  <>
                    <label htmlFor="glico-collaboration-subject">{t("glicoAssistant.investigation.titleLabel")}</label>
                    <input id="glico-collaboration-subject" className="react-field" maxLength={180} value={collaborationTitle} onChange={(event) => setCollaborationTitle(event.target.value)} disabled={busy} />
                  </>
                ) : (
                  <>
                    <label htmlFor="glico-investigation-id">{t("glicoAssistant.investigation.selectLabel")}</label>
                    <select id="glico-investigation-id" className="react-field" value={investigationId} onChange={(event) => setInvestigationId(event.target.value)} disabled={busy}>
                      <option value="">{t("glicoAssistant.investigation.selectPlaceholder")}</option>
                      {investigations.map((item) => <option key={item.id} value={item.id}>{t("glicoAssistant.query.investigationItem", { id: item.id, status: t(`investigation.status.${String(item.status).toLowerCase()}`, { defaultValue: t("glicoAssistant.query.statusUnknown") }), date: item.date })}</option>)}
                    </select>
                    {!investigations.length ? <p className="glico-hint">{t("glicoAssistant.investigation.findFirstHint")}</p> : null}
                  </>
                )}
                <label htmlFor="glico-collaboration-message">{t("glicoAssistant.investigation.messageLabel")}</label>
                <textarea id="glico-collaboration-message" className="react-field" rows={3} maxLength={10000} value={collaborationText} onChange={(event) => setCollaborationText(event.target.value)} disabled={busy} />
                <div className="glico__collaboration-actions">
                  <button type="button" className="react-button react-button--quiet" onClick={startDictation} disabled={busy}>{dictating ? t("glicoAssistant.investigation.stopDictation") : t("glicoAssistant.investigation.dictate")}</button>
                  <button type="submit" className="react-button react-button--primary" disabled={busy || !collaborationText.trim() || (collaborationKind === "investigation_open" && !collaborationTitle.trim()) || (collaborationKind === "investigation_message" && !investigationId)}>{t("glicoAssistant.investigation.review")}</button>
                </div>
                <p className="glico-hint">{t("glicoAssistant.investigation.dictationPrivacy")}</p>
              </form>
            </section>
          ) : null}

          <form className="glico__composer" onSubmit={submitMessage}>
            <label htmlFor="glico-message">{t("glicoAssistant.messageLabel")}</label>
            <textarea
              id="glico-message"
              className="react-field"
              rows={3}
              maxLength={maxChars}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={t("glicoAssistant.placeholder")}
              disabled={!hasPatientContext || busy}
              aria-describedby="glico-composer-help"
            />
            <div className="glico__composer-footer">
              <span id="glico-composer-help" className="glico-hint">
                {!hasPatientContext
                  ? (isDoctor ? t("glicoAssistant.selectPatientRequired") : t("glicoAssistant.contextLoading"))
                  : `${t("glicoAssistant.charCount", { count: draft.length, max: maxChars })} · ${t("glicoAssistant.privacyNote")}`}
              </span>
              <button type="submit" className="react-button react-button--primary" disabled={!hasPatientContext || busy || !draft.trim()}>
                {busy && !processing ? t("glicoAssistant.working") : t("glicoAssistant.send")}
              </button>
            </div>
          </form>

          <GlicoMediaCapture
            capabilities={capabilities}
            enabled={hasPatientContext}
            processing={processing}
            onSubmit={submitMedia}
            onCancel={cancelMedia}
            onError={(key) => setError({ key })}
          />
        </section>
      ) : null}

      <p className="glico-hint glico__disclaimer">{t("glicoAssistant.notClinicalAdvice")}</p>
    </section>
  );
}

function session_panel_link(conversation) {
  const id = conversation?.context?.patient_id;
  return id ? `/patients/${id}` : null;
}
