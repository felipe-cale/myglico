import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
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
import { fetchPatientDetail, patientReportPdfUrl } from "../api";
import StateBlock from "../components/StateBlock";

const PIE_COLORS = ["#e35d73", "#19a86a", "#f4a93d"];
const HOURLY_TICKS = Array.from({ length: 24 }, (_, index) => index);
const TREND_COLOR = "#167cd9";
const HYPO_COLOR = "#e35d73";
const HYPER_COLOR = "#f4a93d";
const HIGH_RISK_COLOR = "#7a52cc";

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value) + suffix;
}

function formatDate(dateValue) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(`${dateValue}T00:00:00`));
}

function formatDateTime(dateValue) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(dateValue));
}

function formatShortDate(dateValue) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${dateValue}T00:00:00`));
}

function getClusterProfileLabel(indicator) {
  if (indicator?.cluster_profile_label) {
    return indicator.cluster_profile_label;
  }
  if (indicator?.cluster_label !== null && indicator?.cluster_label !== undefined) {
    return `Grupo ${indicator.cluster_label}`;
  }
  return "-";
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

function ClusterProfileValue({ indicator, compact = false, showGroup = true }) {
  const profileLabel = getClusterProfileLabel(indicator);
  const profileDescription = indicator?.cluster_profile_description;
  const groupLabel =
    showGroup && indicator?.cluster_profile_label && indicator?.cluster_label !== null && indicator?.cluster_label !== undefined
      ? `Grupo ${indicator.cluster_label}`
      : null;

  return (
    <span className={`react-cluster-profile${compact ? " is-compact" : ""}`}>
      <span className="react-cluster-profile__row">
        <span className="react-cluster-profile__label">{profileLabel}</span>
        <InfoTooltip content={profileDescription} label={`Explicar ${profileLabel}`} />
      </span>
      {groupLabel ? <small>{groupLabel}</small> : null}
    </span>
  );
}

function PatientStatCard({ label, value, helper, tone = "blue" }) {
  return (
    <article className={`react-stat-card react-stat-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
    </article>
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

export default function PatientDetailPage() {
  const { patientId } = useParams();
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
  const lastResolvedRequestRef = useRef("");
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
  const requestKey = `${patientId}:${requestedStart || ""}:${requestedEnd || ""}`;

  useEffect(() => {
    if (data && lastResolvedRequestRef.current === requestKey) {
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);
    fetchPatientDetail(patientId, { startDate: requestedStart, endDate: requestedEnd })
      .then((payload) => {
        if (!active) {
          return;
        }
        setData(payload);
        setDraftStartDate(payload.filters.start_date || "");
        setDraftEndDate(payload.filters.end_date || "");
        lastResolvedRequestRef.current = `${patientId}:${payload.filters.start_date || ""}:${payload.filters.end_date || ""}`;

        const next = new URLSearchParams();
        if (payload.filters.start_date) {
          next.set("start_date", payload.filters.start_date);
        }
        if (payload.filters.end_date) {
          next.set("end_date", payload.filters.end_date);
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
  }, [patientId, requestedStart, requestedEnd, requestKey, data, searchParams, setSearchParams]);

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
      { name: "Hipo", value: data.summary.pct_hypo },
      { name: "Em faixa", value: data.summary.pct_in_range },
      { name: "Hiper", value: data.summary.pct_hyper }
    ];
  }, [data]);

  const selectedDayDistribution = useMemo(() => {
    if (!selectedDaySummary) {
      return [];
    }

    return [
      { name: "Hipo", value: selectedDaySummary.pctHypo },
      { name: "Em faixa", value: selectedDaySummary.pctInRange },
      { name: "Hiper", value: selectedDaySummary.pctHyper }
    ];
  }, [selectedDaySummary]);

  const overviewStats = useMemo(() => {
    if (isDayMode && selectedDaySummary) {
      return [
        {
          label: "Medições",
          value: selectedDaySummary.measurementCount,
          helper: "leituras do dia",
          tone: "blue"
        },
        {
          label: "Média do dia",
          value: `${formatNumber(selectedDaySummary.avgGlucose)} mg/dL`,
          helper: formatShortDate(selectedDaySummary.date),
          tone: "cyan"
        },
        {
          label: "% em hipo",
          value: formatNumber(selectedDaySummary.pctHypo, "%"),
          helper: `${selectedDaySummary.lowEventsCount} eventos`,
          tone: "rose"
        },
        {
          label: "% em faixa",
          value: formatNumber(selectedDaySummary.pctInRange, "%"),
          helper: "distribuição do dia",
          tone: "green"
        },
        {
          label: "% em hiper",
          value: formatNumber(selectedDaySummary.pctHyper, "%"),
          helper: `${selectedDaySummary.highEventsCount} eventos`,
          tone: "yellow"
        }
      ];
    }

    return [
      {
        label: "Dias observados",
        value: summary?.days_observed ?? "-",
        helper: "dias com leituras",
        tone: "blue"
      },
      {
        label: "Média glicêmica",
        value: `${formatNumber(summary?.avg_glucose)} mg/dL`,
        helper: "média do período",
        tone: "cyan"
      },
      {
        label: "% em hipo",
        value: formatNumber(summary?.pct_hypo, "%"),
        helper: "leituras abaixo de 70 mg/dL",
        tone: "rose"
      },
      {
        label: "% em faixa",
        value: formatNumber(summary?.pct_in_range, "%"),
        helper: "leituras na faixa",
        tone: "green"
      },
      {
        label: "% em hiper",
        value: formatNumber(summary?.pct_hyper, "%"),
        helper: "acima da meta",
        tone: "yellow"
      },
      {
        label: "Dias atípicos",
        value: summary?.anomaly_days ?? "-",
        helper: "sinalizados pela análise",
        tone: "slate"
      }
    ];
  }, [isDayMode, selectedDaySummary, summary]);

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
    next.set("start_date", draftStartDate);
    next.set("end_date", draftEndDate);

    if (next.toString() !== searchParams.toString()) {
      lastResolvedRequestRef.current = "";
      setSelectedDay("");
      setViewMode("period");
      setSearchParams(next);
    }
  }

  if (loading) {
    return <StateBlock title="Carregando painel do paciente" description="Estamos preparando os indicadores e a visualização clínica." tone="info" />;
  }

  if (error || !data) {
    return <StateBlock title="Não foi possível carregar o paciente" description="Tivemos um problema ao montar o detalhamento analítico deste paciente." tone="danger" />;
  }

  const { patient, filters, recent_events: recentEvents } = data;
  const activeDistributionData = isDayMode && selectedDaySummary ? selectedDayDistribution : distributionData;
  const distributionChartHeight = isCompactMobile ? 182 : 206;
  const insightChartHeight = isCompactMobile ? 168 : 182;
  const dropHoursChartHeight = isCompactMobile ? 180 : 228;
  const trendChartHeight = isCompactMobile ? 260 : 340;
  const trendChartMargin = isCompactMobile
    ? { top: 8, right: 4, left: -20, bottom: 0 }
    : { top: 8, right: 12, left: 0, bottom: 0 };
  const dayChartMargin = isCompactMobile
    ? { top: 8, right: 4, left: -20, bottom: 0 }
    : { top: 8, right: 12, left: 0, bottom: 0 };
  const pieInnerRadius = isCompactMobile ? 56 : 64;
  const pieOuterRadius = isCompactMobile ? 72 : 80;
  const axisTickStyle = { fontSize: isCompactMobile ? 11 : 12 };
  const hourlyAxisTickStyle = { fontSize: isCompactMobile ? 9 : 10 };
  const trendLegendItems = [
    {
      label: isDayMode ? "Curva glicêmica" : "Média diária",
      color: TREND_COLOR,
      dashed: false,
    },
    {
      label: "Hipoglicemia < 70 mg/dL",
      color: HYPO_COLOR,
      dashed: true,
    },
    {
      label: "Meta alta 180 mg/dL",
      color: HYPER_COLOR,
      dashed: true,
    },
    {
      label: "Risco > 250 mg/dL",
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

  const reportUrl = patientReportPdfUrl(patient.id, {
    startDate: filters.start_date,
    endDate: filters.end_date
  });

  return (
    <div className="react-page react-page--patient-detail">
      <section className="react-hero react-hero--compact">
        <div className="react-hero__content">
          <div className="react-badges">
            <span className="react-badge react-badge--soft">{patient.source_file}</span>
            <span className="react-badge react-badge--blue">{summary.glucose_measurements} medições</span>
          </div>
          <p className="react-eyebrow">Detalhe do paciente</p>
          <h1>{patient.display_name}</h1>
          <p>
            Este painel consolida o período selecionado a partir do core clínico, com atualização dinâmica dos
            indicadores, registros e gráficos.
          </p>
          <div className="react-actions">
            <Link to="/" className="react-button react-button--ghost">
              Voltar para a visão geral
            </Link>
            <a className="react-button" href={reportUrl || "#"} target="_blank" rel="noreferrer">
              Baixar PDF clínico
            </a>
          </div>
        </div>
        <div className="react-hero__side">
          <div className="react-summary-box">
            <span>Período analisado</span>
            <strong>
              {formatDate(filters.start_date)} - {formatDate(filters.end_date)}
            </strong>
            <small>Janela padrão de 30 dias a partir da data mais recente disponível.</small>
          </div>
        </div>
      </section>

      <section className="react-panel react-panel--filter">
        <div className="react-filter-layout">
          <div className="react-filter-copy">
            <p className="react-eyebrow">Filtro temporal</p>
            <h2>Refinar o recorte analítico</h2>
            <p>Selecione o intervalo desejado e aplique o filtro para atualizar a análise.</p>
          </div>
          <div className="react-filter-controls">
            <form className="react-filter-form" onSubmit={applyRange}>
              <label>
                <span>Data inicial</span>
                <input
                  type="date"
                  value={draftStartDate}
                  min={filters.available_start_date}
                  max={filters.available_end_date}
                  onChange={(event) => setDraftStartDate(event.target.value)}
                />
              </label>
              <label>
                <span>Data final</span>
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
                  Filtrar
                </button>
                {hasInvalidRange ? <small>A data inicial não pode ser maior que a data final.</small> : null}
              </div>
            </form>
          </div>
        </div>
      </section>

      <section className="react-patient-insights">
        <article className="react-panel react-panel--summary">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">Distribuição</p>
              <h2>{isDayMode && selectedDaySummary ? `Faixa de ${formatShortDate(selectedDaySummary.date)}` : "Faixa glicêmica"}</h2>
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
              <p className="react-eyebrow">Eventos extremos</p>
              <h2>Ocorrências críticas por horário</h2>
            </div>
          </div>
          <div className="react-chart react-chart--insight react-chart--drop-hours">
            <ResponsiveContainer width="100%" height={dropHoursChartHeight}>
              <BarChart data={hourlyExtremes} margin={trendChartMargin} barGap={isCompactMobile ? 2 : 4} barCategoryGap={isCompactMobile ? "10%" : "18%"}>
                <CartesianGrid strokeDasharray="4 4" stroke="rgba(22, 124, 217, 0.12)" />
                <XAxis
                  dataKey="hour"
                  ticks={HOURLY_TICKS}
                  interval={0}
                  tickFormatter={(value) => `${value}h`}
                  tick={hourlyAxisTickStyle}
                  minTickGap={0}
                  height={isCompactMobile ? 28 : 32}
                />
                <YAxis allowDecimals={false} tick={axisTickStyle} width={isCompactMobile ? 24 : 32} />
                <Tooltip formatter={(value) => `${value} eventos`} labelFormatter={(label) => `${String(label).padStart(2, "0")}h`} />
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
              <p className="react-eyebrow">Tendência glicêmica</p>
              <h2>{isDayMode ? "Curva glicêmica do dia" : "Média diária do período"}</h2>
              <p>
                {isDayMode && selectedDay
                  ? `Visualização horária das leituras de ${formatDate(selectedDay)}, com foco na variação glicêmica ao longo do dia.`
                  : "Selecione um dia no gráfico ou na linha do tempo abaixo para abrir a leitura detalhada sem sair da página."}
              </p>
            </div>
            <div className="react-chip-row">
              <button
                type="button"
                className={`react-chip${!isDayMode ? " is-active" : ""}`}
                onClick={handleShowPeriod}
              >
                Período
              </button>
              {selectedDay ? (
                <button
                  type="button"
                  className={`react-chip${isDayMode ? " is-active" : ""}`}
                  onClick={() => setViewMode("day")}
                >
                  Dia selecionado
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
                    name="Média"
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
                  <Line type="monotone" dataKey="glucose_mg_dl" name="Glicemia" stroke={TREND_COLOR} strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <StateBlock
                title="Sem leituras suficientes no dia selecionado"
                description="Não há medições glicêmicas suficientes para compor a visualização horária deste dia."
              />
            )}
          </div>
          <div className="react-chart-legend" aria-label="Legenda do gráfico glicêmico">
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
          <div className="react-day-strip" role="list" aria-label="Dias disponíveis no período">
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
                <p className="react-eyebrow">{isDayMode && selectedDaySummary ? "Foco diário" : "Resumo clínico"}</p>
                <h2>{isDayMode && selectedDaySummary ? formatDate(selectedDaySummary.date) : "Visão do período"}</h2>
                <p>
                  {isDayMode && selectedDaySummary
                    ? "Resumo dos principais sinais observados no dia selecionado."
                    : "Síntese dos indicadores mais relevantes para leitura clínica rápida."}
                </p>
              </div>
            </div>
            <div className="react-stat-grid">
              {overviewStats.map((stat) => (
                <PatientStatCard
                  key={stat.label}
                  label={stat.label}
                  value={stat.value}
                  helper={stat.helper}
                  tone={stat.tone}
                />
              ))}
            </div>
          </article>
        </aside>
      </section>

      <section className="react-grid react-grid--detail-data">

        <article className="react-panel react-panel--wide">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">Indicadores diários</p>
              <h2>Evolução diária no período</h2>
            </div>
          </div>
          {isCompactMobile ? (
            <div className="react-mobile-list" aria-label="Indicadores diários">
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
                      <span className="react-mobile-card__eyebrow">Data</span>
                      <h3>{formatDate(indicator.date)}</h3>
                    </div>
                    <span className={`react-mobile-card__badge${indicator.anomaly_flag ? " is-alert" : ""}`}>
                      {indicator.anomaly_flag ? "Atípico" : "Estável"}
                    </span>
                  </div>
                  <div className="react-mobile-card__grid">
                    <MobileDetailField
                      label="Média"
                      value={indicator.avg_glucose != null ? `${formatNumber(indicator.avg_glucose)} mg/dL` : "-"}
                    />
                    <MobileDetailField label="% Hipo" value={formatNumber(indicator.pct_hypo, "%")} />
                    <MobileDetailField label="% Faixa" value={formatNumber(indicator.pct_in_range, "%")} />
                    <MobileDetailField label="% Hiper" value={formatNumber(indicator.pct_hyper, "%")} />
                    <MobileDetailField label="Perfil do dia" className="react-mobile-card__field--profile">
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
                    <th>Data</th>
                    <th>Média</th>
                    <th>% Hipo</th>
                    <th>% Faixa</th>
                    <th>% Hiper</th>
                    <th>Atípico</th>
                    <th>Perfil do dia</th>
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
                      <td>{indicator.anomaly_flag ? "Sim" : "Não"}</td>
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
              <p className="react-eyebrow">Eventos recentes</p>
              <h2>Últimos registros do período</h2>
            </div>
          </div>
          {isCompactMobile ? (
            <div className="react-mobile-list" aria-label="Eventos recentes">
              {recentEvents.map((event) => {
                const eventTypeLabel = event.event_type_label || event.event_type || "-";
                const eventSubtypeLabel = event.event_subtype_label || event.event_subtype || "-";
                const contextLabel = event.context_label_display || event.context_label || "-";

                return (
                  <article key={`${event.occurred_at}-${event.event_type}`} className="react-mobile-card">
                    <div className="react-mobile-card__header">
                      <div>
                        <span className="react-mobile-card__eyebrow">Quando</span>
                        <h3>{formatDateTime(event.occurred_at)}</h3>
                      </div>
                      <span className="react-mobile-card__badge" title={event.event_type || ""}>
                        {eventTypeLabel}
                      </span>
                    </div>
                    <div className="react-mobile-card__grid">
                      <MobileDetailField label="Subtipo" value={eventSubtypeLabel} />
                      <MobileDetailField
                        label="Valor"
                        value={
                          event.glucose_mg_dl != null
                            ? `${formatNumber(event.glucose_mg_dl)} mg/dL`
                            : event.numeric_value != null
                              ? formatNumber(event.numeric_value)
                              : "-"
                        }
                      />
                      <MobileDetailField label="Contexto" value={contextLabel} />
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
                    <th>Quando</th>
                    <th>Tipo</th>
                    <th>Subtipo</th>
                    <th>Valor</th>
                    <th>Contexto</th>
                  </tr>
                </thead>
                <tbody>
                  {recentEvents.map((event) => {
                    const eventTypeLabel = event.event_type_label || event.event_type || "-";
                    const eventSubtypeLabel = event.event_subtype_label || event.event_subtype || "-";
                    const contextLabel = event.context_label_display || event.context_label || "-";

                    return (
                      <tr key={`${event.occurred_at}-${event.event_type}`}>
                        <td>{formatDateTime(event.occurred_at)}</td>
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
