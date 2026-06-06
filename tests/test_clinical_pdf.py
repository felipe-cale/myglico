from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.clinical_pdf import build_daily_glucose_summaries, build_patient_report_pdf


def _event(day: str, time: str, glucose: float, context: str = "Sem contexto informado") -> dict[str, object]:
    return {
        "occurred_at": f"{day}T{time}:00",
        "event_date": day,
        "event_time": time,
        "event_type_label": "Medição de glicose",
        "event_subtype_label": context,
        "glucose_mg_dl": glucose,
        "context_label_display": context,
        "timestamp_quality_label": "Registrado",
    }


def _context(events: list[dict[str, object]], indicators: list[dict[str, object]] | None = None) -> dict[str, object]:
    if indicators is None:
        days = sorted({event["event_date"] for event in events})
        indicators = []
        for day in days:
            day_values = [float(event["glucose_mg_dl"]) for event in events if event["event_date"] == day]
            total = len(day_values)
            low = len([value for value in day_values if value < 70])
            high = len([value for value in day_values if value > 180])
            indicators.append(
                {
                    "date": day,
                    "avg_glucose": sum(day_values) / total if total else None,
                    "pct_hypo": (low / total) * 100 if total else 0,
                    "pct_in_range": ((total - low - high) / total) * 100 if total else 0,
                    "pct_hyper": (high / total) * 100 if total else 0,
                    "anomaly_flag": False,
                }
            )
    values = [float(event["glucose_mg_dl"]) for event in events]
    low = len([value for value in values if value < 70])
    high = len([value for value in values if value > 180])
    return {
        "patient": SimpleNamespace(display_name="Paciente Teste", source_file="data-test"),
        "filters": {"start_date": indicators[0]["date"], "end_date": indicators[-1]["date"]},
        "summary": {
            "days_observed": len(indicators),
            "avg_glucose": sum(item["avg_glucose"] for item in indicators if item["avg_glucose"] is not None) / len(indicators),
            "pct_hypo": sum(item["pct_hypo"] for item in indicators) / len(indicators),
            "pct_in_range": sum(item["pct_in_range"] for item in indicators) / len(indicators),
            "pct_hyper": sum(item["pct_hyper"] for item in indicators) / len(indicators),
            "anomaly_days": sum(1 for item in indicators if item.get("anomaly_flag")),
            "glucose_measurements": len(events),
        },
        "daily_indicators_json": indicators,
        "glucose_events_json": events,
        "recent_events_json": events[-20:],
        "hourly_lows": [],
        "hourly_highs_250": [],
    }


def _pdf_text(pdf: bytes) -> str:
    return pdf.decode("cp1252", errors="ignore")


class ClinicalPdfTests(unittest.TestCase):
    def test_daily_metrics_are_calculated_from_available_readings(self) -> None:
        context = _context([_event("2026-06-01", "08:00", 60), _event("2026-06-01", "12:00", 160), _event("2026-06-01", "18:00", 260)])

        summary = build_daily_glucose_summaries(context)[0]

        self.assertEqual(summary.count, 3)
        self.assertEqual(summary.min_glucose, 60)
        self.assertEqual(summary.max_glucose, 260)
        self.assertAlmostEqual(summary.pct_hypo, 33.3333, places=1)
        self.assertAlmostEqual(summary.pct_hyper, 33.3333, places=1)

    def test_hypoglycemia_day_is_attention_point(self) -> None:
        summary = build_daily_glucose_summaries(_context([_event("2026-06-01", "08:00", 61)]))[0]

        self.assertIn("Hipoglicemia", summary.attention_reasons)

    def test_critical_high_day_is_attention_point_at_250_or_more(self) -> None:
        summary = build_daily_glucose_summaries(_context([_event("2026-06-01", "08:00", 250)]))[0]

        self.assertIn("Risco elevado", summary.attention_reasons)

    def test_hyperglycemic_predominance_is_attention_point(self) -> None:
        summary = build_daily_glucose_summaries(
            _context([_event("2026-06-01", "08:00", 190), _event("2026-06-01", "12:00", 210)])
        )[0]

        self.assertIn("Predomínio hiperglicêmico", summary.attention_reasons)

    def test_pdf_contains_required_sections_and_removes_source_field(self) -> None:
        context = _context([_event("2026-06-01", "08:00", 61), _event("2026-06-01", "12:00", 260)])

        text = _pdf_text(build_patient_report_pdf(context))

        self.assertNotIn("Fonte", text)
        self.assertNotIn("Interpretação", text)
        self.assertNotIn("Conclusão interpretativa automatizada", text)
        self.assertNotIn("Confiabilidade", text)
        self.assertIn("Dias atípicos e pontos de atenção", text)
        self.assertIn("Análise detalhada do período", text)
        self.assertIn("Média glicêmica diária", text)
        self.assertIn("Sem contexto informado", text)

    def test_pdf_handles_few_data_points_in_day(self) -> None:
        context = _context([_event("2026-06-01", "08:00", 110)])

        text = _pdf_text(build_patient_report_pdf(context))

        self.assertIn("Leituras", text)
        self.assertIn("00h", text)
        self.assertIn("24h", text)

    def test_table_headers_repeat_after_page_break(self) -> None:
        events = [_event("2026-06-01", f"{index % 24:02d}:00", 80 + (index % 190)) for index in range(90)]
        context = _context(events)

        text = _pdf_text(build_patient_report_pdf(context))

        self.assertGreaterEqual(text.count("Quando"), 2)

    def test_pdf_uses_landscape_pages_after_cover_page(self) -> None:
        events = [_event("2026-06-01", "08:00", 110), _event("2026-06-02", "08:00", 260)]
        pdf = build_patient_report_pdf(_context(events))
        raw = pdf.decode("latin-1", errors="ignore")

        self.assertIn("/MediaBox [0 0 595.28 841.89]", raw)
        self.assertIn("/MediaBox [0 0 841.89 595.28]", raw)


if __name__ == "__main__":
    unittest.main()
