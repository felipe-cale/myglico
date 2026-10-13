import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { fetchAtypicalDayPrompts, deferAtypicalDayPrompt } from "../api";
import { useAuth } from "../contexts/AuthContext";
import Pagination from "./Pagination";
import { ChevronDownIcon } from "./Icons";
import { preferredScrollBehavior } from "../hooks/usePrefersReducedMotion";

function formatPromptDate(value, locale) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

export default function ProactivePrompt() {
  const { t, i18n } = useTranslation();
  const { session } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [prompts, setPrompts] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, pages: 1 });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [refresh, setRefresh] = useState(0);
  const [expandedPrompt, setExpandedPrompt] = useState(null);
  const targetPromptLookupRef = useRef("");
  const [loadingPage, setLoadingPage] = useState(false);
  const [deferErrorId, setDeferErrorId] = useState(null);
  const [deferringId, setDeferringId] = useState(null);

  useEffect(() => {
    if (!session?.patient?.id) return undefined;
    let active = true;
    setLoadingPage(true);
    fetchAtypicalDayPrompts(session.patient.id, { page, page_size: pageSize })
      .then(data => {
        if (!active) return;
        const items = data.prompts || data || [];
        setPrompts(items.filter((item) => item.status === "created"));
        if (data.pagination) {
          setPagination(data.pagination);
          if (data.pagination.page !== page) setPage(data.pagination.page);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoadingPage(false);
      });
    return () => {
      active = false;
    };
  }, [session?.patient?.id, page, pageSize, refresh]);

  useEffect(() => {
    const match = location.hash.match(/^#atypical-day-(.+)$/);
    if (!match) return;
    const indicatorId = decodeURIComponent(match[1]);
    const prompt = prompts.find((item) => item.indicator_ids?.includes(indicatorId) || item.indicator_id === indicatorId);
    if (!prompt) {
      if (targetPromptLookupRef.current !== indicatorId && session?.patient?.id) {
        targetPromptLookupRef.current = indicatorId;
        fetchAtypicalDayPrompts(session.patient.id, { indicator_id: indicatorId, page_size: pageSize })
          .then((data) => {
            if (data.pagination?.page) setPage(data.pagination.page);
          })
          .catch(() => {});
      }
      return;
    }
    targetPromptLookupRef.current = "";
    if (expandedPrompt !== prompt.batch_id) {
      setExpandedPrompt(prompt.batch_id);
      return;
    }
    requestAnimationFrame(() => document.getElementById(`atypical-day-${indicatorId}`)?.scrollIntoView({ behavior: preferredScrollBehavior(), block: "center" }));
  }, [location.hash, prompts, expandedPrompt, session?.patient?.id]);

  const handleDefer = async (prompt) => {
    setDeferErrorId(null);
    setDeferringId(prompt.batch_id);
    try {
      const indicatorIds = prompt.indicator_ids?.length ? prompt.indicator_ids : [prompt.indicator_id];
      await deferAtypicalDayPrompt(indicatorIds);
      setPrompts((current) => current.filter(p => p.batch_id !== prompt.batch_id));
      setRefresh((current) => current + 1);
    } catch {
      setDeferErrorId(prompt.batch_id);
    } finally {
      setDeferringId(null);
    }
  };

  const promptText = (prompt) => {
    const dates = prompt.dates?.length ? [...prompt.dates].sort() : [prompt.date];
    if (dates.length > 1) {
      return t("cscw.proactivePromptBatchPatient", {
        count: dates.length,
        first: formatPromptDate(dates[0], i18n.language),
        last: formatPromptDate(dates[dates.length - 1], i18n.language)
      });
    }
    return t("cscw.proactivePromptDatedPatient", { date: formatPromptDate(dates[0], i18n.language) });
  };

  const handleOpenInvestigation = (indicatorId) => {
    const params = new URLSearchParams({ atypical_day_event_id: indicatorId });
    navigate(`/dashboard?${params.toString()}#investigations`);
  };

  if (!session?.patient?.id || !prompts || prompts.length === 0) return null;

  return (
    <section id="atypical-days-prompts" role="region" aria-label={t("cscw.promptRegion")} className="react-panel react-prompt">
      <div className="react-panel__header">
        <div className="react-panel__header-copy">
          <p className="react-eyebrow">{t("cscw.promptEyebrow")}</p>
          <h2>{t("cscw.promptTitle")}</h2>
        </div>
      </div>
      <ul className="react-prompt__list" aria-busy={loadingPage}>
        {prompts.map(p => (
          <li key={p.batch_id || p.indicator_id} className={`react-prompt__item${expandedPrompt === p.batch_id ? " is-expanded" : ""}`}>
            <button type="button" className="react-prompt__toggle" aria-expanded={expandedPrompt === p.batch_id} onClick={() => setExpandedPrompt(expandedPrompt === p.batch_id ? null : p.batch_id)}>
              <span>{promptText(p)}</span><span className="react-prompt__chevron"><ChevronDownIcon /></span>
            </button>
            {expandedPrompt === p.batch_id && <>
              <ul className="react-prompt__days">
                {(p.dates || [p.date]).map((date, index) => (
                  <li key={date} id={`atypical-day-${p.indicator_ids?.[index] || p.indicator_id}`}>
                    <strong>{formatPromptDate(date, i18n.language)}</strong>
                    <div className="react-actions">
                      <button type="button" className="react-button react-button--ghost" onClick={() => navigate(`/patients/${session.patient.id}?dates=${encodeURIComponent(date)}`)}>{t("cscw.viewInDetail")}</button>
                      <button type="button" className="react-button" onClick={() => handleOpenInvestigation(p.indicator_ids?.[index] || p.indicator_id)}>{t("cscw.openPatient")}</button>
                    </div>
                  </li>
                ))}
              </ul>
              <button type="button" className="react-button react-button--text" onClick={() => handleDefer(p)} disabled={deferringId === p.batch_id}>{t("cscw.defer")}</button>
              {deferErrorId === p.batch_id ? (
                <p className="react-form-message is-error" role="alert">{t("cscw.deferFailed")}</p>
              ) : null}
            </>}
          </li>
        ))}
      </ul>
      <p className="react-list-refresh" aria-live="polite">{loadingPage ? t("common.updating") : ""}</p>
      <div className="react-panel__footer">
        <Pagination
          page={pagination.page}
          pages={pagination.pages}
          count={pagination.total}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
        />
      </div>
    </section>
  );
}
