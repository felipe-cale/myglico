import { useTranslation } from "react-i18next";

function formatOriginDate(value, locale) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

// `origin` comes from the backend: { indicator_id, date, analysis_run_id, is_current_classification }.
// The conversation keeps its historical origin even when a later analysis no longer flags that day.
export default function InvestigationOrigin({ investigation, variant = "line" }) {
  const { t, i18n } = useTranslation();
  const chip = variant === "chip";
  const simpleClass = chip ? "react-badge react-badge--compact react-origin react-origin--chip" : "react-origin";

  const origins = investigation?.origins?.length ? investigation.origins : investigation?.origin ? [investigation.origin] : [];
  if (!origins.length && !investigation?.atypical_day_event_id) {
    return chip
      ? <span className={`${simpleClass} react-badge--soft`}>{t("cscw.noAtypical")}</span>
      : <p className="react-origin react-origin--none">{t("cscw.noAtypical")}</p>;
  }
  if (!origins.length) {
    return chip
      ? <span className={`${simpleClass} react-badge--blue`}>{t("cscw.originAtypical")}</span>
      : <p className="react-origin">{t("cscw.originAtypical")}</p>;
  }
  const content = origins.map((origin) => {
    if (!origin?.date) return t("cscw.originAtypical");
    const date = formatOriginDate(origin.date, i18n.language);
    return origin.is_current_classification === false
      ? origins.length === 1
        ? t("cscw.originPreviousClassification", { date })
        : t("cscw.originPreviousShort", { date })
      : t("cscw.originAtypicalDated", { date });
  });
  return chip ? (
    <span className={`${simpleClass} react-badge--blue`} data-testid="investigation-origin">
      {content.join(" · ")}
    </span>
  ) : (
    <p className="react-origin" data-testid="investigation-origin">{content.join(" · ")}</p>
  );
}
