import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { fetchAtypicalDayPrompts, deferAtypicalDayPrompt } from "../api";
import { useAuth } from "../contexts/AuthContext";

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
  const [expandedPrompt, setExpandedPrompt] = useState(null);

  useEffect(() => {
    if (session?.patient?.id) {
      fetchAtypicalDayPrompts(session.patient.id)
        .then(data => {
          const items = data.prompts || data || [];
          setPrompts(items.filter((item) => item.status === "created"));
        })
        .catch(() => {});
    }
  }, [session]);

  useEffect(() => {
    const match = location.hash.match(/^#atypical-day-(.+)$/);
    if (!match) return;
    const indicatorId = decodeURIComponent(match[1]);
    const prompt = prompts.find((item) => item.indicator_ids?.includes(indicatorId) || item.indicator_id === indicatorId);
    if (!prompt) return;
    if (expandedPrompt !== prompt.batch_id) {
      setExpandedPrompt(prompt.batch_id);
      return;
    }
    requestAnimationFrame(() => document.getElementById(`atypical-day-${indicatorId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }, [location.hash, prompts, expandedPrompt]);

  const handleDefer = async (prompt) => {
    try {
      const indicatorIds = prompt.indicator_ids?.length ? prompt.indicator_ids : [prompt.indicator_id];
      await deferAtypicalDayPrompt(indicatorIds);
      setPrompts(prompts.filter(p => p.batch_id !== prompt.batch_id));
    } catch(e) {}
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
      <ul className="react-prompt__list">
        {prompts.map(p => (
          <li key={p.batch_id || p.indicator_id} className={`react-prompt__item${expandedPrompt === p.batch_id ? " is-expanded" : ""}`}>
            <button type="button" className="react-prompt__toggle" aria-expanded={expandedPrompt === p.batch_id} onClick={() => setExpandedPrompt(expandedPrompt === p.batch_id ? null : p.batch_id)}>
              <span>{promptText(p)}</span><span aria-hidden="true">{expandedPrompt === p.batch_id ? "−" : "+"}</span>
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
              <button type="button" className="react-button react-button--text" onClick={() => handleDefer(p)}>{t("cscw.defer")}</button>
            </>}
          </li>
        ))}
      </ul>
    </section>
  );
}
