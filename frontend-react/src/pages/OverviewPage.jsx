import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fetchDashboardSummary, fetchPatients } from "../api";
import Pagination from "../components/Pagination";
import StateBlock from "../components/StateBlock";
import { useAuth } from "../contexts/AuthContext";
import DoctorLinksManager, { PendingLinksPanel } from "../components/DoctorLinksManager";
import InvestigationsList from "../components/InvestigationsList";
import ProactivePrompt from "../components/ProactivePrompt";
import CloseIcon from "../components/CloseIcon";
import useFocusTrap from "../hooks/useFocusTrap";
import useMediaQuery from "../hooks/useMediaQuery";
import { ArrowRightIcon, CheckIcon, CopyIcon, HelpIcon } from "../components/Icons";

function formatNumber(value, suffix = "", locale = "pt-BR") {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value) + suffix;
}

function getPatientSignal(patient, t) {
  const code =
    patient.signal_code ||
    (patient.pct_hyper >= 65 || patient.avg_glucose >= 185
      ? "attention"
      : patient.pct_hypo >= 10
        ? "oscillation"
        : "stable");
  const tone = code === "attention" ? "warning" : code === "oscillation" ? "alert" : "stable";
  return { label: t(`signal.${code}`), shortLabel: t(`signal.short.${code}`), tone };
}

function FilterHelpDialog({ signal, open, onClose }) {
  const { t } = useTranslation();
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const content = t(`overview.profileHelp.${signal}`, { returnObjects: true, defaultValue: t("overview.profileHelp.all", { returnObjects: true }) });

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handlePointerDown = (event) => {
      if (!dialogRef.current?.contains(event.target)) {
        onClose();
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
    };
  }, [onClose, open]);

  useFocusTrap(open, dialogRef, { initialFocusRef: closeRef, onEscape: onClose });

  if (!open) {
    return null;
  }

  return (
    <div className="react-dialog-backdrop" role="presentation">
      <div
        className="react-dialog react-dialog--profile-help"
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-help-title"
        ref={dialogRef}
      >
        <div className="react-dialog__header">
          <div>
            <p className="react-eyebrow">{t("overview.profileHelp.eyebrow")}</p>
            <h3 id="profile-help-title">{content.title}</h3>
          </div>
          <button type="button" className="react-dialog__close" onClick={onClose} aria-label={t("overview.profileHelp.closeAriaLabel")} ref={closeRef}>
            <CloseIcon />
          </button>
        </div>
        <div className="react-dialog__body">
          <p>{content.intro}</p>
          <div className="react-dialog__sections">
            {content.sections.map((section) => (
              <section key={section.title} className="react-dialog__section">
                <h4>{section.title}</h4>
                <p>{section.body}</p>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function DoctorHome() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [patients, setPatients] = useState(null);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [patientsError, setPatientsError] = useState(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [copiedPatientId, setCopiedPatientId] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const currentPage = Number(searchParams.get("page") || "1");
  const requestedPageSize = Number(searchParams.get("page_size") || "10");
  const currentPageSize = [10, 25, 50].includes(requestedPageSize) ? requestedPageSize : 10;
  const currentQuery = searchParams.get("q") || "";
  const currentSignal = searchParams.get("signal") || "all";
  const [searchValue, setSearchValue] = useState(currentQuery);
  const deferredSearch = useDeferredValue(searchValue);

  useEffect(() => {
    setSearchValue(currentQuery);
  }, [currentQuery]);

  useEffect(() => {
    const nextQuery = deferredSearch.trim();
    if (nextQuery === currentQuery) {
      return;
    }
    startTransition(() => {
      const next = new URLSearchParams(searchParams);
      if (nextQuery) {
        next.set("q", nextQuery);
      } else {
        next.delete("q");
      }
      next.set("page", "1");
      setSearchParams(next);
    });
  }, [currentQuery, deferredSearch, searchParams, setSearchParams]);

  useEffect(() => {
    let active = true;
    setLoadingPatients(true);
    setPatientsError(null);
    fetchPatients({ page: currentPage, pageSize: currentPageSize, query: currentQuery, signal: currentSignal })
      .then((data) => {
        if (active) {
          setPatients(data);
        }
      })
      .catch((error) => {
        if (active) {
          setPatientsError(error);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingPatients(false);
        }
      });
    return () => {
      active = false;
    };
  }, [currentPage, currentPageSize, currentQuery, currentSignal, reloadToken]);

  function handlePageChange(page) {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(page));
    setSearchParams(next);
  }

  function handlePageSizeChange(pageSize) {
    const next = new URLSearchParams(searchParams);
    next.set("page_size", String(pageSize));
    next.set("page", "1");
    setSearchParams(next);
  }

  function handleSignalChange(signal) {
    const next = new URLSearchParams(searchParams);
    if (signal === "all") {
      next.delete("signal");
    } else {
      next.set("signal", signal);
    }
    next.set("page", "1");
    setSearchParams(next);
  }

  async function handleCopyShortId(patientId, shortId) {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(shortId);
      } else {
        const helper = document.createElement("textarea");
        helper.value = shortId;
        helper.setAttribute("readonly", "");
        helper.style.position = "absolute";
        helper.style.left = "-9999px";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        document.body.removeChild(helper);
      }
      setCopiedPatientId(patientId);
      window.setTimeout(() => {
        setCopiedPatientId((current) => (current === patientId ? "" : current));
      }, 1800);
    } catch (error) {
      console.error("Could not copy the patient code.", error);
    }
  }

  const visiblePatients = useMemo(() => patients?.patients || [], [patients]);

  const signalFilters = [
    { value: "all", label: t("common.all") },
    { value: "stable", label: t("signal.stable") },
    { value: "attention", label: t("signal.attention") },
    { value: "oscillation", label: t("signal.oscillation") }
  ];

  const compactList = useMediaQuery("(max-width: 899px)");

  const copyButton = (patient) => {
    const copied = copiedPatientId === patient.id;
    return (
      <button
        type="button"
        className={`react-icon-button react-copy-button${copied ? " is-copied" : ""}`}
        aria-label={t("overview.patients.copyAriaLabel", { code: patient.short_id })}
        title={copied ? t("overview.patients.copied") : t("overview.patients.copy")}
        onClick={() => handleCopyShortId(patient.id, patient.short_id)}
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
    );
  };

  const openPanelLink = (patient) => (
    <Link
      to={`/patients/${patient.id}`}
      className="react-row-link"
      aria-label={t("overview.patients.openPanelAria", { name: patient.display_name })}
    >
      <span>{t("overview.patients.openPanelShort")}</span>
      <ArrowRightIcon />
    </Link>
  );

  const avgLabel = (patient) => (patient.avg_glucose != null ? formatNumber(patient.avg_glucose, "", i18n.language) : "-");
  const copiedPatient = visiblePatients.find((patient) => patient.id === copiedPatientId);

  return (
    <div className="react-page react-page--doctor-home">
      <header className="react-page-header">
        <h1>{t("doctorHome.title")}</h1>
        <p>{t("doctorHome.body")}</p>
      </header>

      <div className="react-doctor-home">
        <div className="react-doctor-home__rail">
          <PendingLinksPanel onChange={() => setReloadToken((current) => current + 1)} />
          <InvestigationsList />
        </div>

        <section className="react-panel react-doctor-home__patients" aria-labelledby="patients-title">
          <div className="react-panel__header react-panel__header--patients">
            <div className="react-panel__header-copy">
              <p className="react-eyebrow">{t("overview.patients.eyebrow")}</p>
              <h2 id="patients-title">{t("overview.patients.title")}</h2>
              <p>{t("overview.patients.body")}</p>
            </div>
            <div className="react-patient-toolbar">
              <label className="react-select-field react-patient-toolbar__filter">
                <span>{t("overview.patients.filterLabel")}</span>
                <select value={currentSignal} onChange={(event) => handleSignalChange(event.target.value)} aria-label={t("overview.patients.filterAriaLabel")}>
                  {signalFilters.map((filter) => (
                    <option key={filter.value} value={filter.value}>
                      {filter.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="react-button react-button--text react-help-link"
                onClick={() => setHelpOpen(true)}
              >
                <HelpIcon />
                <span>{t("overview.patients.helpButtonLabel")}</span>
              </button>
              <div className="react-search react-search--patients">
                <input
                  type="search"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                  placeholder={t("overview.patients.searchPlaceholder")}
                  aria-label={t("overview.patients.searchAriaLabel")}
                />
              </div>
            </div>
          </div>

          <p className="react-visually-hidden" role="status">
            {copiedPatient ? `${t("overview.patients.copied")}: ${copiedPatient.short_id}` : ""}
          </p>

          {loadingPatients ? (
            <StateBlock title={t("overview.patients.loading.title")} description={t("overview.patients.loading.description")} tone="info" />
          ) : patientsError ? (
            <StateBlock title={t("overview.patients.error.title")} description={t("overview.patients.error.description")} tone="danger" />
          ) : visiblePatients.length ? (
            <>
              {compactList ? (
                <ul className="react-patient-rows">
                  {visiblePatients.map((patient) => {
                    const signal = getPatientSignal(patient, t);
                    return (
                      <li key={patient.id} className="react-patient-row">
                        <div className="react-patient-row__head">
                          <h3>{patient.display_name}</h3>
                          <span className={`react-signal-chip react-signal-chip--${signal.tone}`}>{signal.label}</span>
                        </div>
                        <p className="react-patient-row__numbers">
                          {t("overview.patients.rowSummary", {
                            avg: avgLabel(patient),
                            low: formatNumber(patient.pct_hypo, "%", i18n.language),
                            high: formatNumber(patient.pct_hyper, "%", i18n.language)
                          })}
                        </p>
                        <div className="react-patient-row__foot">
                          <span className="react-patient-code-inline">
                            <span className="react-mono">{patient.short_id}</span>
                            {copyButton(patient)}
                          </span>
                          {openPanelLink(patient)}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="react-table-shell react-table-shell--patients">
                  <table className="react-table react-patient-table">
                    <thead>
                      <tr>
                        <th scope="col">{t("overview.patients.columns.patient")}</th>
                        <th scope="col">{t("overview.patients.columns.code")}</th>
                        <th scope="col">{t("overview.patients.columns.profile")}</th>
                        <th scope="col" className="is-num">{t("overview.patients.columns.days")}</th>
                        <th scope="col" className="is-num">{t("overview.patients.columns.avg")}</th>
                        <th scope="col" className="is-num">{t("overview.patients.columns.low")}</th>
                        <th scope="col" className="is-num">{t("overview.patients.columns.high")}</th>
                        <th scope="col"><span className="react-visually-hidden">{t("overview.patients.columns.actions")}</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visiblePatients.map((patient) => {
                        const signal = getPatientSignal(patient, t);
                        return (
                          <tr key={patient.id}>
                            <th scope="row">{patient.display_name}</th>
                            <td>
                              <span className="react-patient-code-inline">
                                <span className="react-mono">{patient.short_id}</span>
                                {copyButton(patient)}
                              </span>
                            </td>
                            <td><span className={`react-signal-chip react-signal-chip--${signal.tone}`} title={signal.label}>{signal.shortLabel}</span></td>
                            <td className="is-num">{formatNumber(patient.days_observed, "", i18n.language)}</td>
                            <td className="is-num">{avgLabel(patient)}</td>
                            <td className="is-num">{formatNumber(patient.pct_hypo, "%", i18n.language)}</td>
                            <td className="is-num">{formatNumber(patient.pct_hyper, "%", i18n.language)}</td>
                            <td className="react-patient-table__action">{openPanelLink(patient)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="react-panel__footer">
                <Pagination page={patients.page} pages={patients.pages} count={patients.count} pageSize={currentPageSize} onPageChange={handlePageChange} onPageSizeChange={handlePageSizeChange} />
              </div>
            </>
          ) : (
            <StateBlock title={t("overview.patients.emptyAll.title")} description={t("overview.patients.emptyAll.description")} />
          )}
        </section>
      </div>
      <FilterHelpDialog signal={currentSignal} open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}

function formatReadingWhen(value, locale) {
  return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function PatientHome({ patient }) {
  const { t, i18n } = useTranslation();
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let active = true;
    fetchDashboardSummary()
      .then((data) => {
        if (!active) return;
        setSummary(data);
        setStatus("ready");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, []);

  const latest = summary?.latest_reading;
  const formatCount = (value) => new Intl.NumberFormat(i18n.language).format(value ?? 0);

  return (
    <div className="react-page react-page--patient-home">
      <header className="react-page-header">
        <h1>{t("patientHome.greeting", { name: patient.display_name })}</h1>
        <p>{t("patientHome.body")}</p>
      </header>

      <section className="react-panel react-latest-reading" aria-labelledby="latest-reading-title">
        <h2 id="latest-reading-title" className="react-latest-reading__label">{t("patientHome.metrics.latest.label")}</h2>
        {status === "loading" ? (
          <StateBlock title={t("overview.summaryLoading.title")} description={t("overview.summaryLoading.description")} tone="info" />
        ) : status === "error" ? (
          <StateBlock title={t("overview.summaryError.title")} description={t("overview.summaryError.description")} tone="danger" />
        ) : (
          <>
            {latest ? (
              <div className="react-latest-reading__reading">
                <p className="react-latest-reading__value">
                  <strong>{formatNumber(latest.glucose_mg_dl, "", i18n.language)}</strong>
                  <span>mg/dL</span>
                </p>
                <p className="react-latest-reading__time">
                  <time dateTime={latest.measured_at}>{formatReadingWhen(latest.measured_at, i18n.language)}</time>
                </p>
              </div>
            ) : (
              <p className="react-latest-reading__empty">{t("patientHome.metrics.latest.empty")}</p>
            )}
            <p className="react-latest-reading__counts">
              {t("patientHome.summary.counts.readings", { count: summary.metrics.normalized_count ?? 0, value: formatCount(summary.metrics.normalized_count) })}
              {" · "}
              {t("patientHome.summary.counts.days", { count: summary.metrics.indicator_count ?? 0, value: formatCount(summary.metrics.indicator_count) })}
            </p>
          </>
        )}
        <div className="react-actions react-latest-reading__actions">
          <Link to={`/patients/${patient.id}#new-reading`} className="react-button">
            {t("patientHome.newReading")}
          </Link>
          <Link to={`/patients/${patient.id}`} className="react-button react-button--ghost">
            {t("patientHome.openPanel")}
          </Link>
        </div>
      </section>

      <ProactivePrompt />
      <InvestigationsList />
      <DoctorLinksManager />
    </div>
  );
}

export default function OverviewPage() {
  const { session } = useAuth();
  if (session?.patient?.id) {
    return <PatientHome patient={session.patient} />;
  }
  return <DoctorHome />;
}
