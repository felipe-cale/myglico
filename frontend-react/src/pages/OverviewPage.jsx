import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fetchDashboardSummary, fetchPatients } from "../api";
import MetricCard from "../components/MetricCard";
import Pagination from "../components/Pagination";
import StateBlock from "../components/StateBlock";
import { useAuth } from "../contexts/AuthContext";
import DoctorLinksManager, { PendingLinksPanel } from "../components/DoctorLinksManager";
import InvestigationsList from "../components/InvestigationsList";
import ProactivePrompt from "../components/ProactivePrompt";
import CloseIcon from "../components/CloseIcon";
import useFocusTrap from "../hooks/useFocusTrap";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

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
  return { label: t(`signal.${code}`), tone };
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

  return (
    <div className="react-page react-page--doctor-home">
      <section className="react-hero react-hero--doctor">
        <div className="react-hero__content">
          <h1>{t("doctorHome.title")}</h1>
          <p>{t("doctorHome.body")}</p>
        </div>
      </section>

      <div className="react-home-columns react-home-columns--doctor">
        <PendingLinksPanel onChange={() => setReloadToken((current) => current + 1)} />
        <InvestigationsList />
      </div>

      <section className="react-panel">
        <div className="react-panel__header react-panel__header--patients">
          <div className="react-panel__header-copy">
            <p className="react-eyebrow">{t("overview.patients.eyebrow")}</p>
            <h2>{t("overview.patients.title")}</h2>
            <p>{t("overview.patients.body")}</p>
          </div>
          <div className="react-patient-toolbar">
            <div className="react-patient-filter-row">
              <label className="react-select-field">
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
                className="react-help-button"
                aria-label={t("overview.patients.helpButtonAriaLabel")}
                onClick={() => setHelpOpen(true)}
              >
                ?
              </button>
            </div>
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

        {loadingPatients ? (
          <StateBlock title={t("overview.patients.loading.title")} description={t("overview.patients.loading.description")} tone="info" />
        ) : patientsError ? (
          <StateBlock title={t("overview.patients.error.title")} description={t("overview.patients.error.description")} tone="danger" />
        ) : patients && patients.patients.length ? (
          <>
            <div className="react-patient-grid">
              {visiblePatients.map((patient) => {
                const signal = getPatientSignal(patient, t);
                const copied = copiedPatientId === patient.id;
                return (
                  <article key={patient.id} className="react-patient-card">
                    <div className="react-patient-card__identity">
                      <h3>{patient.display_name}</h3>
                      <div className="react-patient-code">
                        <div className="react-patient-code__content">
                          <span className="react-patient-code__label">{t("overview.patients.patientCode")}</span>
                          <strong className="react-patient-code__value">{patient.short_id}</strong>
                        </div>
                        <button
                          type="button"
                          className={`react-patient-code__copy${copied ? " is-copied" : ""}`}
                          aria-label={t("overview.patients.copyAriaLabel", { code: patient.short_id })}
                          onClick={() => handleCopyShortId(patient.id, patient.short_id)}
                        >
                          {copied ? t("overview.patients.copied") : t("overview.patients.copy")}
                        </button>
                      </div>
                      <span className={`react-patient-card__signal react-patient-card__signal--${signal.tone}`}>{signal.label}</span>
                      <p>{t("overview.patients.daysObserved", { count: patient.days_observed })}</p>
                    </div>
                    <dl className="react-patient-card__metrics">
                      <div className="react-patient-card__metric-row">
                        <dt>{t("overview.patients.avgPeriod")}</dt>
                        <dd>{patient.avg_glucose != null ? `${formatNumber(patient.avg_glucose, "", i18n.language)} mg/dL` : "-"}</dd>
                      </div>
                      <div className="react-patient-card__metric-row">
                        <dt>{t("overview.patients.timeInLow")}</dt>
                        <dd>{formatNumber(patient.pct_hypo, "%", i18n.language)}</dd>
                      </div>
                      <div className="react-patient-card__metric-row">
                        <dt>{t("overview.patients.timeInHigh")}</dt>
                        <dd>{formatNumber(patient.pct_hyper, "%", i18n.language)}</dd>
                      </div>
                    </dl>
                    <Link to={`/patients/${patient.id}`} className="react-patient-card__footer">
                      <span>{t("overview.patients.openPatientPanel")}</span>
                    </Link>
                  </article>
                );
              })}
            </div>
            {visiblePatients.length ? (
              <div className="react-panel__footer">
                <Pagination page={patients.page} pages={patients.pages} count={patients.count} pageSize={currentPageSize} onPageChange={handlePageChange} onPageSizeChange={handlePageSizeChange} />
              </div>
            ) : (
              <StateBlock title={t("overview.patients.emptyFilter.title")} description={t("overview.patients.emptyFilter.description")} />
            )}
          </>
        ) : (
          <StateBlock title={t("overview.patients.emptyAll.title")} description={t("overview.patients.emptyAll.description")} />
        )}
      </section>
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

  return (
    <div className="react-page">
      <section className="react-hero react-hero--patient-home">
        <div className="react-hero__content">
          <h1>{t("patientHome.greeting", { name: patient.display_name })}</h1>
          <p>{t("patientHome.body")}</p>
          <div className="react-actions react-hero__actions">
            <Link to={`/patients/${patient.id}#new-reading`} className="react-button">
              {t("patientHome.newReading")}
            </Link>
            <Link to={`/patients/${patient.id}`} className="react-button react-button--ghost">
              {t("patientHome.openPanel")}
            </Link>
          </div>
        </div>
        <div className="react-hero__visual">
          <img src={assetUrl("img/myglico-logo.png")} alt={t("overview.hero.imageAlt")} />
        </div>
      </section>

      <ProactivePrompt />

      <section className="react-panel" aria-labelledby="personal-summary-title">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <h2 id="personal-summary-title">{t("patientHome.summary.title")}</h2>
            <p>{t("patientHome.summary.body")}</p>
          </div>
        </div>
        {status === "loading" ? (
          <StateBlock title={t("overview.summaryLoading.title")} description={t("overview.summaryLoading.description")} tone="info" />
        ) : status === "error" ? (
          <StateBlock title={t("overview.summaryError.title")} description={t("overview.summaryError.description")} tone="danger" />
        ) : (
          <div className="react-grid react-grid--metrics react-grid--embedded">
            <MetricCard
              label={t("patientHome.metrics.latest.label")}
              value={summary.latest_reading ? `${formatNumber(summary.latest_reading.glucose_mg_dl, "", i18n.language)} mg/dL` : "-"}
              helper={summary.latest_reading ? formatReadingWhen(summary.latest_reading.measured_at, i18n.language) : t("patientHome.metrics.latest.empty")}
              tone="blue"
            />
            <MetricCard label={t("patientHome.metrics.records.label")} value={summary.metrics.normalized_count} helper={t("patientHome.metrics.records.helper")} tone="cyan" />
            <MetricCard label={t("patientHome.metrics.days.label")} value={summary.metrics.indicator_count} helper={t("patientHome.metrics.days.helper")} tone="green" />
          </div>
        )}
      </section>

      <DoctorLinksManager />
      <InvestigationsList />
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
