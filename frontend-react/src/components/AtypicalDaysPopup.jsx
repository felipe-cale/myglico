import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { fetchAtypicalDays } from "../api";
import { useAuth } from "../contexts/AuthContext";
import StateBlock from "./StateBlock";
import Pagination from "./Pagination";
import CloseIcon from "./CloseIcon";
import useFocusTrap from "../hooks/useFocusTrap";
import useBodyScrollLock from "../hooks/useBodyScrollLock";
import { ChevronDownIcon } from "./Icons";

function formatDay(value, locale) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

// Short factual line for a day: the API reason when it has one, otherwise the day's own figures.
function dayFacts(day, t, locale) {
  if (day.reason_summary) return day.reason_summary;
  const parts = [];
  if (day.avg_glucose != null) {
    parts.push(t("cscw.popupDayAvg", { value: new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(day.avg_glucose) }));
  }
  if (day.low_events_count) parts.push(t("cscw.popupDayLow", { count: day.low_events_count }));
  if (day.high_events_count) parts.push(t("cscw.popupDayHigh", { count: day.high_events_count }));
  return parts.join(" · ");
}

export default function AtypicalDaysPopup({ patientId, appliedDates = [], activeStart = "", activeEnd = "", onApplyDates, onClearDays, renderTrigger }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { session } = useAuth();
  const isPatient = Boolean(session?.patient?.id);
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, pages: 1 });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [status, setStatus] = useState("idle");
  const [selectedDates, setSelectedDates] = useState(() => new Set(appliedDates));
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [rangeFormOpen, setRangeFormOpen] = useState(false);
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
      params.page = page;
      params.page_size = pageSize;
      const data = await fetchAtypicalDays(patientId, params);
      setDays(data?.days || []);
      if (data?.pagination) {
        setPagination(data.pagination);
        if (data.pagination.page !== page) setPage(data.pagination.page);
      }
      setStatus("ready");
    } catch (error) {
      setDays([]);
      setStatus("error");
    }
  }, [patientId, rangeStart, rangeEnd, invalidRange, page, pageSize]);

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
    setPage(1);
    setRangeFormOpen(false);
    setOpen(true);
  };

  const hasRange = Boolean(rangeStart || rangeEnd);
  const isActivePeriod = hasRange && rangeStart === (activeStart || "") && rangeEnd === (activeEnd || "");
  const scopeText = !hasRange
    ? t("cscw.popupScopeAll", { count: pagination.total })
    : t("cscw.popupScopeRange", { count: pagination.total, start: formatDay(rangeStart, i18n.language) || "…", end: formatDay(rangeEnd, i18n.language) || "…" });
  const canClear = selectedDates.size > 0 || appliedDates.length > 0;

  useFocusTrap(open, dialogRef, { initialFocusRef: headingRef, onEscape: close });
  useBodyScrollLock(open);

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

      {open && createPortal(
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
            aria-describedby={isPatient ? "atypical-days-explain" : undefined}
            ref={dialogRef}
          >
            <div className="react-dialog__header">
              <div>
                <h3 id="atypical-days-title" ref={headingRef} tabIndex={-1}>{t("cscw.popupTitle")}</h3>
                {isPatient ? <p id="atypical-days-explain">{t("cscw.atypicalExplainPatient")}</p> : null}
              </div>
              <button type="button" className="react-dialog__close" onClick={close} aria-label={t("cscw.popupCloseAria")}>
                <CloseIcon />
              </button>
            </div>

            <div className="react-dialog__body">
              <div className="react-atypical-scope">
                {status === "ready" && <p data-testid="atypical-scope">{scopeText}</p>}
                <div className="react-atypical-scope__actions">
                  <button
                    type="button"
                    className="react-button react-button--text react-disclosure-toggle"
                    aria-expanded={rangeFormOpen}
                    aria-controls="atypical-range-form"
                    onClick={() => setRangeFormOpen((current) => !current)}
                  >
                    <span>{t("patientDetail.filter.toggle")}</span>
                    <ChevronDownIcon />
                  </button>
                  {hasRange && (
                    <button type="button" className="react-button react-button--text" onClick={() => { setRangeStart(""); setRangeEnd(""); setPage(1); }}>
                      {t("cscw.popupShowAll")}
                    </button>
                  )}
                  {!isActivePeriod && activeStart && activeEnd && (
                    <button type="button" className="react-button react-button--text" onClick={() => { setRangeStart(activeStart); setRangeEnd(activeEnd); setPage(1); }}>
                      {t("cscw.popupUseActive")}
                    </button>
                  )}
                </div>
                {!isActivePeriod ? <small>{t("cscw.popupOutsideHint")}</small> : null}
              </div>

              {rangeFormOpen ? (
                <form
                  id="atypical-range-form"
                  className="react-atypical-range"
                  onSubmit={(event) => {
                    event.preventDefault();
                    loadData();
                  }}
                >
                  <label className="react-field">
                    <span>{t("patientDetail.filter.startDate")}</span>
                    <input type="date" value={rangeStart} onChange={(event) => { setRangeStart(event.target.value); setPage(1); }} />
                  </label>
                  <label className="react-field">
                    <span>{t("patientDetail.filter.endDate")}</span>
                    <input type="date" value={rangeEnd} onChange={(event) => { setRangeEnd(event.target.value); setPage(1); }} />
                  </label>
                  {invalidRange && <small className="react-form-message is-error" role="alert">{t("patientDetail.filter.invalidRange")}</small>}
                </form>
              ) : null}

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
                <>
                  <ul className="react-atypical-list">
                    {days.map((d) => {
                      const facts = dayFacts(d, t, i18n.language);
                      return (
                        <li key={d.indicator_id || d.date} className={`react-atypical-item${selectedDates.has(d.date) ? " is-selected" : ""}`}>
                          <label className="react-atypical-item__select">
                            <input type="checkbox" checked={selectedDates.has(d.date)} onChange={() => handleToggle(d.date)} />
                            <span>
                              <strong>{formatDay(d.date, i18n.language)}</strong>
                              {facts ? <small>{facts}</small> : null}
                              {d.has_investigation && <small>{t("cscw.hasInvestigation")}</small>}
                            </span>
                          </label>
                          <div className="react-atypical-item__actions">
                            <button type="button" className="react-button react-button--text" onClick={() => handleViewInDetail(d.date)}>
                              {t("cscw.viewInDetail")}
                            </button>
                            <button type="button" className="react-button react-button--text" onClick={() => handleOpenInv(d.indicator_id)}>
                              {t(isPatient ? "cscw.popupAskPatient" : "cscw.popupAskDoctor")}
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                  <Pagination
                    page={pagination.page}
                    pages={pagination.pages}
                    count={pagination.total}
                    pageSize={pageSize}
                    onPageChange={setPage}
                    onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
                  />
                </>
              )}

              <div className="react-actions react-dialog__actions">
                <button
                  type="button"
                  onClick={handleApply}
                  disabled={selectedDates.size === 0}
                  aria-describedby={selectedDates.size === 0 ? "atypical-apply-hint" : undefined}
                  className="react-button"
                >
                  {t("cscw.popupApply")}
                </button>
                <button type="button" onClick={handleClear} className="react-button react-button--ghost" disabled={!canClear}>
                  {t("cscw.popupClearDays")}
                </button>
                {selectedDates.size === 0 ? (
                  <small id="atypical-apply-hint" className="react-action-hint">{t("cscw.popupApplyHint")}</small>
                ) : null}
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
