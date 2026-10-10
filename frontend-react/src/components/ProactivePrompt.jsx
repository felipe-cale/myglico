import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
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
  const [prompts, setPrompts] = useState([]);

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

  const handleDefer = async (prompt) => {
    try {
      const indicatorIds = prompt.indicator_ids?.length ? prompt.indicator_ids : [prompt.indicator_id];
      await deferAtypicalDayPrompt(indicatorIds);
      setPrompts(prompts.filter(p => p.batch_id !== prompt.batch_id));
    } catch(e) {}
  };

  const handleViewDay = (prompt) => {
    const dates = prompt.dates?.length ? prompt.dates : [prompt.date];
    const params = new URLSearchParams({ dates: [...dates].sort().join(",") });
    navigate(`/patients/${session.patient.id}?${params.toString()}`);
  };

  const promptText = (prompt) => {
    const dates = prompt.dates?.length ? [...prompt.dates].sort() : [prompt.date];
    if (dates.length > 1) {
      return t("cscw.proactivePromptBatch", {
        count: dates.length,
        first: formatPromptDate(dates[0], i18n.language),
        last: formatPromptDate(dates[dates.length - 1], i18n.language)
      });
    }
    return t("cscw.proactivePromptDated", { date: formatPromptDate(dates[0], i18n.language) });
  };

  const handleOpenInvestigation = (indicatorId) => {
    navigate(`/dashboard?atypical_day_event_id=${encodeURIComponent(indicatorId)}#investigations`);
  };

  if (!session?.patient?.id || !prompts || prompts.length === 0) return null;

  return (
    <div role="region" aria-label={t("cscw.promptRegion")} style={{ background: '#fff3cd', border: '1px solid #ffeeba', padding: '1rem', borderRadius: '4px', marginBottom: '1rem' }}>
      {prompts.map(p => (
        <div key={p.indicator_id} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <p>{promptText(p)}</p>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button className="react-button" style={{ background: '#ffc107', border: 'none' }} onClick={() => handleViewDay(p)}>{p.dates?.length > 1 ? t("cscw.viewDays") : t("cscw.viewDay")}</button>
            <button className="react-button" style={{ background: '#005fcc', color: '#fff', border: 'none' }} onClick={() => handleOpenInvestigation(p.indicator_id)}>{t("cscw.open")}</button>
            <button className="react-button" style={{ background: 'transparent', border: '1px solid #ccc' }} onClick={() => handleDefer(p)}>{t("cscw.defer")}</button>
          </div>
        </div>
      ))}
    </div>
  );
}
