import { useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

function pad(value) {
  return String(value).padStart(2, "0");
}

export function toLocalInput(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function initialFields(proposal) {
  const fields = proposal?.fields || {};
  const kind = proposal?.kind || "glucose_single";
  if (kind === "investigation_open") {
    return {
      title: fields.title || "",
      content: fields.content || "",
      associated_days: fields.associated_days || []
    };
  }
  if (kind === "investigation_message") {
    return {
      content: fields.content || ""
    };
  }
  return {
    glucose_mg_dl: fields.glucose_mg_dl ?? "",
    measured_at: toLocalInput(fields.measured_at),
    context_label: fields.context_label || "",
    notes: fields.notes || ""
  };
}

export default function GlicoProposalCard({ proposal, role, busy, onSave, onConfirm, onDiscard }) {
  const { t, i18n } = useTranslation();
  const uid = useId();
  const [values, setValues] = useState(() => initialFields(proposal));
  const baseline = useMemo(() => initialFields(proposal), [proposal]);

  useEffect(() => {
    setValues(baseline);
  }, [baseline]);

  const kind = proposal?.kind || "glucose_single";
  const editable = kind === "glucose_single" || kind === "investigation_open" || kind === "investigation_message";
  const dirty = editable && Object.keys(baseline).some((key) => String(values[key]) !== String(baseline[key]));
  const isPatient = role === "patient";
  const ready = proposal.state === "READY" && !dirty && !proposal.missing_fields?.length;
  const expires = proposal.expires_at
    ? new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit" }).format(new Date(proposal.expires_at))
    : null;

  const update = (key) => (event) => {
    if (key === "associated_days" && event.target.type === "checkbox") {
      const day = event.target.value;
      setValues((current) => ({
        ...current,
        associated_days: event.target.checked
          ? [...(current.associated_days || []), day]
          : (current.associated_days || []).filter((d) => d !== day)
      }));
    } else {
      setValues((current) => ({ ...current, [key]: event.target.value }));
    }
  };

  const number = Number(values.glucose_mg_dl);
  const valueInvalid = values.glucose_mg_dl === "" || !(number >= 20 && number <= 600);
  const dateInvalid = !values.measured_at;
  const titleInvalid = kind === "investigation_open" && !values.title.trim();
  const contentInvalid = (kind === "investigation_open" || kind === "investigation_message") && !values.content.trim();
  const invalid = (kind === "glucose_single" && (valueInvalid || dateInvalid))
    || (kind === "investigation_open" && (titleInvalid || contentInvalid))
    || (kind === "investigation_message" && contentInvalid);

  const save = (event) => {
    event.preventDefault();
    if (invalid) return;
    if (kind === "glucose_single") {
      onSave({
        glucose_mg_dl: number,
        measured_at: new Date(values.measured_at).toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        context_label: values.context_label || null,
        notes: values.notes || null
      });
    } else if (kind === "investigation_open") {
      onSave({
        title: values.title,
        content: values.content,
        associated_days: values.associated_days || []
      });
    } else if (kind === "investigation_message") {
      onSave({
        content: values.content
      });
    }
  };

  const field = (name) => `${uid}-${name}`;

  const titleKey = kind === "investigation_open" ? "glicoAssistant.investigation.openTitle"
    : kind === "investigation_message" ? "glicoAssistant.investigation.messageTitle"
    : "glicoAssistant.proposalTitle";
  const introKey = kind === "investigation_open" ? "glicoAssistant.investigation.openIntro"
    : kind === "investigation_message" ? "glicoAssistant.investigation.messageIntro"
    : "glicoAssistant.proposalIntro";

  return (
    <section className="glico-card" aria-labelledby={field("title")} data-testid="glico-proposal">
      <div className="glico-card__heading">
        <h2 id={field("title")}>{t(titleKey)}</h2>
        <span className="react-badge react-badge--pending">{t(`glicoAssistant.states.${proposal.state}`, { defaultValue: proposal.state })}</span>
      </div>
      <p>{t(introKey)}</p>
      {expires ? <p className="glico-hint">{t("glicoAssistant.proposalExpires", { time: expires })}</p> : null}

      {editable ? (
        <form onSubmit={save} className="glico-card__form" noValidate>
          {kind === "glucose_single" && (
            <>
              <label htmlFor={field("value")}>{t("glicoAssistant.valueLabel")}</label>
              <div className="glico-card__value">
                <input
                  id={field("value")}
                  className="react-field"
                  type="number"
                  inputMode="decimal"
                  min="20"
                  max="600"
                  step="0.1"
                  value={values.glucose_mg_dl}
                  onChange={update("glucose_mg_dl")}
                  disabled={busy}
                  aria-invalid={valueInvalid && values.glucose_mg_dl !== "" ? "true" : undefined}
                  aria-describedby={field("unit")}
                />
                <span id={field("unit")}>mg/dL</span>
              </div>
              <label htmlFor={field("at")}>{t("glicoAssistant.measuredAtLabel")}</label>
              <input id={field("at")} className="react-field" type="datetime-local" value={values.measured_at} onChange={update("measured_at")} disabled={busy} />
              <label htmlFor={field("ctx")}>{t("glicoAssistant.contextLabel")}</label>
              <input id={field("ctx")} className="react-field" type="text" maxLength={100} value={values.context_label} onChange={update("context_label")} disabled={busy} />
              <label htmlFor={field("notes")}>{t("glicoAssistant.notesLabel")}</label>
              <textarea id={field("notes")} className="react-field" rows={2} maxLength={500} value={values.notes} onChange={update("notes")} disabled={busy} />
            </>
          )}

          {kind === "investigation_open" && (
            <>
              <label htmlFor={field("title")}>{t("glicoAssistant.investigation.titleLabel")}</label>
              <input id={field("title")} className="react-field" type="text" maxLength={200} value={values.title} onChange={update("title")} disabled={busy} placeholder={t("glicoAssistant.investigation.placeholderTitle")} aria-invalid={titleInvalid ? "true" : undefined} />
              <label htmlFor={field("content")}>{t("glicoAssistant.investigation.contentLabel")}</label>
              <textarea id={field("content")} className="react-field" rows={3} maxLength={2000} value={values.content} onChange={update("content")} disabled={busy} placeholder={t("glicoAssistant.investigation.placeholderContent")} aria-invalid={contentInvalid ? "true" : undefined} />
              <label>{t("glicoAssistant.investigation.associatedDaysLabel")}</label>
              <div className="glico__associated-days">
                {proposal.associated_days?.length ? (
                  proposal.associated_days.map((day) => (
                    <label key={day} className="glico__day-checkbox">
                      <input type="checkbox" value={day} checked={values.associated_days?.includes(day)} onChange={update("associated_days")} disabled={busy} />
                      <span>{day}</span>
                    </label>
                  ))
                ) : (
                  <p className="glico-hint">{t("glicoAssistant.investigation.noDays")}</p>
                )}
              </div>
            </>
          )}

          {kind === "investigation_message" && (
            <>
              <label htmlFor={field("content")}>{t("glicoAssistant.investigation.contentLabel")}</label>
              <textarea id={field("content")} className="react-field" rows={3} maxLength={2000} value={values.content} onChange={update("content")} disabled={busy} placeholder={t("glicoAssistant.investigation.placeholderContent")} aria-invalid={contentInvalid ? "true" : undefined} />
            </>
          )}

          {proposal.missing_fields?.length ? <p className="glico-hint" role="note">{t("glicoAssistant.missingFields")}</p> : null}
          {proposal.missing_fields?.includes("measured_at") ? <p className="glico-hint" role="note">{t("glicoAssistant.missingMeasuredAtHint")}</p> : null}
          {dirty ? <p className="glico-hint" role="note">{t("glicoAssistant.unsavedEdits")}</p> : null}
          {!isPatient && kind === "glucose_single" ? <p className="glico-hint" role="note">{t("glicoAssistant.doctorCannotConfirm")}</p> : null}

          <div className="glico-card__actions">
            <button type="submit" className="react-button react-button--ghost" disabled={busy || !dirty || invalid}>
              {t("glicoAssistant.saveCorrection")}
            </button>
            <button type="button" className="react-button react-button--primary" onClick={onConfirm} disabled={busy || !ready || !isPatient}>
              {t("glicoAssistant.confirm")}
            </button>
            <button type="button" className="react-button react-button--quiet" onClick={onDiscard} disabled={busy}>
              {t("glicoAssistant.discard")}
            </button>
          </div>
        </form>
      ) : (
        <div className="glico-card__form">
          <p className="glico-hint">{t("glicoAssistant.readOnlyKind")}</p>
          <div className="glico-card__actions">
            <button type="button" className="react-button react-button--quiet" onClick={onDiscard} disabled={busy}>
              {t("glicoAssistant.discard")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
