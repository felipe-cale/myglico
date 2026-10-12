import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { fetchDoctorLinks, fetchPatientDetail, patientReportPdfUrl, revokeDoctorLink } from "../api";
import StateBlock from "../components/StateBlock";
import AtypicalDaysPopup from "../components/AtypicalDaysPopup";
import ConfirmDialog from "../components/ConfirmDialog";
import ManualGlucoseEntryForm from "../components/ManualGlucoseEntryForm";
import { useAuth } from "../contexts/AuthContext";

const PIE_COLORS = ["#e35d73", "#19a86a", "#f4a93d"];
const HOURLY_TICKS = Array.from({ length: 24 }, (_, index) => index);
const TREND_COLOR = "#167cd9";
const HYPO_COLOR = "#e35d73";
const HYPER_COLOR = "#f4a93d";
const HIGH_RISK_COLOR = "#7a52cc";

function formatNumberBase(value, suffix = "", locale = "pt-BR") {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value) + suffix;
}

function formatDateBase(dateValue, locale = "pt-BR") {
  if (!dateValue) {
    return "-";
  }
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(`${dateValue}T00:00:00`));
}

function formatDateTimeBase(dateValue, locale = "pt-BR") {
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(dateValue));
}

function formatShortDateBase(dateValue, locale = "pt-BR") {
  if (!dateValue) {
    return "-";
  }
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${dateValue}T00:00:00`));
}

function getClusterProfileLabel(indicator, t) {
  if (indicator?.cluster_profile_code) {
    return t(`clusterProfile.${indicator.cluster_profile_code}.label`);
  }
  if (indicator?.cluster_profile_label) {
    return indicator.cluster_profile_label;
  }
  if (indicator?.cluster_label !== null && indicator?.cluster_label !== undefined) {
    return t("clusterProfile.group", { n: indicator.cluster_label });
  }
  return "-";
}

function getClusterProfileDescription(indicator, t) {
  if (indicator?.cluster_profile_code) {
    return t(`clusterProfile.${indicator.cluster_profile_code}.description`);
  }
  return indicator?.cluster_profile_description;
}

function enumLabel(namespace, code, fallback, t) {
  if (!code) {
    return fallback || "-";
  }
  const key = `enums.${namespace}.${code}`;
  const translated = t(key);
  return translated === key ? fallback || code : translated;
}

function InfoTooltip({ content, label }) {
  const [isOpen, setIsOpen] = useState(false);
  const tooltipRef = useRef(null);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const handlePointerDown = (event) => {
      if (!tooltipRef.current?.contains(event.target)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  if (!content) {
    return null;
  }

  return (
    <span
      className={`react-info-tooltip${isOpen ? " is-open" : ""}`}
      ref={tooltipRef}
      onClick={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        className="react-info-tooltip__trigger"
        aria-label={label}
        aria-expanded={isOpen}
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((current) => !current);
        }}
      >
        i
      </button>
      <span className="react-info-tooltip__content" role="tooltip">
        {content}
      </span>
    </span>
  );
}

function PendingAnalysisChip() {
  const { t } = useTranslation();
  return <span className="react-badge react-badge--pending react-badge--compact">{t("patientDetail.dailyIndicators.badgePending")}</span>;
}

function ClusterProfileValue({ indicator, compact = false, showGroup = true }) {
  const { t } = useTranslation();
  if (indicator?.analysis_pending) {
    return <PendingAnalysisChip />;
  }
  const profileLabel = getClusterProfileLabel(indicator, t);
  const profileDescription = getClusterProfileDescription(indicator, t);
  const hasProfile = Boolean(indicator?.cluster_profile_code || indicator?.cluster_profile_label);
  const groupLabel =
    showGroup && hasProfile && indicator?.cluster_label !== null && indicator?.cluster_label !== undefined
      ? t("clusterProfile.group", { n: indicator.cluster_label })
      : null;

  return (
    <span className={`react-cluster-profile${compact ? " is-compact" : ""}`}>
      <span className="react-cluster-profile__row">
        <span className="react-cluster-profile__label">{profileLabel}</span>
        <InfoTooltip content={profileDescription} label={t("common.explain", { label: profileLabel })} />
      </span>
      {groupLabel ? <small>{groupLabel}</small> : null}
    </span>
  );
}

function PatientStatCard({ label, value, helper, tone = "blue", onClick, actionHint, ariaLabel, buttonRef }) {
  const Tag = onClick ? "button" : "article";
  return (
    <Tag
      className={`react-stat-card react-stat-card--${tone}${onClick ? " react-stat-card--interactive" : ""}`}
      ref={buttonRef}
      onClick={onClick}
      type={onClick ? "button" : undefined}
      aria-label={ariaLabel}
      aria-haspopup={onClick ? "dialog" : undefined}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
      {actionHint ? <small className="react-stat-card__action-hint">{actionHint}</small> : null}
    </Tag>
  );
}

function MobileDetailField({ label, value, children, className = "" }) {
  return (
    <div className={`react-mobile-card__field${className ? ` ${className}` : ""}`}>
      <span>{label}</span>
      {children ?? <strong>{value}</strong>}
    </div>
  );
}

const DEFAULT_WINDOW_DAYS = 30;

// Mirrors the backend default (reports._resolve_date_window): the last 30 days up to the latest available date.
function isDefaultDetailWindow(filters) {
  const { start_date: start, end_date: end, available_start_date: availableStart, available_end_date: availableEnd } = filters ?? {};
  if (!start || !end || !availableEnd || end !== availableEnd) return false;
  const windowStart = new Date(`${availableEnd}T00:00:00Z`);
  windowStart.setUTCDate(windowStart.getUTCDate() - (DEFAULT_WINDOW_DAYS - 1));
  let expectedStart = windowStart.toISOString().slice(0, 10);
  if (availableStart && expectedStart < availableStart) expectedStart = availableStart;
  return start === expectedStart;
}

const PRESERVED_RANGE_KEY = "myglico.preservedRange.";

// The user's period before exact days widened it; kept per tab so a reload can still restore it.
function readPreservedRange(patientId) {
  try {
    const raw = window.sessionStorage.getItem(`${PRESERVED_RANGE_KEY}${patientId}`);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed?.start && parsed?.end ? parsed : null;
  } catch {
    return null;
  }
}

function writePreservedRange(patientId, value) {
  try {
    const key = `${PRESERVED_RANGE_KEY}${patientId}`;
    if (value?.start && value?.end) window.sessionStorage.setItem(key, JSON.stringify({ start: value.start, end: value.end }));
    else window.sessionStorage.removeItem(key);
  } catch {
    // Without storage the in-memory value still covers the current page view.
  }
}

function rangeCoveringDates(base, dates) {
  let start = base?.start || "";
  let end = base?.end || "";
  const first = dates[0];
  const last = dates[dates.length - 1];
  const outside = dates.filter((value) => (start && value < start) || (end && value > end));
  if (start && first < start) start = first;
  if (end && last > end) end = last;
  return { start, end, adjusted: outside.length > 0, outside, originalStart: base?.start || "", originalEnd: base?.end || "" };
}

export default function PatientDetailPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const formatNumber = (value, suffix = "") => formatNumberBase(value, suffix, locale);
  const formatDate = (dateValue) => formatDateBase(dateValue, locale);
  const formatDateTime = (dateValue) => formatDateTimeBase(dateValue, locale);
  const formatPatientEventDateTime = (event) => event.event_date && event.event_time
    ? `${formatDate(event.event_date)} ${event.event_time}`
    : formatDateTime(event.occurred_at);
  const formatShortDate = (dateValue) => formatShortDateBase(dateValue, locale);
  const { patientId } = useParams();
  const { session } = useAuth();
  const navigate = useNavigate();
  const isDoctorView = Boolean(session?.doctor?.id);
  const [doctorLink, setDoctorLink] = useState(null);
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [draftStartDate, setDraftStartDate] = useState("");
  const [draftEndDate, setDraftEndDate] = useState("");
  const [viewMode, setViewMode] = useState("period");
  const [selectedDay, setSelectedDay] = useState("");
  const [isCompactMobile, setIsCompactMobile] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width: 640px)").matches : false
  );
  const [reloadToken, setReloadToken] = useState(0);
  const lastResolvedRequestRef = useRef("");
  const preservedRangeRef = useRef(readPreservedRange(patientId));
  const preservedPatientRef = useRef(patientId);
  if (preservedPatientRef.current !== patientId) {
    preservedPatientRef.current = patientId;
    preservedRangeRef.current = readPreservedRange(patientId);
  }

  function setPreservedRange(value) {
    preservedRangeRef.current = value;
    writePreservedRange(patientId, value);
  }
  const silentReloadRef = useRef(false);

  useEffect(() => {
    if (!isDoctorView) return undefined;
    let active = true;
    setDoctorLink(null);
    fetchDoctorLinks()
      .then((payload) => {
        if (!active) return;
        const links = payload.links || payload || [];
        setDoctorLink(links.find((link) => link.patient_id === patientId && link.status === "active") || null);
      })
      .catch(() => {
        if (active) setDoctorLink(null);
      });
    return () => {
      active = false;
    };
  }, [isDoctorView, patientId]);

  async function handleRevokeLink() {
    if (!doctorLink) return;
    setRevoking(true);
    setRevokeError("");
    try {
      await revokeDoctorLink(doctorLink.id, { version: doctorLink.version });
      setRevokeOpen(false);
      navigate("/dashboard", { replace: true });
    } catch {
      setRevokeError(t("dashboard.linkActionFailed"));
      setRevoking(false);
    }
  }

  const isDayMode = viewMode === "day";
  const summary = data?.summary;
  const hourlyLows = data?.hourly_lows ?? [];
  const hourlyHighs250 = data?.hourly_highs_250 ?? [];

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(max-width: 640px)");
    const updateViewportMode = (event) => {
      setIsCompactMobile(event.matches);
    };

    setIsCompactMobile(mediaQuery.matches);

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", updateViewportMode);
      return () => mediaQuery.removeEventListener("change", updateViewportMode);
    }

    mediaQuery.addListener(updateViewportMode);
    return () => mediaQuery.removeListener(updateViewportMode);
  }, []);

  const requestedStart = searchParams.get("start_date") || undefined;
  const requestedEnd = searchParams.get("end_date") || undefined;
  const requestedDatesParam = searchParams.get("dates") || "";
  const requestedDates = useMemo(
    () => requestedDatesParam.split(",").map((value) => value.trim()).filter(Boolean).sort(),
    [requestedDatesParam]
  );
  useEffect(() => {
    if (!requestedDatesParam && preservedRangeRef.current) {
      setPreservedRange(null);
    }
  }, [patientId, requestedDatesParam]);

  const requestKey = `${patientId}:${requestedStart || ""}:${requestedEnd || ""}:${requestedDatesParam}:${reloadToken}`;

  useEffect(() => {
    if (data && lastResolvedRequestRef.current === requestKey) {
      setLoading(false);
      return;
    }

    let active = true;
    if (!silentReloadRef.current) {
      setLoading(true);
    }
    silentReloadRef.current = false;
    setError(null);
    const hasExactDates = requestedDates.length > 0;
    const detailRequest = hasExactDates
      ? { dates: requestedDates }
      : { startDate: requestedStart, endDate: requestedEnd };
    fetchPatientDetail(patientId, detailRequest)
      .then((payload) => {
        if (!active) {
          return;
        }
        // With exact days the API reports no period, so the user's period stays in the URL untouched.
        const periodStart = hasExactDates ? requestedStart || preservedRangeRef.current?.start : payload.filters.start_date;
        const periodEnd = hasExactDates ? requestedEnd || preservedRangeRef.current?.end : payload.filters.end_date;
        setData(payload);
        setDraftStartDate(periodStart || "");
        setDraftEndDate(periodEnd || "");
        lastResolvedRequestRef.current = `${patientId}:${periodStart || ""}:${periodEnd || ""}:${requestedDatesParam}:${reloadToken}`;

        const next = new URLSearchParams();
        if (periodStart) {
          next.set("start_date", periodStart);
        }
        if (periodEnd) {
          next.set("end_date", periodEnd);
        }
        if (requestedDatesParam) {
          next.set("dates", requestedDatesParam);
        }
        const nextQuery = next.toString();
        const currentQuery = searchParams.toString();
        if (nextQuery !== currentQuery) {
          setSearchParams(next, { replace: true });
        }
      })
      .catch((reason) => {
        if (active) {
          setError(reason);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [patientId, requestedStart, requestedEnd, requestedDates, requestedDatesParam, requestKey, reloadToken, data, searchParams, setSearchParams]);

  const chartData = useMemo(() => {
    if (!data) {
      return [];
    }
    return data.daily_indicators.map((indicator) => ({
      ...indicator,
      label: formatShortDate(indicator.date)
    }));
  }, [data]);

  const glucoseEventsByDate = useMemo(() => {
    if (!data) {
      return {};
    }

    return data.glucose_events.reduce((accumulator, event) => {
      const key = event.event_date;
      if (!accumulator[key]) {
        accumulator[key] = [];
      }
      accumulator[key].push({
        ...event,
        time_label: event.event_time,
        glucose_value: event.glucose_mg_dl
      });
      return accumulator;
    }, {});
  }, [data]);

  const availableDayDates = useMemo(() => {
    if (!data) {
      return [];
    }

    const fromIndicators = data.daily_indicators.map((indicator) => indicator.date);
    const fromEvents = Object.keys(glucoseEventsByDate);
    return Array.from(new Set([...fromIndicators, ...fromEvents])).sort();
  }, [data, glucoseEventsByDate]);

  const selectedDayEvents = useMemo(() => {
    if (!selectedDay) {
      return [];
    }
    return glucoseEventsByDate[selectedDay] || [];
  }, [glucoseEventsByDate, selectedDay]);

  const selectedDaySummary = useMemo(() => {
    if (!selectedDay) {
      return null;
    }

    const glucoseValues = selectedDayEvents
      .map((event) => event.glucose_mg_dl)
      .filter((value) => value !== null && value !== undefined);

    if (!glucoseValues.length) {
      return null;
    }

    const total = glucoseValues.length;
    const hypoCount = glucoseValues.filter((value) => value < 70).length;
    const hyperCount = glucoseValues.filter((value) => value > 180).length;
    const inRangeCount = total - hypoCount - hyperCount;

    return {
      date: selectedDay,
      measurementCount: total,
      avgGlucose: glucoseValues.reduce((sum, value) => sum + value, 0) / total,
      pctHypo: (hypoCount / total) * 100,
      pctInRange: (inRangeCount / total) * 100,
      pctHyper: (hyperCount / total) * 100,
      lowEventsCount: hypoCount,
      highEventsCount: hyperCount
    };
  }, [selectedDay, selectedDayEvents]);

  const distributionData = useMemo(() => {
    if (!data) {
      return [];
    }
    return [
      { name: t("patientDetail.distribution.hypo"), value: data.summary.pct_hypo },
      { name: t("patientDetail.distribution.inRange"), value: data.summary.pct_in_range },
      { name: t("patientDetail.distribution.hyper"), value: data.summary.pct_hyper }
    ];
  }, [data, t]);

  const selectedDayDistribution = useMemo(() => {
    if (!selectedDaySummary) {
      return [];
    }

    return [
      { name: t("patientDetail.distribution.hypo"), value: selectedDaySummary.pctHypo },
      { name: t("patientDetail.distribution.inRange"), value: selectedDaySummary.pctInRange },
      { name: t("patientDetail.distribution.hyper"), value: selectedDaySummary.pctHyper }
    ];
  }, [selectedDaySummary, t]);

  const overviewStats = useMemo(() => {
    if (isDayMode && selectedDaySummary) {
      return [
        {
          label: t("patientDetail.stats.measurements.label"),
          value: selectedDaySummary.measurementCount,
          helper: t("patientDetail.stats.measurements.helper"),
          tone: "blue"
        },
        {
          label: t("patientDetail.stats.avgDay.label"),
          value: `${formatNumber(selectedDaySummary.avgGlucose)} mg/dL`,
          helper: formatShortDate(selectedDaySummary.date),
          tone: "cyan"
        },
        {
          label: t("patientDetail.stats.pctHypoDay.label"),
          value: formatNumber(selectedDaySummary.pctHypo, "%"),
          helper: t("patientDetail.stats.pctHypoDay.helper", { count: selectedDaySummary.lowEventsCount }),
          tone: "rose"
        },
        {
          label: t("patientDetail.stats.pctInRangeDay.label"),
          value: formatNumber(selectedDaySummary.pctInRange, "%"),
          helper: t("patientDetail.stats.pctInRangeDay.helper"),
          tone: "green"
        },
        {
          label: t("patientDetail.stats.pctHyperDay.label"),
          value: formatNumber(selectedDaySummary.pctHyper, "%"),
          helper: t("patientDetail.stats.pctHyperDay.helper", { count: selectedDaySummary.highEventsCount }),
          tone: "yellow"
        }
      ];
    }

    return [
      {
        label: t("patientDetail.stats.daysObserved.label"),
        value: summary?.days_observed ?? "-",
        helper: t("patientDetail.stats.daysObserved.helper"),
        tone: "blue"
      },
      {
        label: t("patientDetail.stats.avgGlucose.label"),
        value: `${formatNumber(summary?.avg_glucose)} mg/dL`,
        helper: t("patientDetail.stats.avgGlucose.helper"),
        tone: "cyan"
      },
      {
        label: t("patientDetail.stats.pctHypoPeriod.label"),
        value: formatNumber(summary?.pct_hypo, "%"),
        helper: t("patientDetail.stats.pctHypoPeriod.helper"),
        tone: "rose"
      },
      {
        label: t("patientDetail.stats.pctInRangePeriod.label"),
        value: formatNumber(summary?.pct_in_range, "%"),
        helper: t("patientDetail.stats.pctInRangePeriod.helper"),
        tone: "green"
      },
      {
        label: t("patientDetail.stats.pctHyperPeriod.label"),
        value: formatNumber(summary?.pct_hyper, "%"),
        helper: t("patientDetail.stats.pctHyperPeriod.helper"),
        tone: "yellow"
      },
      {
        label: t("patientDetail.stats.anomalyDays.label"),
        value: summary?.anomaly_days ?? "-",
        helper: t("patientDetail.stats.anomalyDays.helper"),
        actionHint: t("patientDetail.stats.anomalyDays.action"),
        action: "atypical-days",
        tone: "slate"
      }
    ];
  }, [isDayMode, selectedDaySummary, summary, t, locale]);

  const hourlyExtremes = useMemo(
    () =>
      HOURLY_TICKS.map((hour) => ({
        hour,
        lowCount: hourlyLows.find((item) => item.hour === hour)?.count ?? 0,
        highCount: hourlyHighs250.find((item) => item.hour === hour)?.count ?? 0,
      })),
    [hourlyHighs250, hourlyLows]
  );

  useEffect(() => {
    if (!availableDayDates.length) {
      setSelectedDay("");
      setViewMode("period");
      return;
    }

    if (selectedDay && availableDayDates.includes(selectedDay)) {
      return;
    }

    if (selectedDay) {
      setSelectedDay("");
    }
    setViewMode("period");
  }, [availableDayDates, selectedDay]);

  const hasPendingFilterChange = Boolean(
    data &&
      (draftStartDate !== (data.filters.start_date || "") || draftEndDate !== (data.filters.end_date || ""))
  );
  const hasInvalidRange = Boolean(draftStartDate && draftEndDate && draftStartDate > draftEndDate);

  function applyRange(event) {
    event.preventDefault();
    if (!draftStartDate || !draftEndDate || hasInvalidRange) {
      return;
    }

    const next = new URLSearchParams(searchParams);
    let nextStart = draftStartDate;
    let nextEnd = draftEndDate;
    if (requestedDates.length) {
      setPreservedRange({ start: draftStartDate, end: draftEndDate });
      const covering = rangeCoveringDates({ start: draftStartDate, end: draftEndDate }, requestedDates);
      nextStart = covering.start;
      nextEnd = covering.end;
    }
    next.set("start_date", nextStart);
    next.set("end_date", nextEnd);

    if (next.toString() !== searchParams.toString()) {
      lastResolvedRequestRef.current = "";
      setSelectedDay("");
      setViewMode("period");
      setSearchParams(next);
    }
  }

  function showFullHistory() {
    const availableStart = data?.filters?.available_start_date;
    const availableEnd = data?.filters?.available_end_date;
    if (!availableStart || !availableEnd) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("dates");
    next.set("start_date", availableStart);
    next.set("end_date", availableEnd);
    setPreservedRange(null);
    lastResolvedRequestRef.current = "";
    setSelectedDay("");
    setViewMode("period");
    setSearchParams(next);
  }

  function applyAtypicalDates(dates) {
    const exactDates = Array.from(new Set(dates)).sort();
    const next = new URLSearchParams(searchParams);
    const currentStart = searchParams.get("start_date") || data?.filters?.start_date || "";
    const currentEnd = searchParams.get("end_date") || data?.filters?.end_date || "";
    if (exactDates.length) {
      if (!requestedDates.length || !preservedRangeRef.current) {
        setPreservedRange({ start: currentStart, end: currentEnd });
      }
      // Days outside the user's period widen it explicitly; the original period is kept to restore on clear.
      const covering = rangeCoveringDates(preservedRangeRef.current, exactDates);
      next.set("dates", exactDates.join(","));
      if (covering.start && covering.end) {
        next.set("start_date", covering.start);
        next.set("end_date", covering.end);
      }
    } else {
      const restoreStart = preservedRangeRef.current?.start || currentStart;
      const restoreEnd = preservedRangeRef.current?.end || currentEnd;
      next.delete("dates");
      if (restoreStart && restoreEnd) {
        next.set("start_date", restoreStart);
        next.set("end_date", restoreEnd);
      } else {
        next.delete("start_date");
        next.delete("end_date");
      }
      setPreservedRange(null);
    }
    lastResolvedRequestRef.current = "";
    setSelectedDay("");
    setViewMode("period");
    setSearchParams(next);
  }

  function clearDaySelection() {
    applyAtypicalDates([]);
  }

  function removeSelectedDay(date) {
    applyAtypicalDates(requestedDates.filter((value) => value !== date));
  }

  function handleManualRecordCreated(record) {
    const measuredDate = record?.measured_at?.slice(0, 10);
    const { start_date: currentStart, end_date: currentEnd } = data?.filters ?? {};
    silentReloadRef.current = true;
    lastResolvedRequestRef.current = "";
    if (measuredDate && currentStart && currentEnd && (measuredDate < currentStart || measuredDate > currentEnd)) {
      const windowStart = new Date(`${measuredDate}T00:00:00Z`);
      windowStart.setUTCDate(windowStart.getUTCDate() - 29);
      const startDate = windowStart.toISOString().slice(0, 10);
      const next = new URLSearchParams(searchParams);
      next.set("start_date", startDate);
      next.set("end_date", measuredDate);
      setSelectedDay("");
      setViewMode("period");
      setDraftStartDate(startDate);
      setDraftEndDate(measuredDate);
      setSearchParams(next);
      return;
    }
    setReloadToken((current) => current + 1);
  }

  if (loading) {
    return <StateBlock title={t("patientDetail.loading.title")} description={t("patientDetail.loading.description")} tone="info" />;
  }

  if (error || !data) {
    return <StateBlock title={t("patientDetail.error.title")} description={t("patientDetail.error.description")} tone="danger" />;
  }

  const { patient, filters, recent_events: recentEvents } = data;
  const activeDistributionData = isDayMode && selectedDaySummary ? selectedDayDistribution : distributionData;
  const distributionChartHeight = isCompactMobile ? 182 : 206;
  const insightChartHeight = isCompactMobile ? 168 : 182;
  const dropHoursChartHeight = isCompactMobile ? 180 : 228;
  const trendChartHeight = isCompactMobile ? 260 : 340;
  const trendChartMargin = isCompactMobile
    ? { top: 8, right: 4, left: 0, bottom: 0 }
    : { top: 8, right: 12, left: 0, bottom: 0 };
  const dayChartMargin = isCompactMobile
    ? { top: 8, right: 4, left: 0, bottom: 0 }
    : { top: 8, right: 12, left: 0, bottom: 0 };
  const pieInnerRadius = isCompactMobile ? 56 : 64;
  const pieOuterRadius = isCompactMobile ? 72 : 80;
  const axisTickStyle = { fontSize: isCompactMobile ? 11 : 12 };
  const hourlyAxisTickStyle = { fontSize: isCompactMobile ? 9 : 10 };
  const hourlyAxisTicks = isCompactMobile
    ? Array.from(
        new Set([
          ...HOURLY_TICKS.filter((hour) => hour % 3 === 0),
          ...hourlyExtremes.filter((item) => item.lowCount > 0 || item.highCount > 0).map((item) => item.hour)
        ])
      ).sort((a, b) => a - b)
    : HOURLY_TICKS;
  const trendLegendItems = [
    {
      label: isDayMode ? t("patientDetail.trend.legendDayCurve") : t("patientDetail.trend.legendDailyAvg"),
      color: TREND_COLOR,
      dashed: false,
    },
    {
      label: t("patientDetail.trend.legendHypo"),
      color: HYPO_COLOR,
      dashed: true,
    },
    {
      label: t("patientDetail.trend.legendHyperTarget"),
      color: HYPER_COLOR,
      dashed: true,
    },
    {
      label: t("patientDetail.trend.legendHighRisk"),
      color: HIGH_RISK_COLOR,
      dashed: true,
    },
  ];
  function handleSelectDay(dateValue) {
    setSelectedDay(dateValue);
    setViewMode("day");
  }

  function handleShowPeriod() {
    setViewMode("period");
    setSelectedDay("");
  }

  const preservedRange = preservedRangeRef.current;
  const coveringRange = requestedDates.length && preservedRange ? rangeCoveringDates(preservedRange, requestedDates) : null;
  const periodAdjustment = coveringRange?.adjusted ? coveringRange : null;
  const isDefaultWindow = isDefaultDetailWindow(filters);
  const periodDays = filters.start_date && filters.end_date
    ? Math.round((Date.parse(`${filters.end_date}T00:00:00Z`) - Date.parse(`${filters.start_date}T00:00:00Z`)) / 86400000) + 1
    : 0;

  const isOwnPatientView = Boolean(session?.patient?.id && session.patient.id === patient.id);
  const pendingAnalysisDays = summary?.pending_analysis_days ?? 0;
  const isFullHistory = Boolean(
    filters.available_start_date &&
      filters.start_date === filters.available_start_date &&
      filters.end_date === filters.available_end_date
  );
  const reportUrl = patientReportPdfUrl(patient.id, {
    startDate: filters.start_date,
    endDate: filters.end_date,
    lang: locale
  });

  const revokeDialog = (
    <ConfirmDialog
      open={revokeOpen && Boolean(doctorLink)}
      eyebrow={t("dashboard.revokeDialog.eyebrow")}
      title={t("dashboard.revokeDialog.titleDoctor", { name: patient.display_name })}
      description={t("dashboard.revokeDialog.bodyDoctor", { name: patient.display_name })}
      confirmLabel={t("dashboard.revokeConfirm")}
      cancelLabel={t("dashboard.keepLink")}
      busy={revoking}
      error={revokeError}
      onConfirm={handleRevokeLink}
      onCancel={() => setRevokeOpen(false)}
    />
  );

  return (
    <div className="react-page react-page--patient-detail">
      {revokeDialog}
      <section className="react-hero react-hero--compact">
        <div className="react-hero__content">
          <div className="react-badges">
            {!isOwnPatientView && patient.source_file ? (
              <span className="react-badge react-badge--soft">{patient.source_file}</span>
            ) : null}
            <span className="react-badge react-badge--blue">{t("patientDetail.hero.measurementsBadge", { count: summary.glucose_measurements })}</span>
          </div>
          <p className="react-eyebrow">{isOwnPatientView ? t("patientDetail.hero.eyebrowSelf") : t("patientDetail.hero.eyebrow")}</p>
          <h1>{patient.display_name}</h1>
          <p>{isOwnPatientView ? t("patientDetail.hero.bodySelf") : t("patientDetail.hero.body")}</p>
          <div className="react-actions">
            <Link to="/dashboard" className="react-button react-button--ghost">
              {isOwnPatientView ? t("patientDetail.hero.backHome") : t("patientDetail.hero.backToOverview")}
            </Link>
            <a className="react-button" href={reportUrl || "#"} target="_blank" rel="noreferrer">
              {t("patientDetail.hero.downloadReport")}
            </a>
            {isDoctorView && doctorLink ? (
              <button
                type="button"
                className="react-button react-button--danger"
                onClick={() => {
                  setRevokeError("");
                  setRevokeOpen(true);
                }}
              >
                {t("dashboard.revokeLink")}
              </button>
            ) : null}
          </div>
        </div>
        <div className="react-hero__side">
          {requestedDates.length > 0 ? (
            <div className="react-summary-box" data-testid="period-summary">
              <span>{t("patientDetail.hero.selectedDays", { count: requestedDates.length })}</span>
              <strong>{requestedDates.map((value) => formatDate(value)).join(", ")}</strong>
              {requestedStart && requestedEnd ? (
                <small>{t("patientDetail.hero.referencePeriod", { start: formatDate(requestedStart), end: formatDate(requestedEnd) })}</small>
              ) : null}
            </div>
          ) : (
            <div className="react-summary-box" data-testid="period-summary">
              <span>{t("patientDetail.hero.periodAnalyzed")}</span>
              <strong>
                {formatDate(filters.start_date)} - {formatDate(filters.end_date)}
              </strong>
              <small>
                {isDefaultWindow
                  ? t("patientDetail.hero.defaultWindow")
                  : t("patientDetail.hero.customWindow", { count: periodDays })}
              </small>
              {filters.available_start_date && filters.available_end_date ? (
                <div className="react-summary-box__history">
                  <small data-testid="available-period">
                    {t("patientDetail.hero.availablePeriod", {
                      start: formatDate(filters.available_start_date),
                      end: formatDate(filters.available_end_date)
                    })}
                  </small>
                  {isFullHistory ? null : (
                    <button type="button" className="react-button react-button--ghost react-button--compact" onClick={showFullHistory}>
                      {t("patientDetail.hero.viewAllHistory")}
                    </button>
                  )}
                </div>
              ) : null}
              {pendingAnalysisDays > 0 ? (
                <p className="react-pending-note" role="note">
                  {t("patientDetail.hero.pendingAnalysisNote", { count: pendingAnalysisDays })}
                </p>
              ) : null}
            </div>
          )}
        </div>
      </section>

      <section className="react-panel react-panel--filter">
        <div className="react-filter-layout">
          <div className="react-filter-copy">
            <p className="react-eyebrow">{t("patientDetail.filter.eyebrow")}</p>
            <h2>{t("patientDetail.filter.title")}</h2>
            <p>{t("patientDetail.filter.body")}</p>
          </div>
          <div className="react-filter-controls">
            <form className="react-filter-form" onSubmit={applyRange}>
              <label>
                <span>{t("patientDetail.filter.startDate")}</span>
                <input
                  type="date"
                  value={draftStartDate}
                  min={filters.available_start_date}
                  max={filters.available_end_date}
                  onChange={(event) => setDraftStartDate(event.target.value)}
                />
              </label>
              <label>
                <span>{t("patientDetail.filter.endDate")}</span>
                <input
                  type="date"
                  value={draftEndDate}
                  min={filters.available_start_date}
                  max={filters.available_end_date}
                  onChange={(event) => setDraftEndDate(event.target.value)}
                />
              </label>
              <div className="react-filter-actions">
                <button
                  type="submit"
                  className="react-button"
                  disabled={loading || !hasPendingFilterChange || hasInvalidRange}
                >
                  {t("patientDetail.filter.apply")}
                </button>
                {hasInvalidRange ? <small>{t("patientDetail.filter.invalidRange")}</small> : null}
              </div>
            </form>
            {periodAdjustment ? (
              <p className="react-period-notice" role="status" data-testid="period-adjusted">
                {t("patientDetail.filter.periodAdjusted", {
                  dates: periodAdjustment.outside.map((value) => formatDate(value)).join(", "),
                  originalStart: formatDate(periodAdjustment.originalStart),
                  originalEnd: formatDate(periodAdjustment.originalEnd),
                  start: formatDate(periodAdjustment.start),
                  end: formatDate(periodAdjustment.end)
                })}
              </p>
            ) : null}
            {requestedDates.length > 0 ? (
              <div className="react-selected-days" role="group" aria-label={t("cscw.selectedDaysLabel")}>
                <span>{t("cscw.selectedDaysLabel")}</span>
                <div className="react-chip-row">
                  {requestedDates.map((date) => (
                    <button
                      type="button"
                      key={date}
                      className="react-chip is-active react-chip--removable"
                      onClick={() => removeSelectedDay(date)}
                      aria-label={t("cscw.removeDayAria", { date: formatDate(date) })}
                    >
                      {formatDate(date)} ×
                    </button>
                  ))}
                  <button type="button" className="react-chip" onClick={clearDaySelection}>
                    {t("cscw.popupClearDays")}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {isOwnPatientView ? (
        <ManualGlucoseEntryForm patientId={patient.id} onCreated={handleManualRecordCreated} />
      ) : null}

      <section className="react-patient-insights">
        <article className="react-panel react-panel--summary">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">{t("patientDetail.distribution.eyebrow")}</p>
              <h2>{isDayMode && selectedDaySummary ? t("patientDetail.distribution.titleDay", { date: formatShortDate(selectedDaySummary.date) }) : t("patientDetail.distribution.titlePeriod")}</h2>
            </div>
          </div>
            <div className="react-insight-body react-insight-body--distribution">
              <div className="react-distribution-visual">
                <div className="react-chart react-chart--insight react-chart--distribution">
                  <ResponsiveContainer width="100%" height={distributionChartHeight}>
                  <PieChart>
                    <Pie
                      data={activeDistributionData}
                      dataKey="value"
                      innerRadius={pieInnerRadius}
                      outerRadius={pieOuterRadius}
                      paddingAngle={3}
                    >
                      {activeDistributionData.map((entry, index) => (
                        <Cell key={entry.name} fill={PIE_COLORS[index]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `${formatNumber(value)}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
                <div className="react-distribution-center" aria-hidden="true">
                  <div className="react-distribution-center__stack">
                    {activeDistributionData.map((item, index) => (
                    <div key={item.name} className="react-distribution-center__item">
                      <span
                        className="react-distribution-center__dot"
                        style={{ backgroundColor: PIE_COLORS[index] }}
                      />
                      <span className="react-distribution-center__label">{item.name}</span>
                      <strong
                        className="react-distribution-center__value"
                        style={{ color: PIE_COLORS[index] }}
                      >
                        {formatNumber(item.value, "%")}
                      </strong>
                    </div>
                  ))}
                  </div>
                </div>
              </div>
            </div>
          </article>

        <article className="react-panel react-panel--summary react-panel--drop-hours">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">{t("patientDetail.extremeEvents.eyebrow")}</p>
              <h2>{t("patientDetail.extremeEvents.title")}</h2>
            </div>
          </div>
          <div className="react-chart react-chart--insight react-chart--drop-hours">
            <ResponsiveContainer width="100%" height={dropHoursChartHeight}>
              <BarChart data={hourlyExtremes} margin={trendChartMargin} barGap={isCompactMobile ? 2 : 4} barCategoryGap={isCompactMobile ? "10%" : "18%"}>
                <CartesianGrid strokeDasharray="4 4" stroke="rgba(22, 124, 217, 0.12)" />
                <XAxis
                  dataKey="hour"
                  ticks={hourlyAxisTicks}
                  interval={0}
                  tickFormatter={(value) => (isCompactMobile ? `${value}` : `${value}h`)}
                  tick={hourlyAxisTickStyle}
                  minTickGap={0}
                  height={isCompactMobile ? 28 : 32}
                />
                <YAxis allowDecimals={false} tick={axisTickStyle} width={isCompactMobile ? 24 : 32} />
                <Tooltip formatter={(value) => t("patientDetail.extremeEvents.tooltipEvents", { count: value })} labelFormatter={(label) => `${String(label).padStart(2, "0")}h`} />
                <Legend verticalAlign="top" height={32} wrapperStyle={{ fontSize: isCompactMobile ? "11px" : "12px" }} />
                <Bar dataKey="lowCount" name="< 70 mg/dL" fill="#27b7e7" radius={[8, 8, 0, 0]} />
                <Bar dataKey="highCount" name="> 250 mg/dL" fill="#f4a93d" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="react-patient-layout">
        <article className="react-panel react-patient-main">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">{t("patientDetail.trend.eyebrow")}</p>
              <h2>{isDayMode ? t("patientDetail.trend.titleDay") : t("patientDetail.trend.titlePeriod")}</h2>
              <p>
                {isDayMode && selectedDay
                  ? t("patientDetail.trend.bodyDay", { date: formatDate(selectedDay) })
                  : t("patientDetail.trend.bodyPeriod")}
              </p>
            </div>
            <div className="react-chip-row">
              <button
                type="button"
                className={`react-chip${!isDayMode ? " is-active" : ""}`}
                onClick={handleShowPeriod}
              >
                {t("patientDetail.trend.chipPeriod")}
              </button>
              {selectedDay ? (
                <button
                  type="button"
                  className={`react-chip${isDayMode ? " is-active" : ""}`}
                  onClick={() => setViewMode("day")}
                >
                  {t("patientDetail.trend.chipSelectedDay")}
                </button>
              ) : null}
            </div>
          </div>
          <div className="react-chart">
            {!isDayMode ? (
              <ResponsiveContainer width="100%" height={trendChartHeight}>
                <LineChart
                  data={chartData}
                  margin={trendChartMargin}
                  onClick={(state) => {
                    const clickedDate = state?.activePayload?.[0]?.payload?.date;
                    if (clickedDate) {
                      handleSelectDay(clickedDate);
                    }
                  }}
                >
                  <CartesianGrid strokeDasharray="4 4" stroke="rgba(22, 124, 217, 0.12)" />
                  <XAxis dataKey="label" tick={axisTickStyle} minTickGap={isCompactMobile ? 18 : 10} />
                  <YAxis tickFormatter={(value) => `${value}`} tick={axisTickStyle} width={isCompactMobile ? 28 : 40} />
                  <Tooltip formatter={(value) => `${formatNumber(value)} mg/dL`} labelFormatter={(_, payload) => (payload?.[0]?.payload?.date ? formatDate(payload[0].payload.date) : "")} />
                  <ReferenceLine y={70} stroke={HYPO_COLOR} strokeDasharray="5 5" />
                  <ReferenceLine y={180} stroke={HYPER_COLOR} strokeDasharray="5 5" />
                  <ReferenceLine y={250} stroke={HIGH_RISK_COLOR} strokeDasharray="5 5" />
                  <Line
                    type="monotone"
                    dataKey="avg_glucose"
                    name={t("patientDetail.trend.seriesAverage")}
                    stroke={TREND_COLOR}
                    strokeWidth={3}
                    activeDot={{ r: 7, onClick: (_, __, event) => event?.stopPropagation?.() }}
                    dot={(props) => {
                      const { cx, cy, payload, index } = props;
                      if (cx == null || cy == null || !payload?.date) {
                        return null;
                      }

                      const isActive = payload.date === selectedDay;
                        return (
                          <circle
                            key={`trend-dot-${payload.date}-${index ?? "item"}`}
                            cx={cx}
                            cy={cy}
                            r={isActive ? 6 : 4}
                            fill={isActive ? "#1eab69" : "#ffffff"}
                            stroke={TREND_COLOR}
                            strokeWidth={isActive ? 3 : 2}
                            style={{ cursor: "pointer" }}
                            onClick={() => handleSelectDay(payload.date)}
                          />
                      );
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : selectedDayEvents.length ? (
              <ResponsiveContainer width="100%" height={trendChartHeight}>
                <LineChart data={selectedDayEvents} margin={dayChartMargin}>
                  <CartesianGrid strokeDasharray="4 4" stroke="rgba(22, 124, 217, 0.12)" />
                  <XAxis dataKey="event_time" tick={axisTickStyle} minTickGap={isCompactMobile ? 16 : 10} />
                  <YAxis tickFormatter={(value) => `${value}`} tick={axisTickStyle} width={isCompactMobile ? 28 : 40} />
                  <Tooltip
                    formatter={(value) => `${formatNumber(value)} mg/dL`}
                    labelFormatter={(_, payload) =>
                      payload?.[0]?.payload
                        ? `${formatDate(payload[0].payload.event_date)} - ${payload[0].payload.event_time}`
                        : ""
                    }
                    contentStyle={{ borderRadius: "18px", borderColor: "rgba(22, 124, 217, 0.14)" }}
                  />
                  <ReferenceLine y={70} stroke={HYPO_COLOR} strokeDasharray="5 5" />
                  <ReferenceLine y={180} stroke={HYPER_COLOR} strokeDasharray="5 5" />
                  <ReferenceLine y={250} stroke={HIGH_RISK_COLOR} strokeDasharray="5 5" />
                  <Line type="monotone" dataKey="glucose_mg_dl" name={t("patientDetail.trend.seriesGlucose")} stroke={TREND_COLOR} strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <StateBlock
                title={t("patientDetail.trend.insufficientData.title")}
                description={t("patientDetail.trend.insufficientData.description")}
              />
            )}
          </div>
          <div className="react-chart-legend" aria-label={t("patientDetail.trend.chartLegendAriaLabel")}>
            {trendLegendItems.map((item) => (
              <div key={item.label} className="react-chart-legend__item">
                <span
                  className={`react-chart-legend__line${item.dashed ? " is-dashed" : ""}`}
                  style={{ "--legend-color": item.color }}
                  aria-hidden="true"
                />
                <small>{item.label}</small>
              </div>
            ))}
          </div>
          <div className="react-day-strip" role="list" aria-label={t("patientDetail.trend.dayStripAriaLabel")}>
            {availableDayDates.map((dateValue) => (
              <button
                key={dateValue}
                type="button"
                className={`react-day-pill${dateValue === selectedDay ? " is-active" : ""}`}
                onClick={() => handleSelectDay(dateValue)}
              >
                <strong>{formatShortDate(dateValue)}</strong>
                <small>{formatNumber(data.daily_indicators.find((indicator) => indicator.date === dateValue)?.avg_glucose)}</small>
              </button>
            ))}
          </div>
        </article>

        <aside className="react-patient-sidebar">
          <article className="react-panel react-panel--summary">
            <div className="react-panel__header">
              <div>
                <p className="react-eyebrow">{isDayMode && selectedDaySummary ? t("patientDetail.sidebar.eyebrowDay") : t("patientDetail.sidebar.eyebrowPeriod")}</p>
                <h2>{isDayMode && selectedDaySummary ? formatDate(selectedDaySummary.date) : t("patientDetail.sidebar.titlePeriod")}</h2>
                <p>
                  {isDayMode && selectedDaySummary
                    ? t("patientDetail.sidebar.bodyDay")
                    : t("patientDetail.sidebar.bodyPeriod")}
                </p>
              </div>
            </div>
            <div className="react-stat-grid">
              {overviewStats.map((stat) => stat.action === "atypical-days" ? (
                <AtypicalDaysPopup
                  key={stat.label}
                  patientId={patient.id}
                  appliedDates={requestedDates}
                  activeStart={requestedStart || filters.start_date || ""}
                  activeEnd={requestedEnd || filters.end_date || ""}
                  onApplyDates={applyAtypicalDates}
                  onClearDays={clearDaySelection}
                  renderTrigger={(openPopup, triggerRef) => (
                    <PatientStatCard
                      label={stat.label}
                      value={stat.value}
                      helper={stat.helper}
                      actionHint={stat.actionHint}
                      tone={stat.tone}
                      onClick={openPopup}
                      ariaLabel={`${stat.label}: ${stat.value}. ${stat.actionHint}`}
                      buttonRef={triggerRef}
                    />
                  )}
                />
              ) : (
                <PatientStatCard key={stat.label} label={stat.label} value={stat.value} helper={stat.helper} tone={stat.tone} />
              ))}
            </div>
            {!isDayMode && pendingAnalysisDays > 0 ? (
              <p className="react-pending-note" role="note">
                {t("patientDetail.hero.pendingAnalysisNote", { count: pendingAnalysisDays })}
              </p>
            ) : null}
          </article>
        </aside>
      </section>

      <section className="react-grid react-grid--detail-data">

        <article className="react-panel react-panel--wide">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">{t("patientDetail.dailyIndicators.eyebrow")}</p>
              <h2>{t("patientDetail.dailyIndicators.title")}</h2>
            </div>
          </div>
          {isCompactMobile ? (
            <div className="react-mobile-list" aria-label={t("patientDetail.dailyIndicators.eyebrow")}>
              {data.daily_indicators.map((indicator) => (
                <article
                  key={indicator.date}
                  className={`react-mobile-card react-mobile-card--interactive${indicator.date === selectedDay ? " is-selected" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelectDay(indicator.date)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      handleSelectDay(indicator.date);
                    }
                  }}
                >
                  <div className="react-mobile-card__header">
                    <div>
                      <span className="react-mobile-card__eyebrow">{t("patientDetail.dailyIndicators.date")}</span>
                      <h3>{formatDate(indicator.date)}</h3>
                    </div>
                    {indicator.analysis_pending ? (
                      <PendingAnalysisChip />
                    ) : (
                      <span className={`react-mobile-card__badge${indicator.anomaly_flag ? " is-alert" : ""}`}>
                        {indicator.anomaly_flag ? t("patientDetail.dailyIndicators.badgeAtypical") : t("patientDetail.dailyIndicators.badgeStable")}
                      </span>
                    )}
                  </div>
                  <div className="react-mobile-card__grid">
                    <MobileDetailField
                      label={t("patientDetail.dailyIndicators.avg")}
                      value={indicator.avg_glucose != null ? `${formatNumber(indicator.avg_glucose)} mg/dL` : "-"}
                    />
                    <MobileDetailField label={t("patientDetail.dailyIndicators.pctHypo")} value={formatNumber(indicator.pct_hypo, "%")} />
                    <MobileDetailField label={t("patientDetail.dailyIndicators.pctInRange")} value={formatNumber(indicator.pct_in_range, "%")} />
                    <MobileDetailField label={t("patientDetail.dailyIndicators.pctHyper")} value={formatNumber(indicator.pct_hyper, "%")} />
                    <MobileDetailField label={t("patientDetail.dailyIndicators.profile")} className="react-mobile-card__field--profile">
                      <ClusterProfileValue indicator={indicator} compact showGroup={false} />
                    </MobileDetailField>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="react-table-shell react-table-shell--daily-indicators">
              <table className="react-table react-table--daily-indicators">
                <thead>
                  <tr>
                    <th>{t("patientDetail.dailyIndicators.date")}</th>
                    <th>{t("patientDetail.dailyIndicators.avg")}</th>
                    <th>{t("patientDetail.dailyIndicators.pctHypo")}</th>
                    <th>{t("patientDetail.dailyIndicators.pctInRange")}</th>
                    <th>{t("patientDetail.dailyIndicators.pctHyper")}</th>
                    <th>{t("patientDetail.dailyIndicators.anomaly")}</th>
                    <th>{t("patientDetail.dailyIndicators.profile")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.daily_indicators.map((indicator) => (
                    <tr
                      key={indicator.date}
                      className={indicator.date === selectedDay ? "is-selected" : ""}
                      onClick={() => handleSelectDay(indicator.date)}
                    >
                      <td>{formatDate(indicator.date)}</td>
                      <td>{indicator.avg_glucose != null ? `${formatNumber(indicator.avg_glucose)} mg/dL` : "-"}</td>
                      <td>{formatNumber(indicator.pct_hypo, "%")}</td>
                      <td>{formatNumber(indicator.pct_in_range, "%")}</td>
                      <td>{formatNumber(indicator.pct_hyper, "%")}</td>
                      <td>{indicator.analysis_pending ? t("common.dash") : indicator.anomaly_flag ? t("common.yes") : t("common.no")}</td>
                      <td>
                        <div className="react-table-meta">
                          <ClusterProfileValue indicator={indicator} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <article className="react-panel react-panel--wide">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">{t("patientDetail.recentEvents.eyebrow")}</p>
              <h2>{t("patientDetail.recentEvents.title")}</h2>
            </div>
          </div>
          {isCompactMobile ? (
            <div className="react-mobile-list" aria-label={t("patientDetail.recentEvents.eyebrow")}>
              {recentEvents.map((event) => {
                const eventTypeLabel = enumLabel("eventType", event.event_type, event.event_type_label, t);
                const eventSubtypeLabel = enumLabel("eventSubtype", event.event_subtype, event.event_subtype_label, t);
                const contextLabel = enumLabel("context", event.context_label, event.context_label_display, t);

                return (
                  <article key={`${event.occurred_at}-${event.event_type}`} className="react-mobile-card">
                    <div className="react-mobile-card__header">
                      <div>
                        <span className="react-mobile-card__eyebrow">{t("patientDetail.recentEvents.when")}</span>
                        <h3>{formatPatientEventDateTime(event)}</h3>
                      </div>
                      <span className="react-mobile-card__badge" title={event.event_type || ""}>
                        {eventTypeLabel}
                      </span>
                    </div>
                    <div className="react-mobile-card__grid">
                      <MobileDetailField label={t("patientDetail.recentEvents.subtype")} value={eventSubtypeLabel} />
                      <MobileDetailField
                        label={t("patientDetail.recentEvents.value")}
                        value={
                          event.glucose_mg_dl != null
                            ? `${formatNumber(event.glucose_mg_dl)} mg/dL`
                            : event.numeric_value != null
                              ? formatNumber(event.numeric_value)
                              : "-"
                        }
                      />
                      <MobileDetailField label={t("patientDetail.recentEvents.context")} value={contextLabel} />
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="react-table-shell">
              <table className="react-table">
                <thead>
                  <tr>
                    <th>{t("patientDetail.recentEvents.when")}</th>
                    <th>{t("patientDetail.recentEvents.type")}</th>
                    <th>{t("patientDetail.recentEvents.subtype")}</th>
                    <th>{t("patientDetail.recentEvents.value")}</th>
                    <th>{t("patientDetail.recentEvents.context")}</th>
                  </tr>
                </thead>
                <tbody>
                  {recentEvents.map((event) => {
                    const eventTypeLabel = enumLabel("eventType", event.event_type, event.event_type_label, t);
                    const eventSubtypeLabel = enumLabel("eventSubtype", event.event_subtype, event.event_subtype_label, t);
                    const contextLabel = enumLabel("context", event.context_label, event.context_label_display, t);

                    return (
                      <tr key={`${event.occurred_at}-${event.event_type}`}>
                        <td>{formatPatientEventDateTime(event)}</td>
                        <td title={event.event_type || ""}>{eventTypeLabel}</td>
                        <td title={event.event_subtype || ""}>{eventSubtypeLabel}</td>
                        <td>
                          {event.glucose_mg_dl != null
                            ? `${formatNumber(event.glucose_mg_dl)} mg/dL`
                            : event.numeric_value != null
                              ? formatNumber(event.numeric_value)
                              : "-"}
                        </td>
                        <td title={event.context_label || ""}>{contextLabel}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}
