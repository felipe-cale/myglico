import { useState } from "react";
import { useTranslation } from "react-i18next";
import { createManualGlucoseRecord } from "../api";
import { ChevronDownIcon } from "./Icons";

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

export default function ManualGlucoseEntryForm({ patientId, onCreated, open = false, onToggle }) {
  const { t } = useTranslation();
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const hasOptionalDetails = Boolean(form.context || form.customContext || form.notes);
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
    <section id="new-reading" className="react-panel react-manual-entry" aria-labelledby="new-reading-title">
      <div className="react-manual-entry__header">
        <h2 id="new-reading-title">{t("manualEntry.title")}</h2>
        <button
          type="button"
          className="react-button react-button--ghost react-button--compact react-disclosure-toggle"
          aria-expanded={open}
          aria-controls="new-reading-body"
          onClick={onToggle}
        >
          <span>{open ? t("manualEntry.toggleClose") : t("manualEntry.toggle")}</span>
          <ChevronDownIcon />
        </button>
      </div>
      {open ? (
        <div id="new-reading-body" className="react-manual-entry__body">
          <p className="react-manual-entry__intro">{t("manualEntry.body")}</p>
          <form className="react-manual-entry-form" onSubmit={handleSubmit} noValidate>
            <div className="react-manual-entry-form__row">
              <label className="react-field">
                <span>{t("manualEntry.measuredAt")}</span>
                <input type="datetime-local" value={form.measuredAt} onChange={updateField("measuredAt")} required />
              </label>
              <label className="react-field">
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
            </div>
            <details className="react-disclosure react-manual-entry-form__more" open={hasOptionalDetails || undefined}>
              <summary>
                <span>{t("manualEntry.more")}</span>
                <ChevronDownIcon />
              </summary>
              <div className="react-manual-entry-form__optional">
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
                  <label className="react-field">
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
                <label className="react-field react-manual-entry-form__notes">
                  <span>{t("manualEntry.notes")}</span>
                  <textarea
                    rows={2}
                    placeholder={t("manualEntry.notesPlaceholder")}
                    value={form.notes}
                    onChange={updateField("notes")}
                  />
                </label>
              </div>
            </details>
            <div className="react-manual-entry-form__actions">
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
      ) : null}
    </section>
  );
}
