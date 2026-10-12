import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { fetchAtypicalDays } from "../api";
import { useAuth } from "../contexts/AuthContext";
import StateBlock from "./StateBlock";

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

function formatDay(value, locale) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

export default function AtypicalDaysPopup({ patientId, appliedDates = [], activeStart = "", activeEnd = "", onApplyDates, onClearDays, renderTrigger }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { session } = useAuth();
  const isPatient = Boolean(session?.patient?.id);
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState([]);
  const [status, setStatus] = useState("idle");
  const [selectedDates, setSelectedDates] = useState(() => new Set(appliedDates));
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const triggerRef = useRef(null);
  const dialogRef = useRef(null);
  const headingRef = useRef(null);
  const invalidRange = Boolean(rangeStart && rangeEnd && rangeStart > rangeEnd);

  const loadData = useCallback(async () => {
    if (invalidRange) return;
    setStatus("loading");
    try {
      const params = {};
      if (rangeStart) params.start_date = rangeStart;
      if (rangeEnd) params.end_date = rangeEnd;
      const data = await fetchAtypicalDays(patientId, params);
      setDays(data?.days || []);
      setStatus("ready");
    } catch (error) {
      setDays([]);
      setStatus("error");
    }
  }, [patientId, rangeStart, rangeEnd, invalidRange]);

  useEffect(() => {
    if (open) loadData();
  }, [open, loadData]);

  const close = useCallback(() => {
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  const openPopup = () => {
    setSelectedDates(new Set(appliedDates));
    setRangeStart(activeStart || "");
    setRangeEnd(activeEnd || "");
    setOpen(true);
  };

  const hasRange = Boolean(rangeStart || rangeEnd);
  const isActivePeriod = hasRange && rangeStart === (activeStart || "") && rangeEnd === (activeEnd || "");
  const scopeText = !hasRange
    ? t("cscw.popupScopeAll", { count: days.length })
    : isActivePeriod
      ? t("cscw.popupScopeActive", { count: days.length, start: formatDay(rangeStart, i18n.language), end: formatDay(rangeEnd, i18n.language) })
      : t("cscw.popupScopeCustom", { count: days.length, start: formatDay(rangeStart, i18n.language) || "…", end: formatDay(rangeEnd, i18n.language) || "…" });

  useEffect(() => {
    if (!open) return undefined;
    headingRef.current?.focus();
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === headingRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, close]);

  const handleToggle = (date) => {
    const next = new Set(selectedDates);
    if (next.has(date)) next.delete(date);
    else next.add(date);
    setSelectedDates(next);
  };

  const handleApply = () => {
    if (selectedDates.size === 0) return;
    onApplyDates(Array.from(selectedDates).sort());
    close();
  };

  const handleClear = () => {
    setSelectedDates(new Set());
    onClearDays();
    close();
  };

  const handleViewInDetail = (date) => {
    onApplyDates([date]);
    close();
  };

  const handleOpenInv = (indicatorId) => {
    const params = new URLSearchParams({ atypical_day_event_id: indicatorId, patient_id: patientId });
    navigate(`/dashboard?${params.toString()}#investigations`);
  };

  const sortedSelection = Array.from(selectedDates).sort();

  return (
    <>
      {renderTrigger ? renderTrigger(openPopup, triggerRef) : (
        <button type="button" ref={triggerRef} onClick={openPopup} className="react-button react-button--ghost" aria-haspopup="dialog">
          {t("cscw.popupButton")}
        </button>
      )}

      {open && (
        <div
          className="react-dialog-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <div
            className="react-dialog react-dialog--atypical"
            role="dialog"
            aria-modal="true"
            aria-labelledby="atypical-days-title"
            ref={dialogRef}
          >
            <div className="react-dialog__header">
              <div>
                <p className="react-eyebrow">{t("cscw.promptEyebrow")}</p>
                <h3 id="atypical-days-title" ref={headingRef} tabIndex={-1}>{t("cscw.popupTitle")}</h3>
              </div>
              <button type="button" className="react-dialog__close" onClick={close} aria-label={t("cscw.popupCloseAria")}>
                ×
              </button>
            </div>

            <div className="react-dialog__body">
              <form
                className="react-atypical-range"
                onSubmit={(event) => {
                  event.preventDefault();
                  loadData();
                }}
              >
                <label className="react-field">
                  <span>{t("patientDetail.filter.startDate")}</span>
                  <input type="date" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} />
                </label>
                <label className="react-field">
                  <span>{t("patientDetail.filter.endDate")}</span>
                  <input type="date" value={rangeEnd} onChange={(event) => setRangeEnd(event.target.value)} />
                </label>
                {invalidRange && <small className="react-form-message is-error" role="alert">{t("patientDetail.filter.invalidRange")}</small>}
              </form>

              <div className="react-atypical-scope">
                {status === "ready" && <p data-testid="atypical-scope">{scopeText}</p>}
                <div className="react-actions">
                  {hasRange && (
                    <button type="button" className="react-chip" onClick={() => { setRangeStart(""); setRangeEnd(""); }}>
                      {t("cscw.popupShowAll")}
                    </button>
                  )}
                  {!isActivePeriod && activeStart && activeEnd && (
                    <button type="button" className="react-chip" onClick={() => { setRangeStart(activeStart); setRangeEnd(activeEnd); }}>
                      {t("cscw.popupUseActive")}
                    </button>
                  )}
                </div>
                {!isActivePeriod ? <small>{t("cscw.popupOutsideHint")}</small> : null}
              </div>

              {sortedSelection.length > 0 && (
                <div className="react-chip-row" aria-label={t("cscw.selectedDaysLabel")}>
                  {sortedSelection.map((date) => (
                    <button
                      type="button"
                      key={date}
                      className="react-chip is-active react-chip--removable"
                      onClick={() => handleToggle(date)}
                      aria-label={t("cscw.removeDayAria", { date: formatDay(date, i18n.language) })}
                    >
                      {formatDay(date, i18n.language)} ×
                    </button>
                  ))}
                </div>
              )}

              {status === "loading" && (
                <div role="status">
                  <StateBlock title={t("cscw.popupLoading")} tone="info" />
                </div>
              )}
              {status === "error" && (
                <div role="alert" className="react-atypical-error">
                  <StateBlock title={t("cscw.popupError")} tone="danger">
                    <button type="button" className="react-button react-button--ghost react-button--compact" onClick={loadData}>
                      {t("cscw.retry")}
                    </button>
                  </StateBlock>
                </div>
              )}
              {status === "ready" && days.length === 0 && (
                <StateBlock title={t("cscw.popupEmpty")} description={t("cscw.popupEmptyHint")} />
              )}
              {status === "ready" && days.length > 0 && (
                <ul className="react-atypical-list">
                  {days.map((d) => (
                    <li key={d.indicator_id || d.date} className="react-atypical-item">
                      <label className="react-atypical-item__select">
                        <input type="checkbox" checked={selectedDates.has(d.date)} onChange={() => handleToggle(d.date)} />
                        <span>
                          <strong>{formatDay(d.date, i18n.language)}</strong>
                          {d.reason_summary && <small>{d.reason_summary}</small>}
                          {d.has_investigation && <small>{t("cscw.hasInvestigation")}</small>}
                        </span>
                      </label>
                      <div className="react-atypical-item__actions">
                        <button type="button" className="react-button react-button--ghost" onClick={() => handleViewInDetail(d.date)}>
                          {t("cscw.viewInDetail")}
                        </button>
                        <button type="button" className="react-button" onClick={() => handleOpenInv(d.indicator_id)}>
                          {t(isPatient ? "cscw.popupAskPatient" : "cscw.popupAskDoctor")}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              <div className="react-actions react-dialog__actions">
                <button type="button" onClick={handleApply} disabled={selectedDates.size === 0} className="react-button">
                  {t("cscw.popupApply")}
                </button>
                <button type="button" onClick={handleClear} className="react-button react-button--ghost">
                  {t("cscw.popupClearDays")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
