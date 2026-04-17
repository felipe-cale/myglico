(function () {
    const app = document.getElementById("patient-analytics-app");
    if (!app) {
        return;
    }

    const patientId = app.dataset.patientId;
    const apiUrl = app.dataset.apiUrl;
    const startInput = document.getElementById("start-date-input");
    const endInput = document.getElementById("end-date-input");
    const statusBadge = document.getElementById("analytics-status");
    const last30Button = document.getElementById("last-30-days-button");
    const form = document.getElementById("patient-range-form");

    const charts = {
        trend: null,
        distribution: null,
        hourly: null,
    };

    const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    const dateFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
    const shortDateFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });

    function badgeTone(type) {
        if (type === "danger" || type === "warning" || type === "success" || type === "info" || type === "neutral") {
            return type;
        }
        return "neutral";
    }

    function setStatus(message, tone) {
        statusBadge.className = `badge badge--${badgeTone(tone)}`;
        statusBadge.textContent = message;
    }

    function formatNumber(value, suffix = "") {
        if (value === null || value === undefined || Number.isNaN(Number(value))) {
            return "-";
        }
        return `${numberFormat.format(Number(value))}${suffix}`;
    }

    function formatPercent(value) {
        return formatNumber(value, "%");
    }

    function formatDate(value) {
        if (!value) {
            return "-";
        }
        return dateFormat.format(new Date(`${value}T00:00:00`));
    }

    function formatDateTime(value) {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("pt-BR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(new Date(value));
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = value;
        }
    }

    function buildEmptyRow(colspan, title, description) {
        return `<tr><td colspan="${colspan}"><div class="empty-state"><div class="empty-state__icon" aria-hidden="true"></div><div><h3>${title}</h3><p>${description}</p></div></div></td></tr>`;
    }

    function updateUrl(startDate, endDate) {
        const next = new URL(window.location.href);
        next.searchParams.set("start_date", startDate);
        next.searchParams.set("end_date", endDate);
        window.history.replaceState({}, "", `${next.pathname}?${next.searchParams.toString()}`);
    }

    function computeLastThirtyDays(availableStart, availableEnd) {
        const end = new Date(`${availableEnd}T00:00:00`);
        const start = new Date(end);
        start.setDate(start.getDate() - 29);
        const min = new Date(`${availableStart}T00:00:00`);
        const resolvedStart = start < min ? min : start;
        return {
            start: resolvedStart.toISOString().slice(0, 10),
            end: availableEnd,
        };
    }

    function syncInputs(filters) {
        startInput.min = filters.available_start_date || "";
        startInput.max = filters.available_end_date || "";
        endInput.min = filters.available_start_date || "";
        endInput.max = filters.available_end_date || "";
        startInput.value = filters.start_date || "";
        endInput.value = filters.end_date || "";
    }

    function renderSummary(summary, filters) {
        setText("metric-days-observed", String(summary.days_observed ?? 0));
        setText("metric-avg-glucose", summary.avg_glucose == null ? "-" : numberFormat.format(summary.avg_glucose));
        setText("metric-pct-hypo", formatPercent(summary.pct_hypo));
        setText("metric-pct-in-range", formatPercent(summary.pct_in_range));
        setText("metric-pct-hyper", formatPercent(summary.pct_hyper));
        setText("metric-anomaly-days", String(summary.anomaly_days ?? 0));
        setText("hero-in-range", formatPercent(summary.pct_in_range));
        setText("summary-measurements-badge", `${summary.glucose_measurements ?? 0} medicoes`);
        setText("legend-hypo", formatPercent(summary.pct_hypo));
        setText("legend-in-range", formatPercent(summary.pct_in_range));
        setText("legend-hyper", formatPercent(summary.pct_hyper));
        setText("selected-range-copy", `de ${formatDate(filters.start_date)} ate ${formatDate(filters.end_date)}`);
        setText("trend-caption", `Periodo ativo: ${formatDate(filters.start_date)} ate ${formatDate(filters.end_date)}`);
    }

    function destroyChart(chart) {
        if (chart) {
            chart.destroy();
        }
    }

    function renderTrendChart(indicators) {
        const ctx = document.getElementById("glucose-trend-chart");
        if (!ctx || !window.Chart) {
            return;
        }
        destroyChart(charts.trend);
        const labels = indicators.map((item) => shortDateFormat.format(new Date(`${item.date}T00:00:00`)));
        const avgData = indicators.map((item) => item.avg_glucose);
        charts.trend = new Chart(ctx, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Media glicemica",
                        data: avgData,
                        borderColor: "#167cd9",
                        backgroundColor: "rgba(22, 124, 217, 0.12)",
                        fill: true,
                        tension: 0.28,
                        pointRadius: 3,
                        pointHoverRadius: 4,
                    },
                    {
                        label: "Limiar de hipo",
                        data: labels.map(() => 70),
                        borderColor: "#e35d73",
                        borderDash: [6, 6],
                        pointRadius: 0,
                    },
                    {
                        label: "Limite de hiper",
                        data: labels.map(() => 180),
                        borderColor: "#f4a93d",
                        borderDash: [6, 6],
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { position: "bottom" },
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback(value) {
                                return `${value} mg/dL`;
                            },
                        },
                    },
                },
            },
        });
    }

    function renderDistributionChart(summary) {
        const ctx = document.getElementById("distribution-chart");
        if (!ctx || !window.Chart) {
            return;
        }
        destroyChart(charts.distribution);
        charts.distribution = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: ["Hipo", "Em faixa", "Hiper"],
                datasets: [
                    {
                        data: [summary.pct_hypo, summary.pct_in_range, summary.pct_hyper],
                        backgroundColor: ["#e35d73", "#19a86a", "#f4a93d"],
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                cutout: "68%",
            },
        });
    }

    function renderHourlyChart(hourlyLows, hourlyHighs) {
        const ctx = document.getElementById("hourly-extremes-chart");
        if (!ctx || !window.Chart) {
            return;
        }
        destroyChart(charts.hourly);
        const labels = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}h`);
        const lowByHour = Array.from({ length: 24 }, (_, hour) => hourlyLows.find((item) => item.hour === hour)?.count ?? 0);
        const highByHour = Array.from({ length: 24 }, (_, hour) => hourlyHighs.find((item) => item.hour === hour)?.count ?? 0);
        charts.hourly = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Eventos < 70 mg/dL",
                        data: lowByHour,
                        backgroundColor: "rgba(39, 183, 231, 0.65)",
                        borderRadius: 8,
                        borderSkipped: false,
                    },
                    {
                        label: "Eventos > 250 mg/dL",
                        data: highByHour,
                        backgroundColor: "rgba(244, 169, 61, 0.7)",
                        borderRadius: 8,
                        borderSkipped: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { precision: 0 },
                    },
                },
            },
        });
    }

    function renderRecentEvents(events) {
        const tbody = document.getElementById("recent-events-body");
        if (!tbody) {
            return;
        }
        if (!events.length) {
            tbody.innerHTML = buildEmptyRow(6, "Sem eventos", "Nao ha registros recentes para o intervalo selecionado.");
            return;
        }

        tbody.innerHTML = events
            .map((event) => {
                const typeTone = event.event_type === "glucose_measurement" ? "info" : "neutral";
                const value =
                    event.glucose_mg_dl != null
                        ? `${numberFormat.format(event.glucose_mg_dl)} mg/dL`
                        : event.numeric_value != null
                          ? numberFormat.format(event.numeric_value)
                          : "-";
                return `
                    <tr>
                        <td>${formatDateTime(event.occurred_at)}</td>
                        <td><span class="badge badge--${typeTone}">${String(event.event_type || "-").replaceAll("_", " ")}</span></td>
                        <td>${event.event_subtype || "-"}</td>
                        <td>${value}</td>
                        <td>${event.context_label || "-"}</td>
                        <td><span class="badge badge--neutral">${String(event.timestamp_quality || "-").replaceAll("_", " ")}</span></td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderIndicators(indicators) {
        const tbody = document.getElementById("daily-indicators-body");
        if (!tbody) {
            return;
        }
        if (!indicators.length) {
            tbody.innerHTML = buildEmptyRow(7, "Sem indicadores", "Nao ha indicadores diarios para o intervalo selecionado.");
            return;
        }

        tbody.innerHTML = indicators
            .map((indicator) => {
                const avg = indicator.avg_glucose == null ? "-" : `${numberFormat.format(indicator.avg_glucose)} mg/dL`;
                const anomalyTone = indicator.anomaly_flag ? "danger" : "neutral";
                return `
                    <tr>
                        <td>${formatDate(indicator.date)}</td>
                        <td>${avg}</td>
                        <td><span class="badge badge--danger">${formatPercent(indicator.pct_hypo)}</span></td>
                        <td><span class="badge badge--success">${formatPercent(indicator.pct_in_range)}</span></td>
                        <td><span class="badge badge--warning">${formatPercent(indicator.pct_hyper)}</span></td>
                        <td><span class="badge badge--${anomalyTone}">${indicator.anomaly_flag ? "Sim" : "Nao"}</span></td>
                        <td><span title="${indicator.cluster_profile_description || ""}">${indicator.cluster_profile_label || (indicator.cluster_label != null ? `Grupo ${indicator.cluster_label}` : "-")}</span></td>
                    </tr>
                `;
            })
            .join("");
    }

    async function loadAnalytics(startDate, endDate) {
        const params = new URLSearchParams();
        if (startDate) {
            params.set("start_date", startDate);
        }
        if (endDate) {
            params.set("end_date", endDate);
        }

        setStatus("Carregando dados do FastAPI...", "info");
        startInput.disabled = true;
        endInput.disabled = true;
        last30Button.disabled = true;

        try {
            const response = await fetch(`${apiUrl}?${params.toString()}`, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) {
                throw new Error(`Erro ${response.status}`);
            }
            const payload = await response.json();
            syncInputs(payload.filters);
            renderSummary(payload.summary, payload.filters);
            renderTrendChart(payload.daily_indicators);
            renderDistributionChart(payload.summary);
            renderHourlyChart(payload.hourly_lows, payload.hourly_highs_250 || []);
            renderRecentEvents(payload.recent_events);
            renderIndicators(payload.daily_indicators);
            updateUrl(payload.filters.start_date, payload.filters.end_date);
            setStatus("Dados analiticos atualizados via FastAPI", "success");
        } catch (error) {
            console.error(error);
            setStatus("Nao foi possivel atualizar os dados do periodo", "danger");
        } finally {
            startInput.disabled = false;
            endInput.disabled = false;
            last30Button.disabled = false;
        }
    }

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        loadAnalytics(startInput.value, endInput.value);
    });

    last30Button.addEventListener("click", function () {
        if (!startInput.min || !endInput.max) {
            return;
        }
        const range = computeLastThirtyDays(startInput.min, endInput.max);
        startInput.value = range.start;
        endInput.value = range.end;
        loadAnalytics(range.start, range.end);
    });

    loadAnalytics(app.dataset.startDate, app.dataset.endDate);
})();
