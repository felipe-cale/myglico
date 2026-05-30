const HYPO_LIMIT = 70;
const HYPER_LIMIT = 180;
const CRITICAL_HYPER_LIMIT = 250;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value) + suffix;
}

function formatDate(dateValue) {
  if (!dateValue) {
    return "-";
  }
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(`${dateValue}T00:00:00`));
}

function reportFileName(patientName, startDate, endDate) {
  const safeName = (patientName || "paciente")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
  return `relatorio-${safeName || "paciente"}-${startDate || "inicio"}-${endDate || "fim"}.html`;
}

function groupEventsByDate(events) {
  return events.reduce((accumulator, event) => {
    const dateKey = event.event_date;
    if (!accumulator[dateKey]) {
      accumulator[dateKey] = [];
    }
    accumulator[dateKey].push(event);
    return accumulator;
  }, {});
}

function calculateEventStats(events) {
  const values = events
    .map((event) => event.glucose_mg_dl)
    .filter((value) => value !== null && value !== undefined);
  const total = values.length;
  const lowCount = values.filter((value) => value < HYPO_LIMIT).length;
  const highCount = values.filter((value) => value > HYPER_LIMIT).length;
  const inRangeCount = total - lowCount - highCount;

  return {
    measurementCount: total,
    avgGlucose: total ? values.reduce((sum, value) => sum + value, 0) / total : null,
    minGlucose: total ? Math.min(...values) : null,
    maxGlucose: total ? Math.max(...values) : null,
    pctHypo: total ? (lowCount / total) * 100 : 0,
    pctInRange: total ? (inRangeCount / total) * 100 : 0,
    pctHyper: total ? (highCount / total) * 100 : 0,
    lowEventsCount: lowCount,
    highEventsCount: highCount
  };
}

function buildLinePath(points, valueAccessor, width = 620, height = 210) {
  const values = points.map(valueAccessor).filter((value) => value !== null && value !== undefined);
  if (!values.length) {
    return { path: "", circles: "", width, height };
  }
  const minValue = Math.min(...values, HYPO_LIMIT);
  const maxValue = Math.max(...values, CRITICAL_HYPER_LIMIT);
  const spread = Math.max(maxValue - minValue, 1);
  const xStep = width / Math.max(points.length - 1, 1);
  const coords = points.map((point, index) => {
    const rawValue = valueAccessor(point);
    const value = rawValue === null || rawValue === undefined ? minValue : rawValue;
    const x = points.length === 1 ? width / 2 : index * xStep;
    const y = height - ((value - minValue) / spread) * (height - 22) - 11;
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)), value };
  });
  const path = coords.map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x},${coord.y}`).join(" ");
  const circles = coords
    .map((coord) => `<circle cx="${coord.x}" cy="${coord.y}" r="4"><title>${formatNumber(coord.value)} mg/dL</title></circle>`)
    .join("");
  return { path, circles, width, height };
}

function referenceLines(width, height, minValue, maxValue) {
  const spread = Math.max(maxValue - minValue, 1);
  return [HYPO_LIMIT, HYPER_LIMIT, CRITICAL_HYPER_LIMIT]
    .map((limit) => {
      const y = height - ((limit - minValue) / spread) * (height - 22) - 11;
      return `<line x1="0" x2="${width}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}" class="reference reference-${limit}" /><text x="6" y="${Math.max(12, y - 5).toFixed(2)}">${limit} mg/dL</text>`;
    })
    .join("");
}

function renderLineChart(points, valueAccessor, labelAccessor) {
  if (!points.length) {
    return '<div class="empty">Sem dados suficientes para o gráfico.</div>';
  }
  const width = 620;
  const height = 210;
  const values = points.map(valueAccessor).filter((value) => value !== null && value !== undefined);
  const minValue = Math.min(...values, HYPO_LIMIT);
  const maxValue = Math.max(...values, CRITICAL_HYPER_LIMIT);
  const { path, circles } = buildLinePath(points, valueAccessor, width, height);
  const labels = points
    .filter((_, index) => index === 0 || index === points.length - 1 || index % Math.ceil(points.length / 6) === 0)
    .map((point, index, selected) => {
      const originalIndex = points.indexOf(point);
      const x = points.length === 1 ? width / 2 : (originalIndex * width) / Math.max(points.length - 1, 1);
      return `<span style="left:${(x / width) * 100}%">${escapeHtml(labelAccessor(point, index, selected))}</span>`;
    })
    .join("");

  return `
    <div class="line-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico de glicemia">
        ${referenceLines(width, height, minValue, maxValue)}
        <path d="${path}" />
        ${circles}
      </svg>
      <div class="axis-labels">${labels}</div>
    </div>
  `;
}

function renderStatList(stats) {
  return `
    <div class="stat-list">
      ${stats
        .map(
          (stat) => `
            <div class="stat-item">
              <span>${escapeHtml(stat.label)}</span>
              <strong>${escapeHtml(stat.value)}</strong>
              ${stat.helper ? `<small>${escapeHtml(stat.helper)}</small>` : ""}
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderDistributionBars(items) {
  return `
    <div class="distribution-bars">
      ${items
        .map(
          (item) => `
            <div>
              <span>${escapeHtml(item.label)}</span>
              <strong>${formatNumber(item.value, "%")}</strong>
              <em><i style="width:${Math.max(0, Math.min(100, item.value || 0))}%"></i></em>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderHourlyChart(hourlyExtremes) {
  const maxCount = Math.max(...hourlyExtremes.map((item) => Math.max(item.lowCount, item.highCount)), 1);
  return `
    <div class="hourly-chart">
      ${hourlyExtremes
        .map(
          (item) => `
            <div class="hour-row">
              <span>${String(item.hour).padStart(2, "0")}h</span>
              <div class="hour-bars">
                <i class="hypo" style="width:${(item.lowCount / maxCount) * 100}%"></i>
                <i class="hyper" style="width:${(item.highCount / maxCount) * 100}%"></i>
              </div>
              <small>${item.lowCount} hipo / ${item.highCount} hiper</small>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderReadingsTable(events) {
  if (!events.length) {
    return '<p class="empty">Sem leituras glicêmicas registradas neste dia.</p>';
  }
  return `
    <table>
      <thead><tr><th>Horário</th><th>Glicemia</th><th>Contexto</th><th>Classificação</th></tr></thead>
      <tbody>
        ${events
          .map((event) => {
            const classification = event.glucose_mg_dl < HYPO_LIMIT ? "Hipo" : event.glucose_mg_dl > HYPER_LIMIT ? "Hiper" : "Em faixa";
            return `
              <tr>
                <td>${escapeHtml(event.event_time || "-")}</td>
                <td>${formatNumber(event.glucose_mg_dl)} mg/dL</td>
                <td>${escapeHtml(event.context_label_display || event.context_label || "-")}</td>
                <td>${classification}</td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function renderDailySections(data, eventsByDate) {
  const dailyDates = Array.from(new Set([...data.daily_indicators.map((item) => item.date), ...Object.keys(eventsByDate)])).sort();
  return dailyDates
    .map((dateValue) => {
      const indicator = data.daily_indicators.find((item) => item.date === dateValue);
      const events = eventsByDate[dateValue] || [];
      const stats = calculateEventStats(events);
      const chartEvents = events.map((event) => ({ ...event, label: event.event_time }));
      return `
        <section class="day-section">
          <header>
            <div>
              <p>Detalhamento diário</p>
              <h3>${formatDate(dateValue)}</h3>
            </div>
            <strong>${indicator?.anomaly_flag ? "Dia atípico" : "Sem alerta atípico"}</strong>
          </header>
          <div class="chart-with-stats">
            ${renderLineChart(chartEvents, (event) => event.glucose_mg_dl, (event) => event.label)}
            ${renderStatList([
              { label: "Leituras", value: stats.measurementCount },
              { label: "Média do dia", value: `${formatNumber(stats.avgGlucose)} mg/dL` },
              { label: "Mín / Máx", value: `${formatNumber(stats.minGlucose)} / ${formatNumber(stats.maxGlucose)} mg/dL` },
              { label: "% em hipo", value: formatNumber(indicator?.pct_hypo ?? stats.pctHypo, "%"), helper: `${stats.lowEventsCount} leituras < 70` },
              { label: "% em faixa", value: formatNumber(indicator?.pct_in_range ?? stats.pctInRange, "%") },
              { label: "% em hiper", value: formatNumber(indicator?.pct_hyper ?? stats.pctHyper, "%"), helper: `${stats.highEventsCount} leituras > 180` },
              { label: "Perfil do dia", value: indicator?.cluster_profile_label || (indicator?.cluster_label != null ? `Grupo ${indicator.cluster_label}` : "-") }
            ])}
          </div>
          <h4>Leituras registradas no dia</h4>
          ${renderReadingsTable(events)}
        </section>
      `;
    })
    .join("");
}


function renderRecentEventsTable(events) {
  if (!events?.length) {
    return '<p class="empty">Sem eventos recentes no período exportado.</p>';
  }

  return `
    <table>
      <thead><tr><th>Quando</th><th>Tipo</th><th>Subtipo</th><th>Valor</th><th>Contexto</th><th>Confiabilidade</th></tr></thead>
      <tbody>
        ${events
          .map((event) => {
            const value = event.glucose_mg_dl != null
              ? `${formatNumber(event.glucose_mg_dl)} mg/dL`
              : event.numeric_value != null
                ? formatNumber(event.numeric_value)
                : "-";
            return `
              <tr>
                <td>${escapeHtml(event.occurred_at ? new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(event.occurred_at)) : "-")}</td>
                <td>${escapeHtml(event.event_type_label || event.event_type || "-")}</td>
                <td>${escapeHtml(event.event_subtype_label || event.event_subtype || "-")}</td>
                <td>${escapeHtml(value)}</td>
                <td>${escapeHtml(event.context_label_display || event.context_label || "-")}</td>
                <td>${escapeHtml(event.timestamp_quality_label || event.timestamp_quality || "-")}</td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function buildReportHtml(data, hourlyExtremes) {
  const eventsByDate = groupEventsByDate(data.glucose_events || []);
  const generatedAt = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date());
  const periodStats = [
    { label: "Dias observados", value: data.summary.days_observed ?? "-" },
    { label: "Média glicêmica", value: `${formatNumber(data.summary.avg_glucose)} mg/dL` },
    { label: "% em hipo", value: formatNumber(data.summary.pct_hypo, "%"), helper: "leituras abaixo de 70 mg/dL" },
    { label: "% em faixa", value: formatNumber(data.summary.pct_in_range, "%") },
    { label: "% em hiper", value: formatNumber(data.summary.pct_hyper, "%") },
    { label: "Dias atípicos", value: data.summary.anomaly_days ?? "-" },
    { label: "Medições", value: data.summary.glucose_measurements ?? "-" }
  ];
  const distributionItems = [
    { label: "Hipo", value: data.summary.pct_hypo },
    { label: "Em faixa", value: data.summary.pct_in_range },
    { label: "Hiper", value: data.summary.pct_hyper }
  ];

  return `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>Relatório glicêmico - ${escapeHtml(data.patient.display_name)}</title>
  <style>
    :root { color: #17304a; font-family: Arial, sans-serif; }
    body { margin: 0; background: #f4fbfe; }
    main { max-width: 1120px; margin: 0 auto; padding: 28px; }
    .hero, section { background: #fff; border: 1px solid #d8eaf7; border-radius: 22px; padding: 22px; margin-bottom: 18px; box-shadow: 0 12px 28px rgba(20, 79, 126, 0.08); }
    h1, h2, h3, h4, p { margin-top: 0; }
    h1 { font-size: 34px; margin-bottom: 8px; }
    h2 { font-size: 23px; }
    h3 { font-size: 20px; }
    p, small, td, th, span { line-height: 1.45; }
    .meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }
    .meta div, .stat-item { background: #f8fcff; border: 1px solid #d8eaf7; border-radius: 16px; padding: 12px; }
    .meta span, .stat-item span { display: block; color: #61728a; font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    .meta strong, .stat-item strong { display: block; margin-top: 5px; font-size: 18px; }
    .chart-with-stats { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 18px; align-items: start; }
    .stat-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .stat-item small { display: block; color: #61728a; margin-top: 4px; }
    .distribution-bars { display: grid; gap: 11px; }
    .distribution-bars div { display: grid; grid-template-columns: 90px 70px 1fr; gap: 10px; align-items: center; }
    .distribution-bars em { display: block; height: 12px; border-radius: 999px; background: #e8f4fb; overflow: hidden; }
    .distribution-bars i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #167cd9, #1eab69); }
    .line-chart svg { width: 100%; height: auto; min-height: 210px; background: linear-gradient(180deg, #fbfeff, #f2faff); border: 1px solid #d8eaf7; border-radius: 18px; }
    .line-chart path { fill: none; stroke: #167cd9; stroke-width: 4; }
    .line-chart circle { fill: #fff; stroke: #167cd9; stroke-width: 3; }
    .line-chart .reference { stroke-dasharray: 7 6; stroke-width: 1.8; }
    .line-chart .reference-70 { stroke: #e35d73; }
    .line-chart .reference-180 { stroke: #f4a93d; }
    .line-chart .reference-250 { stroke: #7a52cc; }
    .line-chart text { fill: #61728a; font-size: 12px; font-weight: 700; }
    .axis-labels { position: relative; height: 24px; margin-top: 4px; }
    .axis-labels span { position: absolute; transform: translateX(-50%); color: #61728a; font-size: 12px; }
    .hourly-chart { display: grid; gap: 7px; }
    .hour-row { display: grid; grid-template-columns: 42px 1fr 120px; gap: 10px; align-items: center; }
    .hour-bars { display: grid; gap: 3px; }
    .hour-bars i { display: block; min-width: 2px; height: 8px; border-radius: 999px; }
    .hour-bars .hypo { background: #27b7e7; }
    .hour-bars .hyper { background: #f4a93d; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { padding: 9px 10px; border-bottom: 1px solid #d8eaf7; text-align: left; font-size: 13px; }
    th { color: #61728a; text-transform: uppercase; letter-spacing: .07em; background: #f8fcff; }
    .day-section { break-inside: avoid; }
    .day-section header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
    .day-section header p { color: #0b7a51; text-transform: uppercase; letter-spacing: .16em; font-size: 11px; font-weight: 700; }
    .day-section header strong { color: #0a4c9c; }
    .empty { padding: 18px; border: 1px dashed #b9d8ee; border-radius: 16px; color: #61728a; }
    @media print { body { background: #fff; } main { padding: 0; } .hero, section { box-shadow: none; break-inside: avoid; } }
    @media (max-width: 860px) { main { padding: 14px; } .meta, .chart-with-stats { grid-template-columns: 1fr; } .stat-list { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <div class="hero">
      <h1>Relatório glicêmico</h1>
      <p>Exportação analítica da tela de detalhamento do paciente, incluindo gráficos, estatísticas do período e detalhamento diário com todas as leituras do intervalo.</p>
      <div class="meta">
        <div><span>Paciente</span><strong>${escapeHtml(data.patient.display_name)}</strong></div>
        <div><span>Período</span><strong>${formatDate(data.filters.start_date)} - ${formatDate(data.filters.end_date)}</strong></div>
        <div><span>Fonte</span><strong>${escapeHtml(data.patient.source_file || "-")}</strong></div>
        <div><span>Gerado em</span><strong>${escapeHtml(generatedAt)}</strong></div>
      </div>
    </div>

    <section>
      <h2>Estatísticas do período</h2>
      ${renderStatList(periodStats)}
    </section>

    <section>
      <h2>Distribuição glicêmica do período</h2>
      <div class="chart-with-stats">
        ${renderDistributionBars(distributionItems)}
        ${renderStatList(periodStats.slice(2, 5))}
      </div>
    </section>

    <section>
      <h2>Indicativo de hipoglicemia e hiperglicemia por hora</h2>
      <div class="chart-with-stats">
        ${renderHourlyChart(hourlyExtremes)}
        ${renderStatList([
          { label: "Eventos < 70 mg/dL", value: hourlyExtremes.reduce((sum, item) => sum + item.lowCount, 0) },
          { label: "Eventos > 250 mg/dL", value: hourlyExtremes.reduce((sum, item) => sum + item.highCount, 0) },
          { label: "Pico hipo", value: `${String(hourlyExtremes.reduce((current, item) => (item.lowCount > current.lowCount ? item : current), hourlyExtremes[0]).hour).padStart(2, "0")}h` },
          { label: "Pico hiper", value: `${String(hourlyExtremes.reduce((current, item) => (item.highCount > current.highCount ? item : current), hourlyExtremes[0]).hour).padStart(2, "0")}h` }
        ])}
      </div>
    </section>

    <section>
      <h2>Média de glicemia pelo período</h2>
      <div class="chart-with-stats">
        ${renderLineChart(data.daily_indicators, (item) => item.avg_glucose, (item) => formatDate(item.date).slice(0, 5))}
        ${renderStatList(periodStats)}
      </div>
    </section>

    ${renderDailySections(data, eventsByDate)}

    <section>
      <h2>Últimos registros do período</h2>
      ${renderRecentEventsTable(data.recent_events || [])}
    </section>

    <section>
      <h2>Indicadores diários consolidados</h2>
      <table>
        <thead><tr><th>Data</th><th>Média</th><th>% Hipo</th><th>% Faixa</th><th>% Hiper</th><th>Atípico</th><th>Perfil</th></tr></thead>
        <tbody>
          ${data.daily_indicators
            .map(
              (indicator) => `
                <tr>
                  <td>${formatDate(indicator.date)}</td>
                  <td>${formatNumber(indicator.avg_glucose)} mg/dL</td>
                  <td>${formatNumber(indicator.pct_hypo, "%")}</td>
                  <td>${formatNumber(indicator.pct_in_range, "%")}</td>
                  <td>${formatNumber(indicator.pct_hyper, "%")}</td>
                  <td>${indicator.anomaly_flag ? "Sim" : "Não"}</td>
                  <td>${escapeHtml(indicator.cluster_profile_label || (indicator.cluster_label != null ? `Grupo ${indicator.cluster_label}` : "-"))}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>`;
}

export function exportPatientReport(data, hourlyExtremes) {
  if (!data) {
    return;
  }
  const html = buildReportHtml(data, hourlyExtremes);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = reportFileName(data.patient.display_name, data.filters.start_date, data.filters.end_date);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
