import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
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
import Pagination from "../components/Pagination";
import ConfirmDialog from "../components/ConfirmDialog";
import ManualGlucoseEntryForm from "../components/ManualGlucoseEntryForm";
import { ArrowLeftIcon, CalendarIcon, ChartLineIcon, ChevronDownIcon } from "../components/Icons";
import { useAuth } from "../contexts/AuthContext";
import useMediaQuery from "../hooks/useMediaQuery";
import usePrefersReducedMotion from "../hooks/usePrefersReducedMotion";
import useDocumentTitle from "../hooks/useDocumentTitle";

const RANGE_TONES = ["low", "in-range", "high"];
const TREND_REFERENCE_TICKS = [0, 70, 180, 250];
const HOURLY_TICKS = Array.from({ length: 24 }, (_, index) => index);
// Each reference line has its own dash pattern so the thresholds stay distinguishable without color.
const REFERENCE_DASH = { hypo: "2 4", hyper: "9 4", highRisk: "14 4 3 4" };
const MAX_SUMMARY_HOURS = 3;
// Recharts paints SVG attributes, which cannot resolve var(); the tokens are read once from :root.
// The fallbacks only cover a missing stylesheet and mirror the token values in styles.css.
const CHART_TOKENS = {
  trend: ["--react-blue", "#167cd9"],
  low: ["--glyco-low", "#e35d73"],
  inRange: ["--glyco-in-range", "#1eab69"],
  high: ["--glyco-high", "#f4a93d"],
  veryHigh: ["--glyco-very-high", "#8a5300"],
  text: ["--react-text", "#17304a"],
  muted: ["--react-muted", "#56677e"],
  surface: ["--react-surface-solid", "#ffffff"],
  grid: ["--tint-blue-12", "rgba(22, 124, 217, 0.12)"],
  border: ["--react-border", "rgba(22, 124, 217, 0.14)"]
};
let chartPaletteCache = null;

function chartPalette() {
  if (chartPaletteCache) return chartPaletteCache;
  const styles = typeof window !== "undefined" ? window.getComputedStyle(document.documentElement) : null;
  const palette = Object.fromEntries(
    Object.entries(CHART_TOKENS).map(([key, [token, fallback]]) => [key, styles?.getPropertyValue(token).trim() || fallback])
  );
  if (styles?.getPropertyValue("--react-blue").trim()) chartPaletteCache = palette;
  return palette;
}

// A stretch longer than this without readings breaks the trend line instead of bridging it.
const TREND_GAP_DAYS = 14;
// On phones a long period is drawn as weekly averages; the day strip and tables keep every day.
const WEEKLY_TREND_MIN_DAYS = 60;
const DAY_MS = 86400000;
const dayTime = (value) => Date.parse(`${value}T00:00:00Z`);

function weekStartOf(value) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

function buildTrendSeries(indicators, weekly) {
  const days = [...indicators].sort((left, right) => (left.date < right.date ? -1 : left.date > right.date ? 1 : 0));
  let points = days.map((indicator) => ({ ...indicator, key: indicator.date, startDate: indicator.date, endDate: indicator.date, dates: [indicator.date] }));
  if (weekly) {
    const groups = new Map();
    for (const indicator of days) {
      const key = weekStartOf(indicator.date);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(indicator);
    }
    points = Array.from(groups.entries()).map(([key, items]) => {
      const values = items.map((item) => item.avg_glucose).filter((value) => value !== null && value !== undefined);
      const withValue = items.filter((item) => item.avg_glucose !== null && item.avg_glucose !== undefined);
      return {
        key,
        weekly: true,
        date: (withValue.at(-1) || items.at(-1)).date,
        startDate: items[0].date,
        endDate: items.at(-1).date,
        dates: items.map((item) => item.date),
        avg_glucose: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
      };
    });
  }
  const series = [];
  const gaps = [];
  points.forEach((point, index) => {
    const previous = points[index - 1];
    if (previous && (dayTime(point.startDate) - dayTime(previous.endDate)) / DAY_MS > TREND_GAP_DAYS) {
      // A null point between both sides makes Recharts leave the line open across the gap.
      const gap = { key: `gap-${index}`, gap: true, gapStart: previous.endDate, gapEnd: point.startDate, avg_glucose: null };
      gaps.push(gap);
      series.push(gap);
    }
    series.push(point);
  });
  const first = days[0]?.date;
  const last = days.at(-1)?.date;
  const spansYears = Boolean(first && last && (dayTime(last) - dayTime(first)) / DAY_MS > 365);
  return { series, gaps, spansYears };
}

function peakHours(rows, key) {
  const peak = Math.max(0, ...rows.map((row) => row[key]));
  if (!peak) return [];
  return rows.filter((row) => row[key] === peak).slice(0, MAX_SUMMARY_HOURS).map((row) => row.hour);
}
// Below this many readings a smoothed curve would invent values between measurements.
const SMOOTH_CURVE_MIN_READINGS = 6;

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
  return t("common.dash");
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
  const tooltipId = useId();

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
        aria-describedby={tooltipId}
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((current) => !current);
        }}
      >
        i
      </button>
      <span className="react-info-tooltip__content" role="tooltip" id={tooltipId}>
        {content}
      </span>
    </span>
  );
}

function PendingAnalysisChip() {
  const { t } = useTranslation();
  return <span className="react-badge react-badge--pending react-badge--compact">{t("patientDetail.dailyIndicators.badgePending")}</span>;
}

function ClusterProfileValue({ indicator, compact = false }) {
  const { t } = useTranslation();
  if (indicator?.analysis_pending) {
    return <PendingAnalysisChip />;
  }
  const profileLabel = getClusterProfileLabel(indicator, t);
  const profileDescription = getClusterProfileDescription(indicator, t);

  return (
    <span className={`react-cluster-profile${compact ? " is-compact" : ""}`}>
      <span className="react-cluster-profile__row">
        <span className="react-cluster-profile__label">{profileLabel}</span>
        <InfoTooltip content={profileDescription} label={t("common.explain", { label: profileLabel })} />
      </span>
    </span>
  );
}

function KeyFigure({ label, value, unit, helper }) {
  return (
    <div className="react-figure">
      <span className="react-figure__label">{label}</span>
      <strong className="react-figure__value">
        {value}
        {unit ? <small>{unit}</small> : null}
      </strong>
      {helper ? <span className="react-figure__helper">{helper}</span> : null}
    </div>
  );
}

// The accessible name keeps the "{label}: {value}. {action}" pattern the atypical-days E2E locator relies on.
function AtypicalDaysTrigger({ label, value, helper, actionHint, onClick, buttonRef, compact = false }) {
  if (compact) {
    return (
      <button
        type="button"
        className="react-button react-button--ghost"
        ref={buttonRef}
        onClick={onClick}
        aria-haspopup="dialog"
        aria-label={`${label}: ${value}. ${actionHint}`}
      >
        {`${label}: ${value}`}
      </button>
    );
  }
  return (
    <button
      type="button"
      className="react-figure react-figure--action"
      ref={buttonRef}
      onClick={onClick}
      aria-haspopup="dialog"
      aria-label={`${label}: ${value}. ${actionHint}`}
    >
      <span className="react-figure__label">{label}</span>
      <strong className="react-figure__value">{value}</strong>
      {helper ? <span className="react-figure__helper">{helper}</span> : null}
      <span className="react-figure__action">{actionHint}</span>
    </button>
  );
}

const DEFAULT_WINDOW_DAYS = 30;

// Mirrors the backend default (reports._resolve_default_window): the last 30 days up to the latest available date,
// or up to the latest analysed day when the newest days still await analysis (default_* report that window).
function isDefaultDetailWindow(filters) {
  const { start_date: start, end_date: end, available_start_date: availableStart, available_end_date: availableEnd } = filters ?? {};
  if (filters?.default_start_date && filters?.default_end_date) {
    return start === filters.default_start_date && end === filters.default_end_date;
  }
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
  const location = useLocation();
  const navigate = useNavigate();
  const isDoctorView = Boolean(session?.doctor?.id);
  useDocumentTitle(t(isDoctorView ? "documentTitle.patientDetail" : "documentTitle.myPanel"));
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
  const isCompactMobile = useMediaQuery("(max-width: 640px)");
  const reducedMotion = usePrefersReducedMotion();
  const [periodFormOverride, setPeriodFormOverride] = useState(null);
  const [manualOpen, setManualOpen] = useState(() => location.hash === "#new-reading");
  const [entrySaved, setEntrySaved] = useState(false);
  // The period sync below rewrites the URL (replace) and drops the hash, so the "#new-reading" intent is kept here.
  const pendingNewReadingRef = useRef(location.hash === "#new-reading");
  const [reloadToken, setReloadToken] = useState(0);
  const [indicatorPage, setIndicatorPage] = useState(1);
  const [indicatorPageSize, setIndicatorPageSize] = useState(10);
  const [eventPage, setEventPage] = useState(1);
  const [eventPageSize, setEventPageSize] = useState(10);
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
    fetchDoctorLinks({ status: "active", patient_id: patientId, page: 1, page_size: 10 })
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
    setPeriodFormOverride(null);
  }, [patientId]);

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

  const requestKey = `${patientId}:${requestedStart || ""}:${requestedEnd || ""}:${requestedDatesParam}:${reloadToken}:${indicatorPage}:${indicatorPageSize}:${eventPage}:${eventPageSize}`;

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
      ? { dates: requestedDates, indicatorPage, indicatorPageSize, eventPage, eventPageSize }
      : { startDate: requestedStart, endDate: requestedEnd, indicatorPage, indicatorPageSize, eventPage, eventPageSize };
    fetchPatientDetail(patientId, detailRequest)
      .then((payload) => {
        if (!active) {
          return;
        }
        // With exact days the API reports no period, so the user's period stays in the URL untouched.
        const periodStart = hasExactDates ? requestedStart || preservedRangeRef.current?.start : payload.filters.start_date;
        const periodEnd = hasExactDates ? requestedEnd || preservedRangeRef.current?.end : payload.filters.end_date;
        setData(payload);
        if (payload.daily_indicators_pagination?.page !== indicatorPage) setIndicatorPage(payload.daily_indicators_pagination.page);
        if (payload.recent_events_pagination?.page !== eventPage) setEventPage(payload.recent_events_pagination.page);
        setDraftStartDate(periodStart || "");
        setDraftEndDate(periodEnd || "");
        lastResolvedRequestRef.current = `${patientId}:${periodStart || ""}:${periodEnd || ""}:${requestedDatesParam}:${reloadToken}:${indicatorPage}:${indicatorPageSize}:${eventPage}:${eventPageSize}`;

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
  }, [patientId, requestedStart, requestedEnd, requestedDates, requestedDatesParam, requestKey, reloadToken, data, searchParams, setSearchParams, indicatorPage, indicatorPageSize, eventPage, eventPageSize]);

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
      { name: t("patientDetail.distribution.hypo"), range: t("patientDetail.distribution.hypoRange"), value: data.summary.pct_hypo },
      { name: t("patientDetail.distribution.inRange"), range: t("patientDetail.distribution.inRangeRange"), value: data.summary.pct_in_range },
      { name: t("patientDetail.distribution.hyper"), range: t("patientDetail.distribution.hyperRange"), value: data.summary.pct_hyper }
    ];
  }, [data, t]);

  const selectedDayDistribution = useMemo(() => {
    if (!selectedDaySummary) {
      return [];
    }

    return [
      { name: t("patientDetail.distribution.hypo"), range: t("patientDetail.distribution.hypoRange"), value: selectedDaySummary.pctHypo, count: selectedDaySummary.lowEventsCount },
      {
        name: t("patientDetail.distribution.inRange"),
        range: t("patientDetail.distribution.inRangeRange"),
        value: selectedDaySummary.pctInRange,
        count: selectedDaySummary.measurementCount - selectedDaySummary.lowEventsCount - selectedDaySummary.highEventsCount
      },
      { name: t("patientDetail.distribution.hyper"), range: t("patientDetail.distribution.hyperRange"), value: selectedDaySummary.pctHyper, count: selectedDaySummary.highEventsCount }
    ];
  }, [selectedDaySummary, t]);

  const hourlyExtremes = useMemo(
    () =>
      HOURLY_TICKS.map((hour) => ({
        hour,
        lowCount: hourlyLows.find((item) => item.hour === hour)?.count ?? 0,
        highCount: hourlyHighs250.find((item) => item.hour === hour)?.count ?? 0,
      })),
    [hourlyHighs250, hourlyLows]
  );

  // Day mode counts the selected day's own readings with the same thresholds the API uses for the period.
  const dayHourlyExtremes = useMemo(
    () =>
      HOURLY_TICKS.map((hour) => {
        const atHour = selectedDayEvents.filter((event) => Number.parseInt(String(event.event_time || "").slice(0, 2), 10) === hour);
        return {
          hour,
          lowCount: atHour.filter((event) => event.glucose_mg_dl != null && event.glucose_mg_dl < 70).length,
          highCount: atHour.filter((event) => event.glucose_mg_dl != null && event.glucose_mg_dl > 250).length,
        };
      }),
    [selectedDayEvents]
  );

  const weeklyTrend = isCompactMobile && chartData.length > WEEKLY_TREND_MIN_DAYS;
  const trendSeries = useMemo(() => buildTrendSeries(chartData, weeklyTrend), [chartData, weeklyTrend]);

  // The day strip opens on the selected day, or on the most recent one; only the strip scrolls, never the page.
  const dayStripRef = useRef(null);
  useEffect(() => {
    const strip = dayStripRef.current;
    if (!strip) return;
    const target = strip.querySelector(".react-day-pill.is-active") || strip.lastElementChild;
    if (!target) return;
    const stripBox = strip.getBoundingClientRect();
    const targetBox = target.getBoundingClientRect();
    const inset = 6;
    if (targetBox.right > stripBox.right - inset) {
      strip.scrollLeft += targetBox.right - stripBox.right + inset;
    } else if (targetBox.left < stripBox.left + inset) {
      strip.scrollLeft -= stripBox.left + inset - targetBox.left;
    }
  }, [selectedDay, availableDayDates, loading]);

  // A "#new-reading" link opens the entry dialog once per navigation, after the panel data arrives.
  useEffect(() => {
    if (location.hash === "#new-reading") pendingNewReadingRef.current = true;
  }, [location.hash, location.key]);

  useEffect(() => {
    if (!data || !pendingNewReadingRef.current) return;
    pendingNewReadingRef.current = false;
    setManualOpen(true);
  }, [data, location.hash, location.key]);

  useEffect(() => {
    if (!entrySaved) return undefined;
    const timer = setTimeout(() => setEntrySaved(false), 6000);
    return () => clearTimeout(timer);
  }, [entrySaved]);

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

  function showRecentReadings() {
    const latestPending = data?.filters?.latest_pending_date;
    if (!latestPending) return;
    const windowStart = new Date(`${latestPending}T00:00:00Z`);
    windowStart.setUTCDate(windowStart.getUTCDate() - (DEFAULT_WINDOW_DAYS - 1));
    let startDate = windowStart.toISOString().slice(0, 10);
    const availableStart = data?.filters?.available_start_date;
    if (availableStart && startDate < availableStart) startDate = availableStart;
    const next = new URLSearchParams(searchParams);
    next.delete("dates");
    next.set("start_date", startDate);
    next.set("end_date", latestPending);
    setPreservedRange(null);
    lastResolvedRequestRef.current = "";
    setSelectedDay("");
    setViewMode("period");
    setSearchParams(next);
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
    setEntrySaved(true);
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
    return (
      <div role="alert">
        <StateBlock title={t("patientDetail.error.title")} description={t("patientDetail.error.description")} tone="danger">
          <button type="button" className="react-button react-button--ghost react-button--compact" onClick={() => setReloadToken((current) => current + 1)}>
            {t("common.retry")}
          </button>
        </StateBlock>
      </div>
    );
  }

  const { patient, filters, recent_events: recentEvents } = data;
  const dailyIndicatorsPage = data.daily_indicators_page || data.daily_indicators;
  const activeDistributionData = isDayMode && selectedDaySummary ? selectedDayDistribution : distributionData;
  const distributionChartHeight = isCompactMobile ? 148 : 168;
  const dropHoursChartHeight = isCompactMobile ? 180 : 200;
  const trendChartHeight = isCompactMobile ? 260 : 340;
  const trendChartMargin = isCompactMobile
    ? { top: 8, right: 4, left: 0, bottom: 0 }
    : { top: 8, right: 12, left: 0, bottom: 0 };
  const pieInnerRadius = isCompactMobile ? 50 : 58;
  const pieOuterRadius = isCompactMobile ? 68 : 78;
  const axisTickStyle = { fontSize: 12 };
  const hourlyAxisTickStyle = { fontSize: 12 };
  const palette = chartPalette();
  const pieColors = [palette.low, palette.inRange, palette.high];
  const referenceLines = [
    { y: 70, color: palette.low, dash: REFERENCE_DASH.hypo },
    { y: 180, color: palette.high, dash: REFERENCE_DASH.hyper },
    { y: 250, color: palette.veryHigh, dash: REFERENCE_DASH.highRisk }
  ];
  const tooltipContentStyle = { fontSize: 14, borderRadius: 18, borderColor: palette.border };
  const tooltipLabelStyle = { fontSize: 14, fontWeight: 700 };
  const trendValues = isDayMode
    ? selectedDayEvents.map((event) => event.glucose_mg_dl)
    : chartData.map((indicator) => indicator.avg_glucose);
  const trendMax = Math.max(0, ...trendValues.filter((value) => value !== null && value !== undefined));
  // Round top of the scale, far enough above 250 that both tick labels stay readable.
  const trendTop = Math.max(300, Math.ceil(trendMax / 50) * 50);
  const trendYAxisDomain = [0, trendTop];
  const trendYAxisTicks = [...TREND_REFERENCE_TICKS, trendTop];
  const hourlyAxisTicks = isCompactMobile
    ? HOURLY_TICKS.filter((hour) => hour % 3 === 0)
    : HOURLY_TICKS;
  const isSparseDay = isDayMode && selectedDayEvents.length > 0 && selectedDayEvents.length < SMOOTH_CURVE_MIN_READINGS;
  const trendLegendItems = [
    {
      label: isDayMode
        ? t("patientDetail.trend.legendDayCurveCount", { count: selectedDayEvents.length })
        : weeklyTrend
          ? t("patientDetail.trend.legendWeeklyAvg")
          : t("patientDetail.trend.legendDailyAvg"),
      color: palette.trend,
      dash: null,
    },
    {
      label: t("patientDetail.trend.legendHypo"),
      color: palette.low,
      dash: REFERENCE_DASH.hypo,
    },
    {
      label: t("patientDetail.trend.legendHyperTarget"),
      color: palette.high,
      dash: REFERENCE_DASH.hyper,
    },
    {
      label: t("patientDetail.trend.legendHighRisk"),
      color: palette.veryHigh,
      dash: REFERENCE_DASH.highRisk,
    },
  ];
  const trendTickFormat = trendSeries.spansYears
    ? new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "2-digit" })
    : new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit" });
  const formatTrendTick = (key) => (typeof key === "string" && !key.startsWith("gap-") ? trendTickFormat.format(new Date(`${key}T00:00:00`)) : "");
  const formatTrendTooltipLabel = (point) => {
    if (!point) return "";
    if (point.gap) return t("patientDetail.trend.gapTooltip", { start: formatDate(point.gapStart), end: formatDate(point.gapEnd) });
    if (point.weekly) return t("patientDetail.trend.weekOf", { start: formatDate(point.startDate), end: formatDate(point.endDate) });
    return formatDate(point.date);
  };
  const trendGapNote = trendSeries.gaps.length === 1
    ? t("patientDetail.trend.gapNote_one", { start: formatDate(trendSeries.gaps[0].gapStart), end: formatDate(trendSeries.gaps[0].gapEnd) })
    : trendSeries.gaps.length > 1
      ? t("patientDetail.trend.gapNote_other", { count: trendSeries.gaps.length })
      : "";
  const activeHourlyExtremes = isDayMode && selectedDay ? dayHourlyExtremes : hourlyExtremes;
  const formatHourList = (hours) => {
    const labels = hours.map((hour) => `${String(hour).padStart(2, "0")}h`);
    return typeof Intl.ListFormat === "function"
      ? new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(labels)
      : labels.join(", ");
  };
  const extremesTotals = activeHourlyExtremes.reduce(
    (totals, row) => ({ low: totals.low + row.lowCount, high: totals.high + row.highCount }),
    { low: 0, high: 0 }
  );
  const extremesSummary = [
    extremesTotals.low
      ? t("patientDetail.extremeEvents.summaryLow", { count: extremesTotals.low, hours: formatHourList(peakHours(activeHourlyExtremes, "lowCount")) })
      : t("patientDetail.extremeEvents.summaryLowNone"),
    extremesTotals.high
      ? t("patientDetail.extremeEvents.summaryHigh", { count: extremesTotals.high, hours: formatHourList(peakHours(activeHourlyExtremes, "highCount")) })
      : t("patientDetail.extremeEvents.summaryHighNone")
  ].join(" ");
  function handleSelectDay(dateValue) {
    setSelectedDay(dateValue);
    setViewMode("day");
  }

  function handleShowPeriod() {
    setViewMode("period");
  }

  function openManualEntry() {
    setEntrySaved(false);
    setManualOpen(true);
  }

  const preservedRange = preservedRangeRef.current;
  const coveringRange = requestedDates.length && preservedRange ? rangeCoveringDates(preservedRange, requestedDates) : null;
  const periodAdjustment = coveringRange?.adjusted ? coveringRange : null;
  const isDefaultWindow = isDefaultDetailWindow(filters);
  const isAnalysedFallbackWindow = isDefaultWindow && Boolean(filters.window_fallback);
  const pendingOutsideWindow = requestedDates.length ? 0 : filters.pending_outside_window ?? 0;
  const periodDays = filters.start_date && filters.end_date
    ? Math.round((Date.parse(`${filters.end_date}T00:00:00Z`) - Date.parse(`${filters.start_date}T00:00:00Z`)) / 86400000) + 1
    : 0;
  const periodFormOpen = periodFormOverride ?? (requestedDates.length > 0 || !isDefaultWindow);

  const isOwnPatientView = Boolean(session?.patient?.id && session.patient.id === patient.id);
  const pendingAnalysisDays = summary?.pending_analysis_days ?? 0;
  const analysedDays = (summary?.days_observed ?? 0) - pendingAnalysisDays;
  const hasAnalysedDays = analysedDays > 0 && chartData.some((indicator) => indicator.avg_glucose !== null && indicator.avg_glucose !== undefined);
  const showEmptyWindow = !isDayMode && !hasAnalysedDays;
  const isFullHistory = Boolean(
    filters.available_start_date &&
      filters.start_date === filters.available_start_date &&
      filters.end_date === filters.available_end_date
  );
  const canShowFullHistory = Boolean(filters.available_start_date && filters.available_end_date && (!isFullHistory || requestedDates.length > 0));
  const reportUrl = patientReportPdfUrl(patient.id, {
    startDate: filters.start_date,
    endDate: filters.end_date,
    lang: locale
  });
  const metaParts = [
    !isOwnPatientView && patient.source_file ? t("patientDetail.hero.sourceFile", { file: patient.source_file }) : null,
    t("patientDetail.hero.measurementsBadge", { count: summary.glucose_measurements })
  ].filter(Boolean);
  const atypicalLabel = t("patientDetail.stats.anomalyDays.label");
  const atypicalValue = summary?.anomaly_days ?? "-";
  const atypicalHint = t("patientDetail.stats.anomalyDays.action");
  const dailyTotal = data.daily_indicators_pagination?.total ?? dailyIndicatorsPage.length;
  const eventsTotal = data.recent_events_pagination?.total ?? recentEvents.length;

  function renderAtypicalTrigger(compact) {
    return (
      <AtypicalDaysPopup
        patientId={patient.id}
        appliedDates={requestedDates}
        activeStart={requestedStart || filters.start_date || ""}
        activeEnd={requestedEnd || filters.end_date || ""}
        onApplyDates={applyAtypicalDates}
        onClearDays={clearDaySelection}
        renderTrigger={(openPopup, triggerRef) => (
          <AtypicalDaysTrigger
            label={atypicalLabel}
            value={atypicalValue}
            helper={t(isOwnPatientView ? "patientDetail.stats.anomalyDays.helperPatient" : "patientDetail.stats.anomalyDays.helper")}
            actionHint={atypicalHint}
            onClick={openPopup}
            buttonRef={triggerRef}
            compact={compact}
          />
        )}
      />
    );
  }

  const revokeDialog = (
    <ConfirmDialog
      open={revokeOpen && Boolean(doctorLink)}
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

  const renderPagination = (meta, pageSize, setPage, setPageSize) =>
    meta?.total > 0 ? (
      <div className="react-panel__footer">
        <Pagination
          page={meta.page}
          pages={meta.pages}
          count={meta.total}
          pageSize={pageSize}
          onPageChange={(nextPage) => { silentReloadRef.current = true; setPage(nextPage); }}
          onPageSizeChange={(size) => { silentReloadRef.current = true; setPageSize(size); setPage(1); }}
        />
      </div>
    ) : null;

  const dailyIndicatorsPagination = renderPagination(data.daily_indicators_pagination, indicatorPageSize, setIndicatorPage, setIndicatorPageSize);
  const recentEventsPagination = renderPagination(data.recent_events_pagination, eventPageSize, setEventPage, setEventPageSize);

  // Every record here is a glucose reading in practice and the subtype repeats the context, so one
  // "Context" column carries both; a non-glucose event still names its type first.
  const eventContextLabel = (event) => {
    const contextLabel = enumLabel("context", event.context_label, event.context_label_display, t);
    const subtypeLabel = enumLabel("eventSubtype", event.event_subtype, event.event_subtype_label, t);
    const typeLabel = event.event_type && event.event_type !== "glucose_measurement"
      ? enumLabel("eventType", event.event_type, event.event_type_label, t)
      : "";
    const detail = contextLabel && contextLabel !== "-" ? contextLabel : subtypeLabel;
    return [typeLabel, detail].filter((value) => value && value !== "-").join(" · ");
  };

  const formatEventValue = (event) =>
    event.glucose_mg_dl != null
      ? `${formatNumber(event.glucose_mg_dl)} mg/dL`
      : event.numeric_value != null
        ? formatNumber(event.numeric_value)
        : "-";

  const dailyIndicatorRows = (
    <ul className="react-detail-rows" aria-label={t("patientDetail.dailyIndicators.title")}>
      {dailyIndicatorsPage.map((indicator) => {
        const isSelected = indicator.date === selectedDay;
        return (
          <li key={indicator.date} className={`react-detail-row react-detail-row--selectable${isSelected ? " is-selected" : ""}`}>
            <div className="react-detail-row__head">
              <button
                type="button"
                className="react-detail-row__select"
                aria-pressed={isSelected}
                onClick={() => handleSelectDay(indicator.date)}
              >
                {formatDate(indicator.date)}
              </button>
              {indicator.analysis_pending ? (
                <PendingAnalysisChip />
              ) : indicator.anomaly_flag ? (
                <span className="react-badge react-badge--atypical react-badge--compact">{t("patientDetail.dailyIndicators.badgeAtypical")}</span>
              ) : null}
            </div>
            {indicator.analysis_pending ? null : (
              <>
                <p className="react-detail-row__numbers">
                  <span>{t("patientDetail.dailyIndicators.avg")} <strong>{indicator.avg_glucose != null ? `${formatNumber(indicator.avg_glucose)} mg/dL` : "-"}</strong></span>
                  <span>{t("patientDetail.dailyIndicators.pctHypo")} <strong>{formatNumber(indicator.pct_hypo, "%")}</strong></span>
                  <span>{t("patientDetail.dailyIndicators.pctInRange")} <strong>{formatNumber(indicator.pct_in_range, "%")}</strong></span>
                  <span>{t("patientDetail.dailyIndicators.pctHyper")} <strong>{formatNumber(indicator.pct_hyper, "%")}</strong></span>
                </p>
                <div className="react-detail-row__profile">
                  <span>{t("patientDetail.dailyIndicators.profile")}</span>
                  <ClusterProfileValue indicator={indicator} compact />
                </div>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );

  const recentEventRows = (
    <ul className="react-detail-rows" aria-label={t("patientDetail.recentEvents.title")}>
      {recentEvents.map((event) => {
        const context = eventContextLabel(event);
        return (
          <li key={`${event.occurred_at}-${event.event_type}`} className="react-detail-row">
            <div className="react-detail-row__head">
              <span className="react-detail-row__title">{formatPatientEventDateTime(event)}</span>
              <strong className="react-detail-row__value">{formatEventValue(event)}</strong>
            </div>
            {context ? <p className="react-detail-row__meta">{context}</p> : null}
          </li>
        );
      })}
    </ul>
  );

  return (
    <div className="react-page react-page--patient-detail">
      {revokeDialog}
      <header className="react-page-header react-detail-header">
        <Link to="/dashboard" className="react-back-link">
          <ArrowLeftIcon />
          {isOwnPatientView ? t("patientDetail.hero.backHome") : t("patientDetail.hero.backToOverview")}
        </Link>
        <div className="react-detail-header__row">
          <div className="react-detail-header__copy">
            <h1>{patient.display_name}</h1>
            <p className="react-detail-header__meta">{metaParts.join(" · ")}</p>
          </div>
          <div className="react-actions react-detail-header__actions">
            {isOwnPatientView ? (
              <button type="button" className="react-button" onClick={openManualEntry}>
                {t("patientDetail.hero.newReading")}
              </button>
            ) : null}
            <a
              className={`react-button${isOwnPatientView ? " react-button--ghost" : ""}`}
              href={reportUrl || "#"}
              target="_blank"
              rel="noreferrer"
            >
              {t("patientDetail.hero.downloadReport")}
            </a>
          </div>
        </div>
        <p className="react-form-message is-success react-detail-header__saved" role="status">
          {entrySaved ? t("manualEntry.success") : ""}
        </p>
      </header>

      <section className="react-panel react-period-bar" aria-label={t("patientDetail.hero.periodAnalyzed")}>
        <div className="react-period-bar__main">
          <div className="react-period-bar__summary" data-testid="period-summary">
            {requestedDates.length > 0 ? (
              <>
                <h2 className="react-period-bar__range">{t("patientDetail.hero.selectedDays", { count: requestedDates.length })}</h2>
                {requestedStart && requestedEnd ? (
                  <p>{t("patientDetail.hero.referencePeriod", { start: formatDate(requestedStart), end: formatDate(requestedEnd) })}</p>
                ) : null}
              </>
            ) : (
              <>
                <h2 className="react-period-bar__range">
                  {t("patientDetail.periodBar.range", { start: formatDate(filters.start_date), end: formatDate(filters.end_date) })}
                </h2>
                <p>
                  {isAnalysedFallbackWindow
                    ? t("patientDetail.hero.latestAnalysedWindow")
                    : isDefaultWindow
                      ? t("patientDetail.hero.defaultWindow")
                      : isFullHistory
                        ? t("patientDetail.hero.fullHistory")
                        : t("patientDetail.hero.customWindow", { count: periodDays })}
                </p>
              </>
            )}
            {filters.available_start_date && filters.available_end_date ? (
              <p data-testid="available-period">
                {t("patientDetail.hero.availablePeriod", {
                  start: formatDate(filters.available_start_date),
                  end: formatDate(filters.available_end_date)
                })}
              </p>
            ) : null}
          </div>
          <div className="react-actions react-period-bar__actions">
            <button
              type="button"
              className="react-button react-button--ghost react-disclosure-toggle"
              aria-expanded={periodFormOpen}
              aria-controls="period-form"
              onClick={() => setPeriodFormOverride(!periodFormOpen)}
            >
              <span>{t("patientDetail.filter.toggle")}</span>
              <ChevronDownIcon />
            </button>
            {canShowFullHistory && !showEmptyWindow ? (
              <button type="button" className="react-button react-button--ghost" onClick={showFullHistory}>
                {t("patientDetail.hero.viewAllHistory")}
              </button>
            ) : null}
          </div>
        </div>
        {periodFormOpen ? (
          <form id="period-form" className="react-filter-form react-period-bar__form" onSubmit={applyRange}>
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
                aria-describedby={hasInvalidRange || !hasPendingFilterChange ? "period-form-hint" : undefined}
              >
                {t("patientDetail.filter.apply")}
              </button>
            </div>
            {hasInvalidRange ? (
              <p id="period-form-hint" className="react-period-bar__hint is-error" role="alert">{t("patientDetail.filter.invalidRange")}</p>
            ) : !hasPendingFilterChange ? (
              <p id="period-form-hint" className="react-period-bar__hint">{t("patientDetail.filter.applyHint")}</p>
            ) : null}
          </form>
        ) : null}
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
        {pendingAnalysisDays > 0 ? (
          <p className="react-pending-note" role="note">
            {t("patientDetail.hero.pendingAnalysisNote", { count: pendingAnalysisDays })}
          </p>
        ) : null}
        {pendingOutsideWindow > 0 ? (
          <p className="react-pending-note" role="note" data-testid="pending-outside-window">
            <span>{t("patientDetail.hero.pendingOutsideNote", { count: pendingOutsideWindow })}</span>
            {filters.latest_pending_date ? (
              <button type="button" className="react-button react-button--text" onClick={showRecentReadings}>
                {t("patientDetail.hero.viewRecentReadings")}
              </button>
            ) : null}
          </p>
        ) : null}
      </section>

      {showEmptyWindow ? (
        <section className="react-empty-window">
          <StateBlock icon={<CalendarIcon />} title={t("patientDetail.emptyWindow.title")} description={t("patientDetail.emptyWindow.description")}>
            <div className="react-actions react-empty-window__actions">
              {canShowFullHistory ? (
                <button type="button" className="react-button" onClick={showFullHistory}>
                  {t("patientDetail.hero.viewAllHistory")}
                </button>
              ) : null}
              {renderAtypicalTrigger(true)}
            </div>
          </StateBlock>
        </section>
      ) : (
        <>
          <section className="react-panel react-period-summary" aria-labelledby="period-summary-title">
            <div className="react-panel__header">
              <div>
                <h2 id="period-summary-title">
                  {isDayMode && selectedDaySummary
                    ? t("patientDetail.summary.titleDay", { date: formatDate(selectedDaySummary.date) })
                    : t("patientDetail.summary.titlePeriod")}
                </h2>
                <p>{isDayMode && selectedDaySummary ? t("patientDetail.sidebar.bodyDay") : t("patientDetail.sidebar.bodyPeriod")}</p>
              </div>
            </div>
            <div className="react-period-summary__body">
              <div className="react-period-summary__figures">
                {isDayMode && selectedDaySummary ? (
                  <>
                    <KeyFigure
                      label={t("patientDetail.stats.avgDay.label")}
                      value={formatNumber(selectedDaySummary.avgGlucose)}
                      unit="mg/dL"
                    />
                    <KeyFigure
                      label={t("patientDetail.stats.measurements.label")}
                      value={selectedDaySummary.measurementCount}
                      helper={t("patientDetail.stats.measurements.helper")}
                    />
                  </>
                ) : (
                  <>
                    <KeyFigure
                      label={t("patientDetail.stats.avgGlucose.label")}
                      value={formatNumber(summary?.avg_glucose)}
                      unit="mg/dL"
                      helper={t("patientDetail.stats.avgGlucose.helper")}
                    />
                    <KeyFigure
                      label={t("patientDetail.stats.daysObserved.label")}
                      value={summary?.days_observed ?? "-"}
                      helper={t("patientDetail.stats.daysObserved.helper")}
                    />
                  </>
                )}
                {renderAtypicalTrigger(false)}
              </div>
              <div className="react-period-summary__range">
                <h3>{t("patientDetail.summary.timeInRange")}</h3>
                <div className="react-period-summary__range-body">
                  <div className="react-distribution-visual" aria-hidden="true">
                    <ResponsiveContainer width="100%" height={distributionChartHeight}>
                      <PieChart>
                        <Pie
                          data={activeDistributionData}
                          dataKey="value"
                          innerRadius={pieInnerRadius}
                          outerRadius={pieOuterRadius}
                          paddingAngle={3}
                          isAnimationActive={false}
                        >
                          {activeDistributionData.map((entry, index) => (
                            <Cell key={entry.name} fill={pieColors[index]} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="react-distribution-legend">
                    {activeDistributionData.map((item, index) => (
                      <li key={item.name} className="react-distribution-legend__item">
                        <span className={`react-distribution-legend__dot is-${RANGE_TONES[index]}`} aria-hidden="true" />
                        <span className="react-distribution-legend__label">
                          {item.name}
                          <small>
                            {item.range}
                            {item.count !== undefined ? ` · ${t("patientDetail.distribution.readingsCount", { count: item.count })}` : ""}
                          </small>
                        </span>
                        <strong className="react-distribution-legend__value">{formatNumber(item.value, "%")}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </section>

          <section className="react-panel react-trend" aria-labelledby="trend-title">
            <div className="react-panel__header">
              <div>
                <h2 id="trend-title">{isDayMode ? t("patientDetail.trend.titleDay") : weeklyTrend ? t("patientDetail.trend.titlePeriodWeekly") : t("patientDetail.trend.titlePeriod")}</h2>
                <p>
                  {isDayMode && selectedDay
                    ? t("patientDetail.trend.bodyDay", { date: formatDate(selectedDay) })
                    : t("patientDetail.trend.bodyPeriod")}
                </p>
                {isSparseDay ? <p className="react-trend__note">{t("patientDetail.trend.sparseDayNote")}</p> : null}
                {!isDayMode && weeklyTrend ? <p className="react-trend__note">{t("patientDetail.trend.weeklyNote")}</p> : null}
              </div>
              {selectedDay ? (
                <div className="react-segmented" role="group" aria-label={t("patientDetail.trend.viewModeLabel")}>
                  <button type="button" aria-pressed={!isDayMode} onClick={handleShowPeriod}>
                    {t("patientDetail.trend.chipPeriod")}
                  </button>
                  <button type="button" aria-pressed={isDayMode} onClick={() => setViewMode("day")}>
                    {t("patientDetail.trend.chipSelectedDay")}
                  </button>
                </div>
              ) : null}
            </div>
            <div className="react-chart">
              {!isDayMode ? (
                <ResponsiveContainer width="100%" height={trendChartHeight}>
                  <LineChart
                    data={trendSeries.series}
                    margin={trendChartMargin}
                    onClick={(state) => {
                      const clickedDate = state?.activePayload?.[0]?.payload?.date;
                      if (clickedDate) {
                        handleSelectDay(clickedDate);
                      }
                    }}
                  >
                    <CartesianGrid strokeDasharray="4 4" stroke={palette.grid} />
                    <XAxis dataKey="key" tickFormatter={formatTrendTick} tick={axisTickStyle} minTickGap={isCompactMobile ? 18 : 10} />
                    <YAxis tick={axisTickStyle} width={isCompactMobile ? 32 : 40} domain={trendYAxisDomain} ticks={trendYAxisTicks} interval={0} />
                    <Tooltip
                      formatter={(value) => (value == null ? t("patientDetail.trend.gapValue") : `${formatNumber(value)} mg/dL`)}
                      labelFormatter={(_, payload) => formatTrendTooltipLabel(payload?.[0]?.payload)}
                      contentStyle={tooltipContentStyle}
                      labelStyle={tooltipLabelStyle}
                    />
                    {referenceLines.map((line) => (
                      <ReferenceLine key={line.y} y={line.y} stroke={line.color} strokeWidth={1.5} strokeDasharray={line.dash} />
                    ))}
                    {trendSeries.gaps.map((gap) => (
                      <ReferenceLine
                        key={gap.key}
                        x={gap.key}
                        stroke={palette.muted}
                        strokeDasharray="2 3"
                        label={{ value: t("patientDetail.trend.gapMarker"), position: "insideTop", fontSize: 12, fill: palette.muted }}
                      />
                    ))}
                    <Line
                      type="monotone"
                      dataKey="avg_glucose"
                      connectNulls={false}
                      name={weeklyTrend ? t("patientDetail.trend.seriesWeeklyAverage") : t("patientDetail.trend.seriesAverage")}
                      stroke={palette.trend}
                      strokeWidth={3}
                      isAnimationActive={!reducedMotion}
                      activeDot={{ r: 7, onClick: (_, __, event) => event?.stopPropagation?.() }}
                      dot={(props) => {
                        const { cx, cy, payload, index } = props;
                        if (cx == null || cy == null || !payload?.date) {
                          return null;
                        }

                        const isActive = payload.dates ? payload.dates.includes(selectedDay) : payload.date === selectedDay;
                        return (
                          <circle
                            key={`trend-dot-${payload.key || payload.date}-${index ?? "item"}`}
                            cx={cx}
                            cy={cy}
                            r={isActive ? 6 : 4}
                            fill={isActive ? palette.trend : palette.surface}
                            stroke={palette.trend}
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
                  <LineChart data={selectedDayEvents} margin={trendChartMargin}>
                    <CartesianGrid strokeDasharray="4 4" stroke={palette.grid} />
                    <XAxis dataKey="event_time" tick={axisTickStyle} minTickGap={isCompactMobile ? 16 : 10} />
                    <YAxis tick={axisTickStyle} width={isCompactMobile ? 32 : 40} domain={trendYAxisDomain} ticks={trendYAxisTicks} interval={0} />
                    <Tooltip
                      formatter={(value) => `${formatNumber(value)} mg/dL`}
                      labelFormatter={(_, payload) =>
                        payload?.[0]?.payload
                          ? `${formatDate(payload[0].payload.event_date)} - ${payload[0].payload.event_time}`
                          : ""
                      }
                      contentStyle={tooltipContentStyle}
                      labelStyle={tooltipLabelStyle}
                    />
                    {referenceLines.map((line) => (
                      <ReferenceLine key={line.y} y={line.y} stroke={line.color} strokeWidth={1.5} strokeDasharray={line.dash} />
                    ))}
                    <Line
                      type={isSparseDay ? "linear" : "monotone"}
                      dataKey="glucose_mg_dl"
                      name={t("patientDetail.trend.seriesGlucose")}
                      stroke={palette.trend}
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      isAnimationActive={!reducedMotion}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <StateBlock
                  icon={<ChartLineIcon />}
                  title={t("patientDetail.trend.insufficientData.title")}
                  description={t("patientDetail.trend.insufficientData.description")}
                />
              )}
            </div>
            {!isDayMode && trendGapNote ? <p className="react-chart-summary" data-testid="trend-gap-note">{trendGapNote}</p> : null}
            <ul className="react-chart-legend" aria-label={t("patientDetail.trend.chartLegendAriaLabel")}>
              {trendLegendItems.map((item) => (
                <li key={item.label} className="react-chart-legend__item">
                  <svg className="react-chart-legend__line" viewBox="0 0 28 6" aria-hidden="true" focusable="false">
                    <line x1="0" y1="3" x2="28" y2="3" stroke={item.color} strokeWidth={item.dash ? 2 : 3} strokeDasharray={item.dash || undefined} />
                  </svg>
                  <small>{item.label}</small>
                </li>
              ))}
            </ul>
            <div className="react-day-strip" role="group" aria-label={t("patientDetail.trend.dayStripAriaLabel")} ref={dayStripRef}>
              {availableDayDates.map((dateValue) => (
                <button
                  key={dateValue}
                  type="button"
                  className={`react-day-pill${dateValue === selectedDay ? " is-active" : ""}`}
                  aria-pressed={dateValue === selectedDay}
                  onClick={() => handleSelectDay(dateValue)}
                >
                  <strong>{formatShortDate(dateValue)}</strong>
                  <small>{formatNumber(data.daily_indicators.find((indicator) => indicator.date === dateValue)?.avg_glucose)}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="react-panel react-extremes" aria-labelledby="extremes-title">
            <div className="react-panel__header">
              <div>
                <h2 id="extremes-title">{t("patientDetail.extremeEvents.title")}</h2>
                <p>
                  {isDayMode && selectedDay
                    ? t("patientDetail.extremeEvents.scopeDay", { date: formatDate(selectedDay) })
                    : t("patientDetail.extremeEvents.scopePeriod")}
                </p>
              </div>
            </div>
            <div className="react-chart react-chart--extremes">
              <ResponsiveContainer width="100%" height={dropHoursChartHeight}>
                <BarChart data={activeHourlyExtremes} margin={trendChartMargin} barGap={isCompactMobile ? 2 : 4} barCategoryGap={isCompactMobile ? "10%" : "18%"}>
                  <CartesianGrid strokeDasharray="4 4" stroke={palette.grid} />
                  <XAxis
                    dataKey="hour"
                    ticks={hourlyAxisTicks}
                    interval={0}
                    tickFormatter={(value) => (isCompactMobile ? `${value}` : `${value}h`)}
                    tick={hourlyAxisTickStyle}
                    minTickGap={0}
                    height={32}
                  />
                  <YAxis allowDecimals={false} tick={axisTickStyle} width={isCompactMobile ? 24 : 32} />
                  <Tooltip formatter={(value) => t("patientDetail.extremeEvents.tooltipEvents", { count: value })} labelFormatter={(label) => `${String(label).padStart(2, "0")}h`} contentStyle={tooltipContentStyle} labelStyle={tooltipLabelStyle} />
                  <Legend
                    verticalAlign="top"
                    height={32}
                    wrapperStyle={{ fontSize: "14px" }}
                    formatter={(value) => <span style={{ color: palette.text }}>{value}</span>}
                  />
                  <Bar dataKey="lowCount" name="< 70 mg/dL" fill={palette.low} radius={[8, 8, 0, 0]} isAnimationActive={!reducedMotion} />
                  <Bar dataKey="highCount" name="> 250 mg/dL" fill={palette.veryHigh} radius={[8, 8, 0, 0]} isAnimationActive={!reducedMotion} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="react-chart-summary" data-testid="extremes-summary">{extremesSummary}</p>
          </section>
        </>
      )}

      <section className="react-grid react-grid--detail-data">
        <article className="react-panel react-panel--wide react-data-panel">
          {isCompactMobile ? (
            <details className="react-disclosure react-disclosure--panel">
              <summary>
                <h2>{t("patientDetail.dailyIndicators.toggle", { count: dailyTotal })}</h2>
                <ChevronDownIcon />
              </summary>
              {dailyIndicatorRows}
              {dailyIndicatorsPagination}
            </details>
          ) : (
            <>
              <div className="react-panel__header">
                <div>
                  <h2>{t("patientDetail.dailyIndicators.title")}</h2>
                </div>
              </div>
              <div className="react-table-shell react-table-shell--daily-indicators">
                <table className="react-table react-table--daily-indicators">
                  <thead>
                    <tr>
                      <th>{t("patientDetail.dailyIndicators.date")}</th>
                      <th className="is-num">{t("patientDetail.dailyIndicators.avg")}</th>
                      <th className="is-num">{t("patientDetail.dailyIndicators.pctHypo")}</th>
                      <th className="is-num">{t("patientDetail.dailyIndicators.pctInRange")}</th>
                      <th className="is-num">{t("patientDetail.dailyIndicators.pctHyper")}</th>
                      <th>{t("patientDetail.dailyIndicators.anomaly")}</th>
                      <th>{t("patientDetail.dailyIndicators.profile")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyIndicatorsPage.map((indicator) => (
                      <tr
                        key={indicator.date}
                        className={indicator.date === selectedDay ? "is-selected" : ""}
                        onClick={() => handleSelectDay(indicator.date)}
                      >
                        <td>{formatDate(indicator.date)}</td>
                        <td className="is-num">{!indicator.analysis_pending && indicator.avg_glucose != null ? `${formatNumber(indicator.avg_glucose)} mg/dL` : t("common.dash")}</td>
                        <td className="is-num">{indicator.analysis_pending ? t("common.dash") : formatNumber(indicator.pct_hypo, "%")}</td>
                        <td className="is-num">{indicator.analysis_pending ? t("common.dash") : formatNumber(indicator.pct_in_range, "%")}</td>
                        <td className="is-num">{indicator.analysis_pending ? t("common.dash") : formatNumber(indicator.pct_hyper, "%")}</td>
                        <td>
                          {!indicator.analysis_pending && indicator.anomaly_flag ? (
                            <span className="react-badge react-badge--atypical react-badge--compact">{t("patientDetail.dailyIndicators.badgeAtypical")}</span>
                          ) : (
                            t("common.dash")
                          )}
                        </td>
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
              {dailyIndicatorsPagination}
            </>
          )}
        </article>

        <article className="react-panel react-panel--wide react-data-panel">
          {isCompactMobile ? (
            <details className="react-disclosure react-disclosure--panel">
              <summary>
                <h2>{t("patientDetail.recentEvents.toggle", { count: eventsTotal })}</h2>
                <ChevronDownIcon />
              </summary>
              {recentEventRows}
              {recentEventsPagination}
            </details>
          ) : (
            <>
              <div className="react-panel__header">
                <div>
                  <h2>{t("patientDetail.recentEvents.title")}</h2>
                </div>
              </div>
              <div className="react-table-shell">
                <table className="react-table">
                  <thead>
                    <tr>
                      <th>{t("patientDetail.recentEvents.when")}</th>
                      <th className="is-num">{t("patientDetail.recentEvents.value")}</th>
                      <th>{t("patientDetail.recentEvents.context")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentEvents.map((event) => (
                      <tr key={`${event.occurred_at}-${event.event_type}`}>
                        <td>{formatPatientEventDateTime(event)}</td>
                        <td className="is-num">{formatEventValue(event)}</td>
                        <td>{eventContextLabel(event) || t("common.dash")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {recentEventsPagination}
            </>
          )}
        </article>
      </section>

      {isOwnPatientView ? (
        <ManualGlucoseEntryForm
          patientId={patient.id}
          onCreated={handleManualRecordCreated}
          open={manualOpen}
          onClose={() => setManualOpen(false)}
        />
      ) : null}

      {isDoctorView && doctorLink ? (
        <section id="patient-access" className="react-panel react-patient-access" aria-labelledby="patient-access-title">
          <div className="react-patient-access__copy">
            <h2 id="patient-access-title">{t("patientDetail.access.title")}</h2>
            <p>{t("patientDetail.access.body")}</p>
          </div>
          <button
            type="button"
            className="react-button react-button--text react-button--danger-text"
            onClick={() => {
              setRevokeError("");
              setRevokeOpen(true);
            }}
          >
            {t("dashboard.revokeLink")}
          </button>
        </section>
      ) : null}
    </div>
  );
}
