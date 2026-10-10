import { useTranslation } from "react-i18next";

function formatOriginDate(value, locale) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

// `origin` comes from the backend: { indicator_id, date, analysis_run_id, is_current_classification }.
// The conversation keeps its historical origin even when a later analysis no longer flags that day.
export default function InvestigationOrigin({ investigation }) {
  const { t, i18n } = useTranslation();
  if (!investigation?.atypical_day_event_id) {
    return <p>{t("cscw.noAtypical")}</p>;
  }
  const origin = investigation.origin;
  if (!origin?.date) {
    return <p>{t("cscw.originAtypical")}</p>;
  }
  const date = formatOriginDate(origin.date, i18n.language);
  if (origin.is_current_classification === false) {
    return (
      <p className="react-origin react-origin--previous" data-testid="investigation-origin">
        <span className="react-badge react-badge--soft">{t("cscw.previousClassification")}</span>{" "}
        {t("cscw.originPreviousClassification", { date })}
      </p>
    );
  }
  return (
    <p className="react-origin" data-testid="investigation-origin">
      {t("cscw.originAtypicalDated", { date })}
    </p>
  );
}
