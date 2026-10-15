import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../contexts/AuthContext";
import GlicoMediaCapture from "../components/GlicoMediaCapture";
import GlicoNotes from "../components/GlicoNotes";
import GlicoPatientPicker from "../components/GlicoPatientPicker";
import GlicoProposalCard from "../components/GlicoProposalCard";
import { CloseIcon, MicIcon, SendIcon } from "../components/GlicoIcons";
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

// 35794 -> "9 h 56 min"; short waits stay in seconds.
function formatWait(seconds) {
  const total = Math.max(1, Math.round(Number(seconds) || 0));
  if (total < 90) return `${total} s`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.ceil((total % 3600) / 60);
  if (hours === 0) return `${minutes} min`;
  return minutes === 60 ? `${hours + 1} h` : `${hours} h ${String(minutes).padStart(2, "0")} min`;
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
  const [collab, setCollab] = useState(null);
  const [dictating, setDictating] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const abortRef = useRef(null);
  const recognitionRef = useRef(null);
  const activeConversationId = useRef(null);
  const conversationOwner = useRef(null);
  const confirmKeys = useRef(new Map());
  const proposalWrap = useRef(null);
  const threadRef = useRef(null);
  const stickToEnd = useRef(true);
  const [moreOpen, setMoreOpen] = useState(false);
  const [awayFromEnd, setAwayFromEnd] = useState(false);
  const composerRef = useRef(null);

  const isPatient = conversation?.role === "patient";
  const isDoctor = conversation?.role === "doctor";
  const selectedPatientName = patients.find((patient) => patient.id === selectedPatient)?.display_name || "";
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
    setCollab(null);
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
    setCollab(null);
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
    if (!proposal?.id) return undefined;
    proposalWrap.current?.focus({ preventScroll: true });
    // A card taller than the chat shows its top (what to review), not its bottom.
    const frame = requestAnimationFrame(() => {
      const thread = threadRef.current;
      const wrap = proposalWrap.current;
      if (!thread || !wrap) return;
      const top = wrap.getBoundingClientRect().top - thread.getBoundingClientRect().top + thread.scrollTop;
      if (wrap.offsetHeight > thread.clientHeight - 24) thread.scrollTo?.({ top: Math.max(0, top - 12), behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [proposal?.id]);

  // Like a chat app: follow the conversation while the reader is at the bottom, leave them alone once they scroll up.
  const scrollToEnd = useCallback((behavior = "smooth") => {
    const thread = threadRef.current;
    if (!thread) return;
    stickToEnd.current = true;
    setAwayFromEnd(false);
    thread.scrollTo?.({ top: thread.scrollHeight, behavior });
  }, []);

  const onThreadScroll = () => {
    const thread = threadRef.current;
    if (!thread) return;
    const away = thread.scrollHeight - thread.scrollTop - thread.clientHeight > 96;
    stickToEnd.current = !away;
    setAwayFromEnd(away);
  };

  useEffect(() => {
    // The welcome screen is read from the top; only a real conversation follows its end.
    if (!messages.length && !proposal && !shownReceipt) {
      threadRef.current?.scrollTo?.({ top: 0 });
      return;
    }
    if (stickToEnd.current || messages[messages.length - 1]?.role === "user") scrollToEnd();
    else setAwayFromEnd(true);
  }, [messages.length, proposal?.id, shownReceipt, busy, scrollToEnd]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const field = composerRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 176)}px`;
  }, [draft, textOn]);

  useEffect(() => {
    if (!hasPatientContext) setCollab(null);
  }, [hasPatientContext]);

  const onComposerKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

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
        // A doctor's context update always names the patient again; the server re-checks the active link.
        ...(isDoctor ? { patient_id: selectedPatient } : {}),
        period_start: start,
        period_end: end
      });
      if (activeConversationId.current === conversation.id) {
        setConversation(next);
        addAssistant({ text: start || end
          ? t("glicoAssistant.period.applied", { range: `${start || "…"} – ${end || "…"}` })
          : t("glicoAssistant.period.cleared") });
      }
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
    // A newer proposal replaces the one on screen: cancel the old one on the server too, so it
    // cannot come back from a refresh after the newer one is confirmed.
    if (proposal && proposal.id !== next.id) cancelGlicoProposal(proposal.id, proposal.version).catch(() => {});
    setReceipt(null);
    setConversation((current) => withProposal(current, next));
    addAssistant({ text: t("glicoAssistant.reviewPrompt") });
    addAssistant({ type: "proposal", proposalId: next.id });
  };

  const handleResult = (result) => {
    if (result?.type === "message" && typeof result.text === "string" && result.text.trim()) {
      addAssistant({ text: result.text });
      return;
    }
    if (result?.type === "proposal" && result.proposal) {
      showProposal(result.proposal);
      return;
    }
    if (result?.answer_key === "glico.query.readings" && Array.isArray(result.items) && result.items.length) {
      // The list is long; the conversation shows the most recent day with records, newest first.
      const dayOf = (iso) => new Date(iso).toDateString();
      const sorted = [...result.items].sort((left, right) => new Date(right.measured_at) - new Date(left.measured_at));
      const lastDay = dayOf(sorted[0].measured_at);
      const ofLastDay = sorted.filter((item) => dayOf(item.measured_at) === lastDay);
      addAssistant({
        type: "list",
        title: t(isDoctor ? "glicoAssistant.query.readingsTitleDoctor" : "glicoAssistant.query.readingsTitle"),
        subtitle: t("glicoAssistant.query.readingsLastDay", {
          date: new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(new Date(sorted[0].measured_at)),
          count: ofLastDay.length
        }),
        items: ofLastDay.map((item) => ({
          value: item.glucose_mg_dl,
          date: new Intl.DateTimeFormat(i18n.language, { timeStyle: "short" }).format(new Date(item.measured_at)),
          timestamp: item.measured_at,
          context: item.context_label ? t(`enums.context.${item.context_label}`, { defaultValue: item.context_label.replace(/_/g, " ") }) : ""
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
        addAssistant({ text: t("glicoAssistant.query.pdfNeedsPeriod"), actions: ["period"] });
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

  const sendText = async (text, fromDraft = false) => {
    if (!conversation || busy || !hasPatientContext || !textOn) return null;
    if (fromDraft) setDraft("");
    clearFeedback();
    setMessages((current) => [...current, { id: requestId(), role: "user", text }]);
    setBusy(true);
    try {
      // Short plain-text context so a language model can follow up ("and yesterday?").
      const history = capabilities?.language_model
        ? messages.filter((message) => typeof message.text === "string" && message.text).slice(-6)
            .map((message) => ({ role: message.role, text: message.text.slice(0, 600) }))
        : [];
      const result = await sendGlicoMessage(conversation.id, {
        text,
        context_version: conversation.context_version,
        client_request_id: requestId(),
        ...(history.length ? { history } : {})
      });
      if (activeConversationId.current === conversation.id) handleResult(result);
      return result;
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return null;
      if (fromDraft) setDraft(text);
      fail(reason);
      if (reason?.status === 409) refreshConversation(conversation.id).catch(() => {});
      return null;
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const submitMessage = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || !conversation || busy || !hasPatientContext || !textOn) return;
    if (collab) {
      await prepareCollaboration(text);
      return;
    }
    await sendText(text, true);
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
      if (activeConversationId.current === conversation.id) {
        if (kind === "audio" && typeof result?.transcript === "string" && result.transcript.trim()) {
          setMessages((current) => [...current, { id: requestId(), role: "user", text: result.transcript.trim() }]);
        }
        handleResult(result);
      }
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
      setMessages((current) => {
        const turned = current.map((message) => (
          message.type === "proposal" && message.proposalId === proposal.id
            ? { ...message, type: "receipt", receipt: result?.receipt || null }
            : message));
        return turned.some((message) => message.type === "receipt" && message.receipt === (result?.receipt || null))
          ? turned
          : [...turned, { id: requestId(), role: "assistant", type: "receipt", receipt: result?.receipt || null }];
      });
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
      setMessages((current) => current.filter((message) => !(message.type === "proposal" && message.proposalId === proposal.id)));
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

  const prepareCollaboration = async (text) => {
    if (!conversation || busy || !collab) return;
    if (collab.kind === "investigation_message" && !collab.investigationId) {
      setError({ key: "pickInvestigation" });
      return;
    }
    clearFeedback();
    setDraft("");
    setMessages((current) => [...current, { id: requestId(), role: "user", text }]);
    setBusy(true);
    try {
      const title = text.split("\n")[0].replace(/\s+/g, " ").trim().slice(0, 80);
      const result = await createGlicoCollaborationProposal(conversation.id, {
        kind: collab.kind,
        ...(collab.kind === "investigation_open" ? { title } : { investigation_id: collab.investigationId }),
        content: text
      });
      setCollab(null);
      showProposal(result.proposal);
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      setDraft(text);
      fail(reason);
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  const openPeriodCard = () => {
    clearFeedback();
    setMessages((current) => [...current.filter((message) => message.type !== "period"), { id: requestId(), role: "assistant", type: "period" }]);
  };

  const askPdf = () => {
    clearFeedback();
    setMessages((current) => [...current, { id: requestId(), role: "user", text: t("glicoAssistant.chips.pdf") }]);
    handleResult({ answer_key: "glico.query.pdf" });
  };

  const startOpenQuestion = () => {
    clearFeedback();
    setCollab({ kind: "investigation_open" });
    addAssistant({ text: t("glicoAssistant.collab.openPrompt") });
    composerRef.current?.focus();
  };

  const startReplyQuestion = async () => {
    setCollab({ kind: "investigation_message", investigationId: "" });
    const result = await sendText(t("glicoAssistant.chips.investigations"));
    if (result?.items?.length) addAssistant({ text: t("glicoAssistant.collab.replyPrompt") });
    else setCollab(null);
  };

  const selectInvestigation = (id) => {
    setCollab((current) => (current ? { ...current, investigationId: id } : current));
    composerRef.current?.focus();
  };

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
      if (transcript) setDraft((current) => `${current}${current ? " " : ""}${transcript}`);
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

  const isoDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

  // One tap: sets the period to the last N months and hands over the PDF link.
  const reportForMonths = async (months) => {
    if (!conversation || busy || !hasPatientContext) return;
    clearFeedback();
    const end = new Date();
    const start = new Date();
    start.setMonth(start.getMonth() - months);
    setMessages((current) => [...current, { id: requestId(), role: "user", text: t("glicoAssistant.chips.reportMonths", { count: months }) }]);
    setBusy(true);
    try {
      const next = await updateGlicoContext(conversation.id, {
        version: conversation.context_version,
        ...(isDoctor ? { patient_id: selectedPatient } : {}),
        period_start: isoDate(start),
        period_end: isoDate(end)
      });
      if (activeConversationId.current !== conversation.id) return;
      setConversation(next);
      setPeriodStart("");
      setPeriodEnd("");
      const url = patientReportPdfUrl(next.context.patient_id, { startDate: isoDate(start), endDate: isoDate(end), lang: i18n.language });
      addAssistant({
        type: "pdf",
        title: t("glicoAssistant.query.pdfTitle"),
        message: t("glicoAssistant.query.pdfGenerated"),
        url,
        downloadText: t("glicoAssistant.query.pdfDownload")
      });
    } catch (reason) {
      if (activeConversationId.current !== conversation.id) return;
      fail(reason);
      if (reason?.status === 409) refreshConversation(conversation.id).catch(() => {});
    } finally {
      if (activeConversationId.current === conversation.id) setBusy(false);
    }
  };

  // The few things people ask for every day stay one tap away; the rest sits behind "More options".
  const reportChip = (months) => ({ key: `report-${months}`, label: t("glicoAssistant.chips.reportMonths", { count: months }), run: () => reportForMonths(months) });
  const readingsText = t(isDoctor ? "glicoAssistant.chips.readingsDoctor" : "glicoAssistant.chips.readings");
  const readingsChip = { key: "readings", label: readingsText, run: () => sendText(readingsText) };
  const atypicalChip = { key: "atypical", label: t("glicoAssistant.chips.atypical"), run: () => sendText(t("glicoAssistant.chips.atypical")) };
  const pdfChip = { key: "pdf", label: t("glicoAssistant.chips.pdf"), run: askPdf };
  const periodChip = { key: "period", label: t("glicoAssistant.chips.period"), run: openPeriodCard };
  const openChip = { key: "open", label: t("glicoAssistant.chips.open"), run: startOpenQuestion };
  const replyChip = { key: "reply", label: t("glicoAssistant.chips.reply"), run: startReplyQuestion };

  // The everyday shortcuts stay one tap away; the rest sits behind "More options". A doctor reviews and asks
  // questions, never logs readings, so the shortcuts and the help topics differ by role.
  const mainChips = !hasPatientContext ? []
    : isDoctor ? [readingsChip, atypicalChip, reportChip(1), reportChip(3)]
    : [readingsChip, atypicalChip, reportChip(1), reportChip(2), reportChip(3)];
  const actionChips = !hasPatientContext ? []
    : isDoctor ? []
    : [pdfChip, periodChip, openChip, replyChip];
  const faqChips = hasPatientContext && !isDoctor
    ? FAQ_ITEMS.map((item) => ({ key: `faq-${item}`, label: t(`glicoAssistant.faq.${item}.q`), run: () => askFaq(item) }))
    : [];

  const hasMoreChips = actionChips.length + faqChips.length > 0;

  const errorText = error
    ? error.key === "limit" && error.retryAfter
      ? t("glicoAssistant.errors.limitRetry", { wait: formatWait(error.retryAfter) })
      : t(`glicoAssistant.errors.${error.key}`)
    : "";
  const receiptBlock = (data) => {
    const time = data?.committed_at
      ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(data.committed_at))
      : "";
    const status = data
      ? t(`glicoAssistant.analytics.${data.analytics_status}`, { defaultValue: t("glicoAssistant.analytics.unknown") })
      : "";
    return (
      <div className="glico-alert glico-alert--success glico__receipt" role="status" data-testid="glico-receipt">
        <strong>{t("glicoAssistant.receiptTitle")}</strong>
        <p>{t("glicoAssistant.receiptBody", { time, status })}</p>
        {isPatient && session_panel_link(conversation) ? (
          <Link to={session_panel_link(conversation)} className="glico__link">{t("glicoAssistant.viewPatientPanel")}</Link>
        ) : null}
      </div>
    );
  };

  const proposalBlock = (
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
  );
  const proposalInThread = Boolean(proposal) && messages.some((message) => message.type === "proposal" && message.proposalId === proposal.id);
  const receiptInThread = messages.some((message) => message.type === "receipt");

  return (
    <section className="react-page glico glico--chat" aria-labelledby="glico-title">
      <h1 id="glico-title" className="react-visually-hidden">{t("glicoAssistant.title")}</h1>
      <header className="glico-bar">
        {isDoctor ? (
          <div className="glico-bar__patient">
            <GlicoPatientPicker
              patients={patients}
              value={selectedPatient}
              disabled={busy}
              onChange={(id) => choosePatient({ target: { value: id } })}
            />
          </div>
        ) : null}
      </header>
      {isDoctor && !selectedPatient ? (
        <p className="glico-hint glico-bar__hint">{patients.length || busy ? t("glicoAssistant.patientContextPrivacy") : t("glicoAssistant.noPatients")}</p>
      ) : null}

      {capabilities && !textOn ? (
        <section className="glico-panel glico__disabled" role="status">
          <h2>{t("glicoAssistant.unavailableTitle")}</h2>
          <p>{t("glicoAssistant.unavailableBody")}</p>
          <Link className="react-button react-button--ghost" to="/dashboard">{t("glicoAssistant.goDashboard")}</Link>
        </section>
      ) : null}

      {textOn ? (
        <section className="glico__chat" aria-label={t("glicoAssistant.chatLabel")}>
          <div ref={threadRef} onScroll={onThreadScroll} className="glico__thread" role="log" aria-live="polite" aria-relevant="additions" data-testid="glico-thread">
            {!messages.length && !proposal && !shownReceipt ? (
              <div className="glico-welcome">
                <img src="/img/mascote-avatar-420.webp" srcSet="/img/mascote-avatar-192.webp 192w, /img/mascote-avatar-420.webp 420w" sizes="132px" alt="" width="132" height="132" className="glico-welcome__mark" />
                <h2>{t(isDoctor ? (hasPatientContext ? "glicoAssistant.doctor.greetingPatient" : "glicoAssistant.doctor.greeting") : "glicoAssistant.greeting", { name: selectedPatientName })}</h2>
                <p className="glico__empty">{hasPatientContext ? t(isDoctor ? "glicoAssistant.doctor.greetingBody" : "glicoAssistant.greetingBody") : (isDoctor ? t("glicoAssistant.selectPatientRequired") : t("glicoAssistant.contextLoading"))}</p>
                {hasPatientContext ? (
                  <>
                    <ul className="glico-suggestions" aria-label={t("glicoAssistant.chips.title")}>
                      {mainChips.map((chip) => (
                        <li key={chip.key}>
                          <button type="button" className="glico-chip" onClick={chip.run} disabled={busy}>{chip.label}</button>
                        </li>
                      ))}
                      {hasMoreChips ? <li>
                        <button type="button" className="glico-chip glico-chip--quiet glico-chip--more" aria-expanded={moreOpen} onClick={() => setMoreOpen((open) => !open)}>
                          {t(moreOpen ? "glicoAssistant.chips.less" : "glicoAssistant.chips.more")}
                        </button>
                      </li> : null}
                    </ul>
                    {moreOpen ? (
                      <ul className="glico-suggestions glico-suggestions--faq" aria-label={t("glicoAssistant.faq.title")}>
                        {[...actionChips, ...faqChips].map((chip) => (
                          <li key={chip.key}>
                            <button type="button" className="glico-chip glico-chip--quiet" onClick={chip.run} disabled={busy}>{chip.label}</button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                ) : null}
              </div>
            ) : null}

            {messages.map((message) => (
              <article key={message.id} className={`glico__message glico__message--${message.role}`}>
                {message.role === "assistant" ? <img src="/img/mascote-avatar-96.webp" alt="" className="glico__avatar" width="40" height="40" /> : null}
                <div className={`glico__bubble${["proposal", "receipt"].includes(message.type) ? " glico__bubble--wide" : ""}`}>
                  <span className="react-visually-hidden">{t(message.role === "user" ? "glicoAssistant.userSaid" : "glicoAssistant.glicoSaid")}</span>
                  {message.type === "proposal" ? (
                    proposal && proposal.id === message.proposalId
                      ? proposalBlock
                      : <p className="glico-hint">{t("glicoAssistant.proposalReplaced")}</p>
                  ) : message.type === "receipt" ? (
                    receiptBlock(message.receipt)
                  ) : message.type === "period" ? (
                    <form onSubmit={updatePeriod} className="glico__period-form glico-card">
                      <h3>{t("glicoAssistant.period.label")}</h3>
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
                  ) : message.type === "list" ? (
                    <div className="glico__list" aria-label={message.title}>
                      <h3>{message.title}</h3>
                      {message.subtitle ? <p className="glico-hint">{message.subtitle}</p> : null}
                      <ul>
                        {message.items.map((item, idx) => (
                          <li key={`${message.id}-${idx}`} className={message.itemType === "investigation" && collab?.kind === "investigation_message" ? "is-pickable" : undefined}>
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
                                {collab?.kind === "investigation_message" ? (
                                  <button type="button" className="glico__pick" aria-pressed={collab.investigationId === item.id} onClick={() => selectInvestigation(item.id)}>
                                    {t("glicoAssistant.collab.reply")}
                                  </button>
                                ) : null}
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
                  {message.actions?.includes("period") ? (
                    <button type="button" className="glico-chip glico-chip--inline" onClick={openPeriodCard}>{t("glicoAssistant.chips.period")}</button>
                  ) : null}
                  {message.links?.map((to) => (
                    <Link key={to} to={to} className="glico__link">{t("glicoAssistant.goDashboard")}</Link>
                  ))}
                </div>
              </article>
            ))}

            {shownReceipt && !receipt && !receiptInThread ? (
              <article className="glico__message glico__message--assistant">
                <img src="/img/mascote-avatar-96.webp" alt="" className="glico__avatar" width="40" height="40" />
                <div className="glico__bubble glico__bubble--wide">{receiptBlock(shownReceipt)}</div>
              </article>
            ) : null}

            {proposal && !proposalInThread ? (
              <article className="glico__message glico__message--assistant">
                <img src="/img/mascote-avatar-96.webp" alt="" className="glico__avatar" width="40" height="40" />
                <div className="glico__bubble glico__bubble--wide">{proposalBlock}</div>
              </article>
            ) : null}

            {busy && !processing && messages.length ? (
              <div className="glico__typing" role="status">
                <img src="/img/mascote-avatar-96.webp" alt="" className="glico__avatar" width="40" height="40" />
                <span className="glico__dots" aria-hidden="true"><i /><i /><i /></span>
                <span className="react-visually-hidden">{t("glicoAssistant.working")}</span>
              </div>
            ) : null}
          </div>

          {awayFromEnd ? (
            <button type="button" className="glico-jump" onClick={() => scrollToEnd()} aria-label={t("glicoAssistant.jumpToEnd")}>
              <SendIcon size={18} />
            </button>
          ) : null}

          <div className="glico-dock">
            <div className="glico__status" aria-live="polite">
              {error && !["invalidRange", "maxRange"].includes(error.key) ? <div className="glico-alert glico-alert--error" role="alert" data-testid="glico-error">{errorText}</div> : null}
              {notice ? <div className="glico-alert glico-alert--success" role="status">{t(`glicoAssistant.${notice}`)}</div> : null}
            </div>

            {(messages.length || shownReceipt) && !proposal ? (
              <ul className="glico-chips" aria-label={t("glicoAssistant.chips.title")}>
                {[...mainChips, ...(moreOpen ? [...actionChips, ...faqChips] : [])].map((chip) => (
                  <li key={chip.key}>
                    <button type="button" className="glico-chip glico-chip--row" onClick={chip.run} disabled={busy}>{chip.label}</button>
                  </li>
                ))}
                {hasMoreChips ? <li>
                  <button type="button" className="glico-chip glico-chip--row glico-chip--quiet" aria-expanded={moreOpen} onClick={() => setMoreOpen((open) => !open)}>
                    {t(moreOpen ? "glicoAssistant.chips.less" : "glicoAssistant.chips.more")}
                  </button>
                </li> : null}
              </ul>
            ) : null}

            <form className="glico__composer" onSubmit={submitMessage}>
              {collab ? (
                <div className="glico-mode">
                  <span className="glico-mode__label">
                    {collab.kind === "investigation_open"
                      ? t("glicoAssistant.investigation.openAction")
                      : collab.investigationId
                        ? t("glicoAssistant.collab.replyingTo", { id: collab.investigationId })
                        : t("glicoAssistant.collab.pickHint")}
                  </span>
                  <button type="button" className="react-button react-button--quiet react-button--compact" onClick={startDictation} disabled={busy}>
                    <MicIcon size={16} />
                    <span className="glico-mode__text">{dictating ? t("glicoAssistant.investigation.stopDictation") : t("glicoAssistant.investigation.dictate")}</span>
                  </button>
                  <button type="button" className="glico-icon-button glico-icon-button--small" onClick={() => setCollab(null)} aria-label={t("glicoAssistant.collab.cancel")} title={t("glicoAssistant.collab.cancel")}>
                    <CloseIcon size={16} />
                  </button>
                </div>
              ) : null}
              <GlicoMediaCapture
                hidden={isDoctor}
                capabilities={capabilities}
                enabled={hasPatientContext}
                processing={processing}
                onSubmit={submitMedia}
                onCancel={cancelMedia}
                onError={(key) => setError({ key })}
              />
              <div className="glico-composer__field">
                <label htmlFor="glico-message" className="react-visually-hidden">{t("glicoAssistant.messageLabel")}</label>
                <textarea
                  id="glico-message"
                  ref={composerRef}
                  className="glico-composer__input"
                  rows={1}
                  maxLength={maxChars}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={onComposerKeyDown}
                  placeholder={!hasPatientContext ? t("glicoAssistant.composerPlaceholderLocked") : collab ? t("glicoAssistant.collab.placeholder") : t(isDoctor ? "glicoAssistant.doctor.composerPlaceholder" : "glicoAssistant.composerPlaceholder")}
                  disabled={!hasPatientContext || busy}
                  aria-describedby="glico-composer-help"
                />
              </div>
              <span id="glico-composer-help" className="glico-composer__help">
                {draft.length > maxChars * 0.8 ? t("glicoAssistant.charCount", { count: draft.length, max: maxChars }) : ""}
              </span>
              <button type="submit" className="glico-send" aria-label={t("glicoAssistant.send")} title={t("glicoAssistant.send")} disabled={!hasPatientContext || busy || !draft.trim()}>
                {busy && !processing ? <span className="glico-spinner glico-spinner--light" aria-hidden="true" /> : <SendIcon />}
              </button>
            </form>
          </div>
        </section>
      ) : null}

      <div className="glico__notes"><GlicoNotes languageModel={Boolean(capabilities?.language_model)} /></div>
    </section>
  );
}

function session_panel_link(conversation) {
  const id = conversation?.context?.patient_id;
  return id ? `/patients/${id}` : null;
}
