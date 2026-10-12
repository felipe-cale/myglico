import { useState } from "react";
import { useTranslation } from "react-i18next";
import { createManualGlucoseRecord } from "../api";

const CONTEXT_OPTIONS = [
  "pre_breakfast",
  "post_breakfast",
  "pre_lunch",
  "post_lunch",
  "pre_supper",
  "post_supper",
  "pre_snack"
];
const CUSTOM_CONTEXT = "custom";

function currentLocalDateTime() {
  const now = new Date();
  now.setSeconds(0, 0);
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function emptyForm() {
  return { measuredAt: currentLocalDateTime(), glucose: "", context: "", customContext: "", notes: "" };
}

export default function ManualGlucoseEntryForm({ patientId, onCreated }) {
  const { t } = useTranslation();
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const updateField = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    setFeedback(null);

    const glucose = Number(form.glucose);
    if (!form.measuredAt) {
      setFeedback({ tone: "error", message: t("manualEntry.errors.measuredAtRequired") });
      return;
    }
    if (form.glucose === "" || !Number.isFinite(glucose) || glucose <= 0 || glucose > 1000) {
      setFeedback({ tone: "error", message: t("manualEntry.errors.glucoseRange") });
      return;
    }
    const contextLabel = (form.context === CUSTOM_CONTEXT ? form.customContext : form.context).trim();
    if (form.context === CUSTOM_CONTEXT && !contextLabel) {
      setFeedback({ tone: "error", message: t("manualEntry.errors.customContextRequired") });
      return;
    }

    setSubmitting(true);
    try {
      const result = await createManualGlucoseRecord(patientId, {
        measured_at: form.measuredAt,
        glucose_mg_dl: glucose,
        context_label: contextLabel || null,
        notes: form.notes.trim() || null
      });
      setForm(emptyForm());
      setFeedback({ tone: "success", message: t("manualEntry.success") });
      onCreated?.(result.glucose_record);
    } catch (reason) {
      setFeedback({ tone: "error", message: t("manualEntry.errors.saveFailed") });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section id="new-reading" className="react-panel react-panel--filter react-panel--manual-entry">
      <div className="react-filter-layout">
        <div className="react-filter-copy">
          <p className="react-eyebrow">{t("manualEntry.eyebrow")}</p>
          <h2>{t("manualEntry.title")}</h2>
          <p>{t("manualEntry.body")}</p>
        </div>
        <div className="react-filter-controls">
          <form className="react-filter-form react-manual-entry-form" onSubmit={handleSubmit} noValidate>
            <label>
              <span>{t("manualEntry.measuredAt")}</span>
              <input type="datetime-local" value={form.measuredAt} onChange={updateField("measuredAt")} required />
            </label>
            <label>
              <span>{t("manualEntry.glucose")}</span>
              <input
                type="number"
                inputMode="decimal"
                min="1"
                max="1000"
                step="any"
                placeholder={t("manualEntry.glucosePlaceholder")}
                value={form.glucose}
                onChange={updateField("glucose")}
                required
              />
            </label>
            <label className="react-select-field">
              <span>{t("manualEntry.context")}</span>
              <select value={form.context} onChange={updateField("context")}>
                <option value="">{t("manualEntry.contextNone")}</option>
                {CONTEXT_OPTIONS.map((code) => (
                  <option key={code} value={code}>
                    {t(`enums.context.${code}`)}
                  </option>
                ))}
                <option value={CUSTOM_CONTEXT}>{t("manualEntry.contextCustom")}</option>
              </select>
            </label>
            {form.context === CUSTOM_CONTEXT ? (
              <label>
                <span>{t("manualEntry.customContext")}</span>
                <input
                  type="text"
                  maxLength={80}
                  placeholder={t("manualEntry.customContextPlaceholder")}
                  value={form.customContext}
                  onChange={updateField("customContext")}
                />
              </label>
            ) : null}
            <label className="react-manual-entry-form__notes">
              <span>{t("manualEntry.notes")}</span>
              <textarea
                rows={2}
                placeholder={t("manualEntry.notesPlaceholder")}
                value={form.notes}
                onChange={updateField("notes")}
              />
            </label>
            <div className="react-filter-actions react-manual-entry-form__actions">
              <button type="submit" className="react-button" disabled={submitting}>
                {submitting ? t("manualEntry.submitting") : t("manualEntry.submit")}
              </button>
              {feedback ? (
                <small
                  className={`react-manual-entry-form__feedback is-${feedback.tone}`}
                  role={feedback.tone === "error" ? "alert" : "status"}
                >
                  {feedback.message}
                </small>
              ) : null}
            </div>
          </form>
        </div>
      </div>
    </section>
  );
}
