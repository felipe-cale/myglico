from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import ceil
from pathlib import Path
import re
import zlib
from zoneinfo import ZoneInfo


PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
LANDSCAPE_PAGE_WIDTH = PAGE_HEIGHT
LANDSCAPE_PAGE_HEIGHT = PAGE_WIDTH
MARGIN_X = 36.0
MARGIN_TOP = 34.0
MARGIN_BOTTOM = 34.0

HYPO_LIMIT = 70.0
HYPER_LIMIT = 180.0
CRITICAL_HYPER_LIMIT = 250.0

COLOR_TEXT = (0.08, 0.13, 0.20)
COLOR_MUTED = (0.33, 0.40, 0.49)
COLOR_BORDER = (0.79, 0.84, 0.89)
COLOR_PANEL = (0.97, 0.98, 0.99)
COLOR_BLUE = (0.12, 0.46, 0.72)
COLOR_BRAND_GREEN = (0.14, 0.70, 0.44)
COLOR_BRAND_CYAN = (0.50, 0.79, 0.96)
COLOR_BRAND_YELLOW = (1.0, 0.82, 0.35)
COLOR_HYPO = (0.79, 0.23, 0.31)
COLOR_TARGET = (0.09, 0.53, 0.35)
COLOR_HYPER = (0.78, 0.47, 0.09)
COLOR_CRITICAL = (0.46, 0.32, 0.72)

THRESHOLDS = [
    ("hypo", "< 70 mg/dL", COLOR_HYPO),
    ("target", "70 a 180 mg/dL", COLOR_TARGET),
    ("hyper", "> 180 mg/dL", COLOR_HYPER),
    ("critical", ">= 250 mg/dL", COLOR_CRITICAL),
]

DEFAULT_LANG = "pt-BR"
SUPPORTED_LANGS = ("pt-BR", "en-US", "es")

WEEKDAY_NAMES: dict[str, list[str]] = {
    "pt-BR": ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"],
    "en-US": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
}

LOCALIZED_EVENT_TYPE_LABELS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "glucose_measurement": "Medição de glicose", "insulin_dose": "Dose de insulina", "symptom": "Sintoma",
        "meal": "Alimentação", "exercise": "Exercício", "special_event": "Evento especial", "unknown": "Desconhecido",
    },
    "en-US": {
        "glucose_measurement": "Glucose measurement", "insulin_dose": "Insulin dose", "symptom": "Symptom",
        "meal": "Meal", "exercise": "Exercise", "special_event": "Special event", "unknown": "Unknown",
    },
    "es": {
        "glucose_measurement": "Medición de glucosa", "insulin_dose": "Dosis de insulina", "symptom": "Síntoma",
        "meal": "Alimentación", "exercise": "Ejercicio", "special_event": "Evento especial", "unknown": "Desconocido",
    },
}

LOCALIZED_EVENT_SUBTYPE_LABELS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "regular": "Insulina regular", "nph": "Insulina NPH", "ultralente": "Insulina ultralente", "unspecified": "Não especificado",
        "pre_breakfast": "Antes do café da manhã", "post_breakfast": "Após o café da manhã", "pre_lunch": "Antes do almoço",
        "post_lunch": "Após o almoço", "pre_supper": "Antes do jantar", "post_supper": "Após o jantar", "pre_snack": "Antes do lanche",
        "hypoglycemic_symptom": "Sintoma de hipoglicemia", "typical_meal": "Refeição usual", "more_than_usual_meal": "Refeição acima do usual",
        "less_than_usual_meal": "Refeição abaixo do usual", "typical_exercise": "Exercício usual", "more_than_usual_exercise": "Exercício acima do usual",
        "less_than_usual_exercise": "Exercício abaixo do usual", "unspecified_special_event": "Evento especial não especificado", "unknown": "Desconhecido",
    },
    "en-US": {
        "regular": "Regular insulin", "nph": "NPH insulin", "ultralente": "Ultralente insulin", "unspecified": "Unspecified",
        "pre_breakfast": "Before breakfast", "post_breakfast": "After breakfast", "pre_lunch": "Before lunch",
        "post_lunch": "After lunch", "pre_supper": "Before dinner", "post_supper": "After dinner", "pre_snack": "Before snack",
        "hypoglycemic_symptom": "Hypoglycemia symptom", "typical_meal": "Usual meal", "more_than_usual_meal": "Larger than usual meal",
        "less_than_usual_meal": "Smaller than usual meal", "typical_exercise": "Usual exercise", "more_than_usual_exercise": "More exercise than usual",
        "less_than_usual_exercise": "Less exercise than usual", "unspecified_special_event": "Unspecified special event", "unknown": "Unknown",
    },
    "es": {
        "regular": "Insulina regular", "nph": "Insulina NPH", "ultralente": "Insulina ultralenta", "unspecified": "No especificado",
        "pre_breakfast": "Antes del desayuno", "post_breakfast": "Después del desayuno", "pre_lunch": "Antes del almuerzo",
        "post_lunch": "Después del almuerzo", "pre_supper": "Antes de la cena", "post_supper": "Después de la cena", "pre_snack": "Antes de la merienda",
        "hypoglycemic_symptom": "Síntoma de hipoglucemia", "typical_meal": "Comida habitual", "more_than_usual_meal": "Comida mayor de lo habitual",
        "less_than_usual_meal": "Comida menor de lo habitual", "typical_exercise": "Ejercicio habitual", "more_than_usual_exercise": "Ejercicio mayor de lo habitual",
        "less_than_usual_exercise": "Ejercicio menor de lo habitual", "unspecified_special_event": "Evento especial no especificado", "unknown": "Desconocido",
    },
}

LOCALIZED_CONTEXT_LABELS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "unspecified": "Sem contexto informado", "pre_breakfast": "Antes do café da manhã", "post_breakfast": "Após o café da manhã",
        "pre_lunch": "Antes do almoço", "post_lunch": "Após o almoço", "pre_supper": "Antes do jantar", "post_supper": "Após o jantar",
        "pre_snack": "Antes do lanche",
    },
    "en-US": {
        "unspecified": "No context provided", "pre_breakfast": "Before breakfast", "post_breakfast": "After breakfast",
        "pre_lunch": "Before lunch", "post_lunch": "After lunch", "pre_supper": "Before dinner", "post_supper": "After dinner",
        "pre_snack": "Before snack",
    },
    "es": {
        "unspecified": "Sin contexto informado", "pre_breakfast": "Antes del desayuno", "post_breakfast": "Después del desayuno",
        "pre_lunch": "Antes del almuerzo", "post_lunch": "Después del almuerzo", "pre_supper": "Antes de la cena", "post_supper": "Después de la cena",
        "pre_snack": "Antes de la merienda",
    },
}

STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "threshold_hypo": "Hipoglicemia",
        "threshold_target": "Faixa alvo",
        "threshold_hyper": "Hiperglicemia",
        "threshold_critical": "Risco elevado",
        "classify_hypo": "Hipoglicemia",
        "classify_critical": "Risco elevado",
        "classify_hyper": "Hiperglicemia",
        "classify_in_range": "Em faixa",
        "profile_hyper": "Perfil hiperglicêmico",
        "profile_hypo": "Perfil hipoglicêmico",
        "profile_stable": "Perfil em faixa",
        "reason_anomaly_day": "Dia estatisticamente atípico",
        "reason_hypo": "Hipoglicemia",
        "reason_critical": "Risco elevado",
        "reason_hyper_predominance": "Predomínio hiperglicêmico",
        "reason_all_out_of_range": "100% fora da faixa alvo",
        "reason_high_variability": "Alta variabilidade",
        "reason_avg_too_low": "Média diária muito baixa",
        "reason_avg_too_high": "Média diária muito alta",
        "note_flagged_automated": "sinalizado pela análise automatizada",
        "note_readings_low": "{n} leitura(s) < 70 mg/dL",
        "note_readings_critical": "{n} leitura(s) >= 250 mg/dL",
        "note_pct_hyper": "{pct} das leituras do dia > 180 mg/dL",
        "note_no_in_range_reading": "nenhuma leitura entre 70 e 180 mg/dL",
        "note_amplitude": "amplitude diária de {value} mg/dL",
        "note_avg_below_hypo": "média do dia abaixo de 70 mg/dL",
        "note_avg_above_critical": "média do dia >= 250 mg/dL",
        "no_alert": "Sem alerta",
        "footer_text": "MyGlico - relatório gerado automaticamente para apoio à revisão clínica. Não substitui avaliação médica.",
        "page_label": "Página {n}",
        "report_title": "Relatório glicêmico",
        "period_joiner": " a ",
        "header_subtitle": "Resumo do controle glicêmico no período analisado",
        "generated_at_label": "Data da geração",
        "header_intro": "Relatório glicêmico referente ao período de {period}, gerado para apoio à revisão clínica.",
        "label_patient": "Paciente",
        "label_period_analyzed": "Período analisado",
        "label_measurements": "Medições",
        "label_days_observed": "Dias observados",
        "label_period_profile": "Perfil do período",
        "card_avg_glucose": "Média glicêmica",
        "card_pct_hypo": "% hipo",
        "card_pct_range": "% faixa alvo",
        "card_pct_hyper": "% hiper",
        "card_critical_risk": "Risco elevado",
        "card_min_max": "Mín / Máx",
        "card_anomaly_days": "Dias atípicos",
        "card_attention_points": "Pontos atenção",
        "summary_title": "Resultados do acompanhamento glicêmico",
        "row_avg_glucose_daily": "Média glicêmica diária",
        "row_pct_hypo_daily": "% médio diário em hipoglicemia",
        "row_pct_range_daily": "% médio diário em faixa alvo",
        "row_pct_hyper_daily": "% médio diário em hiperglicemia",
        "row_critical_events": "Eventos de risco elevado",
        "row_min_max_reading": "Menor / maior leitura",
        "row_anomaly_days": "Dias atípicos",
        "ref_operational_range": "Faixa operacional do painel: 70 a 180 mg/dL",
        "ref_hypo": "Hipoglicemia: < 70 mg/dL",
        "ref_target": "Faixa alvo: 70 a 180 mg/dL",
        "ref_hyper": "Hiperglicemia: > 180 mg/dL",
        "ref_critical": "Risco elevado: >= 250 mg/dL",
        "ref_thresholds_used": "Limiares usados: 70, 180 e 250 mg/dL",
        "ref_auto_flagging": "Sinalização automática do detalhamento",
        "n_readings": "{n} leitura(s)",
        "col_exam_indicator": "Exame / indicador",
        "col_result": "Resultado",
        "col_reference_value": "Valor de referência",
        "notes_hypo_relevant": "Percentual relevante de hipoglicemia; revisar horários, alimentação e conduta em contexto clínico.",
        "notes_hyper_predominance": "Predomínio hiperglicêmico no período, conforme critérios de triagem do painel.",
        "notes_critical_readings": "{n} leitura(s) atingiram faixa de risco elevado (>= 250 mg/dL).",
        "notes_anomaly_days": "{n} dia(s) foram sinalizados como atípicos pela análise automatizada.",
        "notes_no_alerts": "Sem alertas automáticos relevantes no recorte, considerando os limiares configurados.",
        "notes_pct_follow_detail": "Percentuais do resumo seguem o detalhamento do paciente e representam médias dos indicadores diários no período.",
        "threshold_legend_title": "Legenda dos limiares glicêmicos",
        "distribution_title": "Distribuição glicêmica do período",
        "chart_no_data": "Sem dados suficientes para o gráfico.",
        "chart_daily_avg_title": "Média glicêmica diária",
        "hourly_extremes_title": "Ocorrências críticas por horário",
        "note_hypo_and_critical": "Hipoglicemia e risco >= 250 mg/dL",
        "note_hypo_only": "Hipoglicemia < 70 mg/dL",
        "note_critical_only": "Risco >= 250 mg/dL",
        "no_critical_occurrences": "Sem ocorrências críticas no período",
        "col_time": "Horário",
        "col_lt_70": "< 70 mg/dL",
        "col_gte_250": ">= 250 mg/dL",
        "col_observation": "Observação",
        "daily_table_title": "Indicadores diários consolidados",
        "col_date": "Data",
        "col_count": "Qtd",
        "col_avg": "Média",
        "col_min": "Mín",
        "col_max": "Máx",
        "col_pct_hypo": "% hipo",
        "col_pct_range": "% faixa",
        "col_pct_hyper": "% hiper",
        "col_alert": "Alerta",
        "attention_marker_label": "Traço lateral bege/laranja: dia com ponto de atenção",
        "attention_marker_desc": "Indica dias que atingiram critérios automáticos de alerta.",
        "attention_days_title": "Dias atípicos e pontos de atenção",
        "attention_days_empty": "Nenhum dia do período atingiu os critérios automáticos de ponto de atenção.",
        "col_alert_h": "Alerta",
        "col_reason": "Motivo",
        "col_min_max": "Mín/Máx",
        "col_hfhiper": "H/F/Hiper",
        "col_extremes": "Extremos",
        "col_context": "Contexto",
        "readings_table_title": "Leituras glicêmicas completas",
        "col_when": "Quando",
        "col_type": "Tipo",
        "col_subtype": "Subtipo",
        "col_value": "Valor",
        "badge_attention": "Ponto de atenção",
        "badge_no_alert": "Sem alerta automático",
        "metric_readings": "Leituras",
        "metric_avg": "Média",
        "metric_min_max": "Mín/Máx",
        "metric_pct_hfhiper": "% H/F/Hiper",
        "day_chart_caption": "Pontos = leituras pontuais. Linha discreta apenas facilita a leitura visual.",
        "day_readings_title": "Leituras do dia",
        "col_hour": "Hora",
        "col_value_short": "Valor",
        "col_context_short": "Contexto",
        "col_class": "Classe",
        "more_readings": "+ {n} leitura(s) no anexo",
        "reason_prefix": "Motivo: {note}",
        "detailed_analysis_title": "Análise detalhada do período",
        "detailed_analysis_intro": "Os gráficos diários usam eixo de 00h a 24h e exibem apenas leituras glicêmicas reais registradas no MyGlico.",
        "block_label": "Bloco {n}: {start} a {end}",
        "filename_start_fallback": "inicio",
        "filename_end_fallback": "fim",
        "filename_prefix": "relatorio-glicemico",
    },
    "en-US": {
        "threshold_hypo": "Hypoglycemia",
        "threshold_target": "Target range",
        "threshold_hyper": "Hyperglycemia",
        "threshold_critical": "High risk",
        "classify_hypo": "Hypoglycemia",
        "classify_critical": "High risk",
        "classify_hyper": "Hyperglycemia",
        "classify_in_range": "In range",
        "profile_hyper": "Hyperglycemic profile",
        "profile_hypo": "Hypoglycemic profile",
        "profile_stable": "In-range profile",
        "reason_anomaly_day": "Statistically atypical day",
        "reason_hypo": "Hypoglycemia",
        "reason_critical": "High risk",
        "reason_hyper_predominance": "Hyperglycemic predominance",
        "reason_all_out_of_range": "100% outside target range",
        "reason_high_variability": "High variability",
        "reason_avg_too_low": "Daily average too low",
        "reason_avg_too_high": "Daily average too high",
        "note_flagged_automated": "flagged by automated analysis",
        "note_readings_low": "{n} reading(s) < 70 mg/dL",
        "note_readings_critical": "{n} reading(s) >= 250 mg/dL",
        "note_pct_hyper": "{pct} of the day's readings > 180 mg/dL",
        "note_no_in_range_reading": "no reading between 70 and 180 mg/dL",
        "note_amplitude": "daily amplitude of {value} mg/dL",
        "note_avg_below_hypo": "day's average below 70 mg/dL",
        "note_avg_above_critical": "day's average >= 250 mg/dL",
        "no_alert": "No alert",
        "footer_text": "MyGlico - report automatically generated to support clinical review. It does not replace medical evaluation.",
        "page_label": "Page {n}",
        "report_title": "Glucose report",
        "period_joiner": " to ",
        "header_subtitle": "Summary of glucose control over the analyzed period",
        "generated_at_label": "Generated on",
        "header_intro": "Glucose report for the period of {period}, generated to support clinical review.",
        "label_patient": "Patient",
        "label_period_analyzed": "Period analyzed",
        "label_measurements": "Measurements",
        "label_days_observed": "Days observed",
        "label_period_profile": "Period profile",
        "card_avg_glucose": "Average glucose",
        "card_pct_hypo": "% hypo",
        "card_pct_range": "% target range",
        "card_pct_hyper": "% hyper",
        "card_critical_risk": "High risk",
        "card_min_max": "Min / Max",
        "card_anomaly_days": "Atypical days",
        "card_attention_points": "Attention points",
        "summary_title": "Glucose monitoring results",
        "row_avg_glucose_daily": "Daily average glucose",
        "row_pct_hypo_daily": "Average daily % in hypoglycemia",
        "row_pct_range_daily": "Average daily % in target range",
        "row_pct_hyper_daily": "Average daily % in hyperglycemia",
        "row_critical_events": "High-risk events",
        "row_min_max_reading": "Lowest / highest reading",
        "row_anomaly_days": "Atypical days",
        "ref_operational_range": "Panel operating range: 70 to 180 mg/dL",
        "ref_hypo": "Hypoglycemia: < 70 mg/dL",
        "ref_target": "Target range: 70 to 180 mg/dL",
        "ref_hyper": "Hyperglycemia: > 180 mg/dL",
        "ref_critical": "High risk: >= 250 mg/dL",
        "ref_thresholds_used": "Thresholds used: 70, 180 and 250 mg/dL",
        "ref_auto_flagging": "Automatic flagging from the detailed breakdown",
        "n_readings": "{n} reading(s)",
        "col_exam_indicator": "Test / indicator",
        "col_result": "Result",
        "col_reference_value": "Reference value",
        "notes_hypo_relevant": "Significant percentage of hypoglycemia; review timing, diet, and management in a clinical context.",
        "notes_hyper_predominance": "Hyperglycemic predominance in the period, per the panel's screening criteria.",
        "notes_critical_readings": "{n} reading(s) reached the high-risk range (>= 250 mg/dL).",
        "notes_anomaly_days": "{n} day(s) were flagged as atypical by automated analysis.",
        "notes_no_alerts": "No relevant automatic alerts in this selection, considering the configured thresholds.",
        "notes_pct_follow_detail": "Summary percentages follow the patient's detailed breakdown and represent averages of the daily indicators over the period.",
        "threshold_legend_title": "Glucose threshold legend",
        "distribution_title": "Glucose distribution for the period",
        "chart_no_data": "Not enough data for the chart.",
        "chart_daily_avg_title": "Daily average glucose",
        "hourly_extremes_title": "Critical occurrences by hour",
        "note_hypo_and_critical": "Hypoglycemia and risk >= 250 mg/dL",
        "note_hypo_only": "Hypoglycemia < 70 mg/dL",
        "note_critical_only": "Risk >= 250 mg/dL",
        "no_critical_occurrences": "No critical occurrences in the period",
        "col_time": "Time",
        "col_lt_70": "< 70 mg/dL",
        "col_gte_250": ">= 250 mg/dL",
        "col_observation": "Note",
        "daily_table_title": "Consolidated daily indicators",
        "col_date": "Date",
        "col_count": "Count",
        "col_avg": "Avg",
        "col_min": "Min",
        "col_max": "Max",
        "col_pct_hypo": "% hypo",
        "col_pct_range": "% range",
        "col_pct_hyper": "% hyper",
        "col_alert": "Alert",
        "attention_marker_label": "Beige/orange side stripe: day with an attention point",
        "attention_marker_desc": "Indicates days that met automatic alert criteria.",
        "attention_days_title": "Atypical days and attention points",
        "attention_days_empty": "No day in the period met the automatic attention-point criteria.",
        "col_alert_h": "Alert",
        "col_reason": "Reason",
        "col_min_max": "Min/Max",
        "col_hfhiper": "H/R/Hyper",
        "col_extremes": "Extremes",
        "col_context": "Context",
        "readings_table_title": "Complete glucose readings",
        "col_when": "When",
        "col_type": "Type",
        "col_subtype": "Subtype",
        "col_value": "Value",
        "badge_attention": "Attention point",
        "badge_no_alert": "No automatic alert",
        "metric_readings": "Readings",
        "metric_avg": "Average",
        "metric_min_max": "Min/Max",
        "metric_pct_hfhiper": "% H/R/Hyper",
        "day_chart_caption": "Dots = individual readings. The faint line is only for visual reading ease.",
        "day_readings_title": "Day's readings",
        "col_hour": "Time",
        "col_value_short": "Value",
        "col_context_short": "Context",
        "col_class": "Class",
        "more_readings": "+ {n} reading(s) in the appendix",
        "reason_prefix": "Reason: {note}",
        "detailed_analysis_title": "Detailed period analysis",
        "detailed_analysis_intro": "The daily charts use a 00h to 24h axis and show only actual glucose readings recorded in MyGlico.",
        "block_label": "Block {n}: {start} to {end}",
        "filename_start_fallback": "start",
        "filename_end_fallback": "end",
        "filename_prefix": "glucose-report",
    },
    "es": {
        "threshold_hypo": "Hipoglucemia",
        "threshold_target": "Rango objetivo",
        "threshold_hyper": "Hiperglucemia",
        "threshold_critical": "Riesgo elevado",
        "classify_hypo": "Hipoglucemia",
        "classify_critical": "Riesgo elevado",
        "classify_hyper": "Hiperglucemia",
        "classify_in_range": "En rango",
        "profile_hyper": "Perfil hiperglucémico",
        "profile_hypo": "Perfil hipoglucémico",
        "profile_stable": "Perfil en rango",
        "reason_anomaly_day": "Día estadísticamente atípico",
        "reason_hypo": "Hipoglucemia",
        "reason_critical": "Riesgo elevado",
        "reason_hyper_predominance": "Predominio hiperglucémico",
        "reason_all_out_of_range": "100% fuera del rango objetivo",
        "reason_high_variability": "Alta variabilidad",
        "reason_avg_too_low": "Media diaria muy baja",
        "reason_avg_too_high": "Media diaria muy alta",
        "note_flagged_automated": "señalado por el análisis automatizado",
        "note_readings_low": "{n} lectura(s) < 70 mg/dL",
        "note_readings_critical": "{n} lectura(s) >= 250 mg/dL",
        "note_pct_hyper": "{pct} de las lecturas del día > 180 mg/dL",
        "note_no_in_range_reading": "ninguna lectura entre 70 y 180 mg/dL",
        "note_amplitude": "amplitud diaria de {value} mg/dL",
        "note_avg_below_hypo": "media del día por debajo de 70 mg/dL",
        "note_avg_above_critical": "media del día >= 250 mg/dL",
        "no_alert": "Sin alerta",
        "footer_text": "MyGlico - informe generado automáticamente para apoyar la revisión clínica. No sustituye la evaluación médica.",
        "page_label": "Página {n}",
        "report_title": "Informe glucémico",
        "period_joiner": " a ",
        "header_subtitle": "Resumen del control glucémico en el período analizado",
        "generated_at_label": "Fecha de generación",
        "header_intro": "Informe glucémico correspondiente al período de {period}, generado para apoyar la revisión clínica.",
        "label_patient": "Paciente",
        "label_period_analyzed": "Período analizado",
        "label_measurements": "Mediciones",
        "label_days_observed": "Días observados",
        "label_period_profile": "Perfil del período",
        "card_avg_glucose": "Glucosa media",
        "card_pct_hypo": "% hipo",
        "card_pct_range": "% rango objetivo",
        "card_pct_hyper": "% hiper",
        "card_critical_risk": "Riesgo elevado",
        "card_min_max": "Mín / Máx",
        "card_anomaly_days": "Días atípicos",
        "card_attention_points": "Puntos de atención",
        "summary_title": "Resultados del seguimiento glucémico",
        "row_avg_glucose_daily": "Glucosa media diaria",
        "row_pct_hypo_daily": "% medio diario en hipoglucemia",
        "row_pct_range_daily": "% medio diario en rango objetivo",
        "row_pct_hyper_daily": "% medio diario en hiperglucemia",
        "row_critical_events": "Eventos de riesgo elevado",
        "row_min_max_reading": "Lectura mínima / máxima",
        "row_anomaly_days": "Días atípicos",
        "ref_operational_range": "Rango operativo del panel: 70 a 180 mg/dL",
        "ref_hypo": "Hipoglucemia: < 70 mg/dL",
        "ref_target": "Rango objetivo: 70 a 180 mg/dL",
        "ref_hyper": "Hiperglucemia: > 180 mg/dL",
        "ref_critical": "Riesgo elevado: >= 250 mg/dL",
        "ref_thresholds_used": "Umbrales utilizados: 70, 180 y 250 mg/dL",
        "ref_auto_flagging": "Señalización automática del detalle",
        "n_readings": "{n} lectura(s)",
        "col_exam_indicator": "Examen / indicador",
        "col_result": "Resultado",
        "col_reference_value": "Valor de referencia",
        "notes_hypo_relevant": "Porcentaje relevante de hipoglucemia; revisar horarios, alimentación y manejo en el contexto clínico.",
        "notes_hyper_predominance": "Predominio hiperglucémico en el período, según los criterios de detección del panel.",
        "notes_critical_readings": "{n} lectura(s) alcanzaron el rango de riesgo elevado (>= 250 mg/dL).",
        "notes_anomaly_days": "{n} día(s) fueron señalados como atípicos por el análisis automatizado.",
        "notes_no_alerts": "Sin alertas automáticas relevantes en el recorte, considerando los umbrales configurados.",
        "notes_pct_follow_detail": "Los porcentajes del resumen siguen el detalle del paciente y representan promedios de los indicadores diarios en el período.",
        "threshold_legend_title": "Leyenda de los umbrales glucémicos",
        "distribution_title": "Distribución glucémica del período",
        "chart_no_data": "Datos insuficientes para el gráfico.",
        "chart_daily_avg_title": "Glucosa media diaria",
        "hourly_extremes_title": "Ocurrencias críticas por horario",
        "note_hypo_and_critical": "Hipoglucemia y riesgo >= 250 mg/dL",
        "note_hypo_only": "Hipoglucemia < 70 mg/dL",
        "note_critical_only": "Riesgo >= 250 mg/dL",
        "no_critical_occurrences": "Sin ocurrencias críticas en el período",
        "col_time": "Horario",
        "col_lt_70": "< 70 mg/dL",
        "col_gte_250": ">= 250 mg/dL",
        "col_observation": "Observación",
        "daily_table_title": "Indicadores diarios consolidados",
        "col_date": "Fecha",
        "col_count": "Cant",
        "col_avg": "Media",
        "col_min": "Mín",
        "col_max": "Máx",
        "col_pct_hypo": "% hipo",
        "col_pct_range": "% rango",
        "col_pct_hyper": "% hiper",
        "col_alert": "Alerta",
        "attention_marker_label": "Franja lateral beige/naranja: día con punto de atención",
        "attention_marker_desc": "Indica días que cumplieron criterios automáticos de alerta.",
        "attention_days_title": "Días atípicos y puntos de atención",
        "attention_days_empty": "Ningún día del período cumplió los criterios automáticos de punto de atención.",
        "col_alert_h": "Alerta",
        "col_reason": "Motivo",
        "col_min_max": "Mín/Máx",
        "col_hfhiper": "H/R/Hiper",
        "col_extremes": "Extremos",
        "col_context": "Contexto",
        "readings_table_title": "Lecturas glucémicas completas",
        "col_when": "Cuándo",
        "col_type": "Tipo",
        "col_subtype": "Subtipo",
        "col_value": "Valor",
        "badge_attention": "Punto de atención",
        "badge_no_alert": "Sin alerta automática",
        "metric_readings": "Lecturas",
        "metric_avg": "Media",
        "metric_min_max": "Mín/Máx",
        "metric_pct_hfhiper": "% H/R/Hiper",
        "day_chart_caption": "Los puntos = lecturas individuales. La línea discreta solo facilita la lectura visual.",
        "day_readings_title": "Lecturas del día",
        "col_hour": "Hora",
        "col_value_short": "Valor",
        "col_context_short": "Contexto",
        "col_class": "Clase",
        "more_readings": "+ {n} lectura(s) en el anexo",
        "reason_prefix": "Motivo: {note}",
        "detailed_analysis_title": "Análisis detallado del período",
        "detailed_analysis_intro": "Los gráficos diarios usan un eje de 00h a 24h y muestran solo lecturas glucémicas reales registradas en MyGlico.",
        "block_label": "Bloque {n}: {start} a {end}",
        "filename_start_fallback": "inicio",
        "filename_end_fallback": "fin",
        "filename_prefix": "informe-glucemico",
    },
}


def _translate(lang: str, key: str, **kwargs: object) -> str:
    lang_strings = STRINGS.get(lang) or STRINGS[DEFAULT_LANG]
    template = lang_strings.get(key)
    if template is None:
        template = STRINGS[DEFAULT_LANG].get(key, key)
    return template.format(**kwargs) if kwargs else template


def _localized_lookup(code: object, lang: str, mapping: dict[str, dict[str, str]]) -> str:
    if not code:
        return "-"
    lookup = mapping.get(lang) or mapping.get(DEFAULT_LANG, {})
    code_str = str(code)
    if code_str in lookup:
        return lookup[code_str]
    return code_str.replace("_", " ").title()


LOGO_IMAGE_PATH = Path(__file__).resolve().parents[2] / "frontend-react" / "public" / "img" / "myglico-logo-report.png"
REPORT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
_PNG_IMAGE_CACHE: dict[tuple[Path, int], PdfImage | None] = {}


def _pdf_literal(value: object) -> bytes:
    text = str(value or "")
    data = text.encode("cp1252", errors="replace")
    escaped = bytearray()
    for byte in data:
        if byte in (40, 41, 92):
            escaped.append(92)
        escaped.append(byte)
    return b"(" + bytes(escaped) + b")"


def _rgb(color: tuple[float, float, float]) -> str:
    return f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f}"


def _format_number(value: object, suffix: str = "", lang: str = DEFAULT_LANG) -> str:
    try:
        if value is None:
            return "-"
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if lang == "en-US":
        formatted = f"{number:,.1f}"
    else:
        formatted = f"{number:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}{suffix}"


def _format_date(value: object, lang: str = DEFAULT_LANG) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        date_value = value.date()
    else:
        date_value = datetime.fromisoformat(str(value)).date()
    pattern = "%m/%d/%Y" if lang == "en-US" else "%d/%m/%Y"
    return date_value.strftime(pattern)


def _format_datetime(value: object, lang: str = DEFAULT_LANG) -> str:
    if not value:
        return "-"
    date_value = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    pattern = "%m/%d/%Y %H:%M" if lang == "en-US" else "%d/%m/%Y %H:%M"
    return date_value.strftime(pattern)


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").lower()
    return normalized or "paciente"


def _text_width(text: str, size: float, bold: bool = False) -> float:
    width = 0.0
    for char in text:
        if char == " ":
            width += 0.28
        elif char in "il.,:;!|":
            width += 0.25
        elif char in "mwMW":
            width += 0.85
        elif char.isupper():
            width += 0.62
        else:
            width += 0.50
    return width * size * (1.04 if bold else 1.0)


def _wrap_text(text: object, size: float, max_width: float, bold: bool = False) -> list[str]:
    clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean_text:
        return [""]

    lines: list[str] = []
    current = ""
    for word in clean_text.split(" "):
        candidate = f"{current} {word}".strip()
        if current and _text_width(candidate, size, bold=bold) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _classify_glucose(value: object) -> tuple[str, tuple[float, float, float]]:
    """Returns a language-neutral classification code (hypo/critical/hyper/in_range), not display text."""
    try:
        glucose = float(value)
    except (TypeError, ValueError):
        return "-", COLOR_MUTED
    if glucose < HYPO_LIMIT:
        return "hypo", COLOR_HYPO
    if glucose >= CRITICAL_HYPER_LIMIT:
        return "critical", COLOR_CRITICAL
    if glucose > HYPER_LIMIT:
        return "hyper", COLOR_HYPER
    return "in_range", COLOR_TARGET


def _event_stats(events: list[dict[str, object]]) -> dict[str, object]:
    values = [float(event["glucose_mg_dl"]) for event in events if event.get("glucose_mg_dl") is not None]
    total = len(values)
    low = len([value for value in values if value < HYPO_LIMIT])
    high = len([value for value in values if value > HYPER_LIMIT])
    critical = len([value for value in values if value >= CRITICAL_HYPER_LIMIT])
    in_range = max(total - low - high, 0)
    return {
        "count": total,
        "avg": sum(values) / total if total else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "pct_hypo": (low / total) * 100 if total else 0,
        "pct_in_range": (in_range / total) * 100 if total else 0,
        "pct_hyper": (high / total) * 100 if total else 0,
        "low_count": low,
        "high_count": high,
        "critical_count": critical,
    }


def _profile_label(indicator: dict[str, object]) -> str:
    label = indicator.get("cluster_profile_label")
    if label:
        return str(label)
    cluster_label = indicator.get("cluster_label")
    if cluster_label is not None:
        return f"Grupo {cluster_label}"
    return "-"


def _dominant_profile(indicators: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for indicator in indicators:
        label = _profile_label(indicator)
        if label != "-":
            counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "-"
    return max(counts.items(), key=lambda item: item[1])[0]


def _period_profile(summary: dict[str, object], lang: str = DEFAULT_LANG) -> str:
    avg = float(summary.get("avg_glucose") or 0)
    pct_hypo = float(summary.get("pct_hypo") or 0)
    pct_hyper = float(summary.get("pct_hyper") or 0)
    if pct_hyper >= 65 or avg >= 185:
        return _translate(lang, "profile_hyper")
    if pct_hypo >= 10:
        return _translate(lang, "profile_hypo")
    return _translate(lang, "profile_stable")


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _event_date_key(event: dict[str, object]) -> str:
    if event.get("event_date"):
        return str(event["event_date"])
    occurred_at = _parse_datetime(event.get("occurred_at"))
    return occurred_at.date().isoformat() if occurred_at else ""


def _event_time_minutes(event: dict[str, object]) -> int:
    occurred_at = _parse_datetime(event.get("occurred_at"))
    if occurred_at:
        return occurred_at.hour * 60 + occurred_at.minute
    event_time = str(event.get("event_time") or "00:00")
    try:
        hour, minute = event_time.split(":", 1)
        return int(hour) * 60 + int(minute[:2])
    except (ValueError, TypeError):
        return 0


def _weekday_label(date_value: object, lang: str = DEFAULT_LANG) -> str:
    names = WEEKDAY_NAMES.get(lang) or WEEKDAY_NAMES[DEFAULT_LANG]
    parsed = datetime.fromisoformat(str(date_value)).date()
    return names[parsed.weekday()]


@dataclass(slots=True)
class DailyGlucoseSummary:
    date: str
    events: list[dict[str, object]]
    avg_glucose: float | None
    pct_hypo: float
    pct_in_range: float
    pct_hyper: float
    anomaly_flag: bool
    profile_label: str
    count: int
    min_glucose: float | None
    max_glucose: float | None
    low_count: int
    high_count: int
    critical_count: int
    amplitude: float | None
    attention_reasons: list[str] = field(default_factory=list)
    attention_note: str = ""
    extreme_times: list[str] = field(default_factory=list)
    extreme_contexts: list[str] = field(default_factory=list)
    lang: str = DEFAULT_LANG

    @property
    def is_attention(self) -> bool:
        return bool(self.attention_reasons)

    @property
    def primary_attention_reason(self) -> str:
        return self.attention_reasons[0] if self.attention_reasons else "-"

    @property
    def attention_classification(self) -> str:
        if not self.attention_reasons:
            return _translate(self.lang, "no_alert")
        return "; ".join(self.attention_reasons[:3])


def _group_events_by_day(events: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for event in events:
        key = _event_date_key(event)
        if not key:
            continue
        grouped.setdefault(key, []).append(event)
    for day_events in grouped.values():
        day_events.sort(key=_event_time_minutes)
    return grouped


def _detect_attention_for_day(summary: DailyGlucoseSummary, lang: str = DEFAULT_LANG) -> None:
    reasons: list[str] = []
    notes: list[str] = []

    if summary.anomaly_flag:
        reasons.append(_translate(lang, "reason_anomaly_day"))
        notes.append(_translate(lang, "note_flagged_automated"))
    if summary.low_count:
        reasons.append(_translate(lang, "reason_hypo"))
        notes.append(_translate(lang, "note_readings_low", n=summary.low_count))
    if summary.critical_count:
        reasons.append(_translate(lang, "reason_critical"))
        notes.append(_translate(lang, "note_readings_critical", n=summary.critical_count))
    if summary.count and summary.pct_hyper >= 50:
        reasons.append(_translate(lang, "reason_hyper_predominance"))
        notes.append(_translate(lang, "note_pct_hyper", pct=_format_number(summary.pct_hyper, "%", lang=lang)))
    if summary.count and summary.pct_in_range == 0:
        reasons.append(_translate(lang, "reason_all_out_of_range"))
        notes.append(_translate(lang, "note_no_in_range_reading"))
    if summary.amplitude is not None and summary.amplitude >= 100:
        reasons.append(_translate(lang, "reason_high_variability"))
        notes.append(_translate(lang, "note_amplitude", value=_format_number(summary.amplitude, lang=lang)))
    if summary.avg_glucose is not None and summary.avg_glucose < HYPO_LIMIT:
        reasons.append(_translate(lang, "reason_avg_too_low"))
        notes.append(_translate(lang, "note_avg_below_hypo"))
    if summary.avg_glucose is not None and summary.avg_glucose >= CRITICAL_HYPER_LIMIT:
        reasons.append(_translate(lang, "reason_avg_too_high"))
        notes.append(_translate(lang, "note_avg_above_critical"))

    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason not in deduped_reasons:
            deduped_reasons.append(reason)
    summary.attention_reasons = deduped_reasons
    summary.attention_note = "; ".join(notes[:3]) if notes else "-"
    summary.lang = lang

    extreme_events = [
        event
        for event in summary.events
        if event.get("glucose_mg_dl") is not None
        and (float(event["glucose_mg_dl"]) < HYPO_LIMIT or float(event["glucose_mg_dl"]) >= CRITICAL_HYPER_LIMIT)
    ]
    summary.extreme_times = [str(event.get("event_time") or _format_datetime(event.get("occurred_at"), lang=lang)[-5:]) for event in extreme_events]
    if lang == DEFAULT_LANG:
        contexts = [
            str(event.get("context_label_display") or event.get("context_label") or "-")
            for event in extreme_events
            if event.get("context_label_display") or event.get("context_label")
        ]
    else:
        contexts = []
        for event in extreme_events:
            raw_code = event.get("context_label")
            if raw_code:
                contexts.append(_localized_lookup(raw_code, lang, LOCALIZED_CONTEXT_LABELS))
            elif event.get("context_label_display"):
                contexts.append(str(event.get("context_label_display")))
    summary.extreme_contexts = list(dict.fromkeys(contexts))


def build_daily_glucose_summaries(context: dict[str, object], lang: str = DEFAULT_LANG) -> list[DailyGlucoseSummary]:
    events_by_day = _group_events_by_day(context["glucose_events_json"])
    indicators = {str(item.get("date")): item for item in context["daily_indicators_json"]}
    day_keys = sorted(key for key in set(events_by_day) | set(indicators) if key)
    summaries: list[DailyGlucoseSummary] = []

    for day_key in day_keys:
        events = events_by_day.get(day_key, [])
        values = [float(event["glucose_mg_dl"]) for event in events if event.get("glucose_mg_dl") is not None]
        indicator = indicators.get(day_key, {})
        count = len(values)
        low_count = len([value for value in values if value < HYPO_LIMIT])
        high_count = len([value for value in values if value > HYPER_LIMIT])
        critical_count = len([value for value in values if value >= CRITICAL_HYPER_LIMIT])
        in_range_count = max(count - low_count - high_count, 0)
        avg_glucose = indicator.get("avg_glucose")
        if avg_glucose is None and values:
            avg_glucose = sum(values) / len(values)
        min_glucose = min(values) if values else None
        max_glucose = max(values) if values else None
        summary = DailyGlucoseSummary(
            date=day_key,
            events=events,
            avg_glucose=float(avg_glucose) if avg_glucose is not None else None,
            pct_hypo=float(indicator.get("pct_hypo")) if indicator.get("pct_hypo") is not None else ((low_count / count) * 100 if count else 0),
            pct_in_range=float(indicator.get("pct_in_range")) if indicator.get("pct_in_range") is not None else ((in_range_count / count) * 100 if count else 0),
            pct_hyper=float(indicator.get("pct_hyper")) if indicator.get("pct_hyper") is not None else ((high_count / count) * 100 if count else 0),
            anomaly_flag=bool(indicator.get("anomaly_flag")),
            profile_label=_profile_label(indicator),
            count=count,
            min_glucose=min_glucose,
            max_glucose=max_glucose,
            low_count=low_count,
            high_count=high_count,
            critical_count=critical_count,
            amplitude=(max_glucose - min_glucose) if min_glucose is not None and max_glucose is not None else None,
        )
        _detect_attention_for_day(summary, lang)
        summaries.append(summary)

    return summaries


def build_attention_days(context: dict[str, object], lang: str = DEFAULT_LANG) -> list[DailyGlucoseSummary]:
    return [summary for summary in build_daily_glucose_summaries(context, lang) if summary.is_attention]


def preload_report_assets() -> None:
    _load_png_image(LOGO_IMAGE_PATH)


@dataclass(slots=True)
class PdfImage:
    name: str
    width: int
    height: int
    rgb: bytes
    alpha: bytes | None = None


def _png_scanline_filter(filter_type: int, raw: bytearray, previous: bytes, bpp: int) -> bytes:
    result = bytearray(raw)
    for index in range(len(result)):
        left = result[index - bpp] if index >= bpp else 0
        up = previous[index] if previous else 0
        up_left = previous[index - bpp] if previous and index >= bpp else 0
        if filter_type == 1:
            result[index] = (result[index] + left) & 0xFF
        elif filter_type == 2:
            result[index] = (result[index] + up) & 0xFF
        elif filter_type == 3:
            result[index] = (result[index] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            predictor = left + up - up_left
            pa = abs(predictor - left)
            pb = abs(predictor - up)
            pc = abs(predictor - up_left)
            paeth = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
            result[index] = (result[index] + paeth) & 0xFF
    return bytes(result)


def _load_png_image(path: Path, *, max_width: int = 420) -> PdfImage | None:
    cache_key = (path, max_width)
    if cache_key in _PNG_IMAGE_CACHE:
        return _PNG_IMAGE_CACHE[cache_key]
    if not path.exists():
        _PNG_IMAGE_CACHE[cache_key] = None
        return None
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        _PNG_IMAGE_CACHE[cache_key] = None
        return None
    offset = 8
    width = height = color_type = bit_depth = None
    compressed = bytearray()
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if not width or not height or bit_depth != 8 or color_type not in (2, 6):
        _PNG_IMAGE_CACHE[cache_key] = None
        return None

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows: list[bytes] = []
    previous = bytes(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = _png_scanline_filter(filter_type, bytearray(raw[cursor : cursor + stride]), previous, channels)
        cursor += stride
        rows.append(row)
        previous = row

    scale = min(1.0, max_width / width)
    target_width = max(1, int(width * scale))
    target_height = max(1, int(height * scale))
    rgb = bytearray()
    alpha = bytearray() if channels == 4 else None
    for target_y in range(target_height):
        source_y = min(height - 1, int(target_y / scale)) if scale < 1 else target_y
        row = rows[source_y]
        for target_x in range(target_width):
            source_x = min(width - 1, int(target_x / scale)) if scale < 1 else target_x
            pixel = source_x * channels
            rgb.extend(row[pixel : pixel + 3])
            if alpha is not None:
                alpha.append(row[pixel + 3])
    image = PdfImage(name="ImLogo", width=target_width, height=target_height, rgb=bytes(rgb), alpha=bytes(alpha) if alpha is not None else None)
    _PNG_IMAGE_CACHE[cache_key] = image
    return image


class PdfDocument:
    def __init__(self) -> None:
        self.pages: list[tuple[bytes, float, float]] = []
        self.images: dict[str, PdfImage] = {}

    def add_page(self, content: bytes, width: float, height: float) -> None:
        self.pages.append((content, width, height))

    def add_image(self, image: PdfImage | None) -> None:
        if image:
            self.images[image.name] = image

    def render(self) -> bytes:
        objects: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        }
        page_refs: list[str] = []
        next_object = 5
        xobject_entries: list[str] = []
        for image in self.images.values():
            mask_object = None
            if image.alpha is not None:
                mask_object = next_object
                next_object += 1
                mask_data = zlib.compress(image.alpha)
                objects[mask_object] = (
                    f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height} "
                    f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(mask_data)} >>\nstream\n"
                ).encode("ascii") + mask_data + b"\nendstream"
            image_object = next_object
            next_object += 1
            image_data = zlib.compress(image.rgb)
            smask = f" /SMask {mask_object} 0 R" if mask_object else ""
            objects[image_object] = (
                f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode{smask} /Length {len(image_data)} >>\nstream\n"
            ).encode("ascii") + image_data + b"\nendstream"
            xobject_entries.append(f"/{image.name} {image_object} 0 R")
        xobject_resource = f"/XObject << {' '.join(xobject_entries)} >> " if xobject_entries else ""
        for content, page_width, page_height in self.pages:
            content_object = next_object
            next_object += 1
            page_object = next_object
            next_object += 1
            objects[content_object] = b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream"
            objects[page_object] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width:.2f} {page_height:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> {xobject_resource}>> /Contents {content_object} 0 R >>"
            ).encode("ascii")
            page_refs.append(f"{page_object} 0 R")

        objects[2] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode("ascii")

        buffer = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {0: 0}
        for number in range(1, max(objects) + 1):
            offsets[number] = len(buffer)
            buffer.extend(f"{number} 0 obj\n".encode("ascii"))
            buffer.extend(objects[number])
            buffer.extend(b"\nendobj\n")

        xref_offset = len(buffer)
        buffer.extend(f"xref\n0 {max(objects) + 1}\n".encode("ascii"))
        buffer.extend(b"0000000000 65535 f \n")
        for number in range(1, max(objects) + 1):
            buffer.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
        buffer.extend(
            f"trailer\n<< /Size {max(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        return bytes(buffer)


class PdfPage:
    def __init__(self) -> None:
        self.commands: list[bytes] = []

    def command(self, value: str | bytes) -> None:
        self.commands.append(value if isinstance(value, bytes) else value.encode("ascii"))
        self.commands.append(b"\n")

    def set_fill(self, color: tuple[float, float, float]) -> None:
        self.command(f"{_rgb(color)} rg")

    def set_stroke(self, color: tuple[float, float, float]) -> None:
        self.command(f"{_rgb(color)} RG")

    def set_line_width(self, width: float) -> None:
        self.command(f"{width:.2f} w")

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: tuple[float, float, float] | None = None,
        stroke: tuple[float, float, float] | None = None,
    ) -> None:
        if fill:
            self.set_fill(fill)
        if stroke:
            self.set_stroke(stroke)
        operator = "B" if fill and stroke else "f" if fill else "S"
        self.command(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re {operator}")

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        color: tuple[float, float, float] = COLOR_BORDER,
        width: float = 1.0,
        dashed: bool = False,
    ) -> None:
        self.set_stroke(color)
        self.set_line_width(width)
        self.command("[4 3] 0 d" if dashed else "[] 0 d")
        self.command(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")
        if dashed:
            self.command("[] 0 d")

    def text(
        self,
        x: float,
        y: float,
        value: object,
        *,
        size: float = 10,
        bold: bool = False,
        color: tuple[float, float, float] = COLOR_TEXT,
    ) -> None:
        font = "F2" if bold else "F1"
        prefix = f"BT /{font} {size:.2f} Tf {_rgb(color)} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ".encode("ascii")
        self.commands.append(prefix + _pdf_literal(value) + b" Tj ET\n")

    def polyline(self, points: list[tuple[float, float]], *, color: tuple[float, float, float], width: float = 1.5) -> None:
        if len(points) < 2:
            return
        self.set_stroke(color)
        self.set_line_width(width)
        path = [f"{points[0][0]:.2f} {points[0][1]:.2f} m"]
        path.extend(f"{x:.2f} {y:.2f} l" for x, y in points[1:])
        self.command(" ".join(path) + " S")

    def circle(self, x: float, y: float, radius: float, *, fill: tuple[float, float, float], stroke: tuple[float, float, float]) -> None:
        control = radius * 0.55228475
        self.set_fill(fill)
        self.set_stroke(stroke)
        self.set_line_width(1.2)
        self.command(
            f"{x + radius:.2f} {y:.2f} m "
            f"{x + radius:.2f} {y + control:.2f} {x + control:.2f} {y + radius:.2f} {x:.2f} {y + radius:.2f} c "
            f"{x - control:.2f} {y + radius:.2f} {x - radius:.2f} {y + control:.2f} {x - radius:.2f} {y:.2f} c "
            f"{x - radius:.2f} {y - control:.2f} {x - control:.2f} {y - radius:.2f} {x:.2f} {y - radius:.2f} c "
            f"{x + control:.2f} {y - radius:.2f} {x + radius:.2f} {y - control:.2f} {x + radius:.2f} {y:.2f} c B"
        )

    def image(self, name: str, x: float, y: float, width: float, height: float) -> None:
        self.command(f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")

    def render(self) -> bytes:
        return b"".join(self.commands)


@dataclass(slots=True)
class ClinicalReportPdf:
    context: dict[str, object]
    document: PdfDocument
    page: PdfPage
    y: float
    page_number: int = 0
    page_width: float = PAGE_WIDTH
    page_height: float = PAGE_HEIGHT
    daily_summaries: list[DailyGlucoseSummary] = field(default_factory=list)
    lang: str = DEFAULT_LANG

    @classmethod
    def create(cls, context: dict[str, object], lang: str = DEFAULT_LANG) -> "ClinicalReportPdf":
        if lang not in SUPPORTED_LANGS:
            lang = DEFAULT_LANG
        report = cls(
            context=context,
            document=PdfDocument(),
            page=PdfPage(),
            y=PAGE_HEIGHT - MARGIN_TOP,
            page_width=PAGE_WIDTH,
            page_height=PAGE_HEIGHT,
            daily_summaries=build_daily_glucose_summaries(context, lang),
            lang=lang,
        )
        report.document.add_image(_load_png_image(LOGO_IMAGE_PATH))
        report._new_page()
        return report

    def _t(self, key: str, **kwargs: object) -> str:
        return _translate(self.lang, key, **kwargs)

    def _localized_event_field(
        self,
        event: dict[str, object],
        code_key: str,
        display_key: str,
        mapping: dict[str, dict[str, str]],
    ) -> str:
        if self.lang == DEFAULT_LANG:
            return str(event.get(display_key) or event.get(code_key) or "-")
        raw_code = event.get(code_key)
        if raw_code:
            return _localized_lookup(raw_code, self.lang, mapping)
        return str(event.get(display_key) or "-")

    def _new_page(self) -> None:
        if self.page_number:
            self._footer()
            self.document.add_page(self.page.render(), self.page_width, self.page_height)
        self.page = PdfPage()
        self.page_number += 1
        self.page_width = PAGE_WIDTH if self.page_number == 1 else LANDSCAPE_PAGE_WIDTH
        self.page_height = PAGE_HEIGHT if self.page_number == 1 else LANDSCAPE_PAGE_HEIGHT
        self.y = self.page_height - MARGIN_TOP
        if self.page_number > 1:
            self._running_header()

    def _footer(self) -> None:
        footer = self._t("footer_text")
        self.page.line(MARGIN_X, 25, self.page_width - MARGIN_X, 25, color=COLOR_BORDER, width=0.6)
        self.page.text(MARGIN_X, 14, footer, size=7.8, color=COLOR_MUTED)
        self.page.text(self.page_width - MARGIN_X - 34, 14, self._t("page_label", n=self.page_number), size=7.8, color=COLOR_MUTED)

    def _finish(self) -> bytes:
        self._footer()
        self.document.add_page(self.page.render(), self.page_width, self.page_height)
        return self.document.render()

    def _ensure(self, height: float) -> None:
        if self._needs_page(height):
            self._new_page()

    def _needs_page(self, height: float) -> bool:
        return self.y - height < MARGIN_BOTTOM + 28

    @property
    def content_width(self) -> float:
        return self.page_width - 2 * MARGIN_X

    def _space(self, amount: float) -> None:
        self.y -= amount

    def _section_title(self, title: str, *, keep_with: float = 0) -> None:
        self._ensure(32 + keep_with)
        self.page.line(MARGIN_X, self.y, self.page_width - MARGIN_X, self.y, color=COLOR_BORDER, width=0.8)
        self._space(18)
        self.page.text(MARGIN_X, self.y, title, size=14, bold=True, color=(0.06, 0.15, 0.25))
        self._space(14)

    def _running_header(self) -> None:
        patient = self.context["patient"]
        filters = self.context["filters"]
        joiner = self._t("period_joiner")
        period = f"{_format_date(filters.get('start_date'), self.lang)}{joiner}{_format_date(filters.get('end_date'), self.lang)}"
        self._myglico_logo(MARGIN_X, self.y + 3, scale=0.34)
        self.page.text(MARGIN_X + 44, self.y, self._t("report_title"), size=8.2, bold=True, color=COLOR_TEXT)
        self.page.text(MARGIN_X + 44, self.y - 11, f"{patient.display_name} | {period}", size=7.8, color=COLOR_MUTED)
        self.page.text(self.page_width - MARGIN_X - 58, self.y, self._t("page_label", n=self.page_number), size=7.8, color=COLOR_MUTED)
        self.page.line(MARGIN_X, self.y - 19, self.page_width - MARGIN_X, self.y - 19, color=COLOR_BORDER, width=0.6)
        self.y -= 36

    def _wrapped_text(self, x: float, y: float, text: str, width: float, *, size: float, bold: bool = False, color=COLOR_TEXT) -> float:
        line_height = size + 3
        current_y = y
        for line in _wrap_text(text, size, width, bold=bold):
            self.page.text(x, current_y, line, size=size, bold=bold, color=color)
            current_y -= line_height
        return current_y

    def _myglico_logo(self, x: float, y: float, *, scale: float = 1.0, wordmark: bool = True) -> None:
        if "ImLogo" in self.document.images:
            width = 96 * scale
            height = width * self.document.images["ImLogo"].height / self.document.images["ImLogo"].width
            self.page.image("ImLogo", x, y - height, width, height)
            return
        icon = 22 * scale
        book_x = x
        book_y = y - icon + 2 * scale
        self.page.rect(book_x, book_y, icon * 0.55, icon * 0.70, fill=(1, 1, 1), stroke=COLOR_BRAND_GREEN)
        self.page.line(book_x + 4 * scale, book_y + icon * 0.50, book_x + icon * 0.42, book_y + icon * 0.50, color=COLOR_BRAND_CYAN, width=1.2 * scale)
        self.page.line(book_x + 4 * scale, book_y + icon * 0.37, book_x + icon * 0.42, book_y + icon * 0.37, color=COLOR_BORDER, width=1.0 * scale)
        self.page.line(book_x + 4 * scale, book_y + icon * 0.24, book_x + icon * 0.32, book_y + icon * 0.24, color=COLOR_BORDER, width=1.0 * scale)
        meter_cx = x + icon * 0.64
        meter_cy = y - icon * 0.47
        self.page.circle(meter_cx, meter_cy, icon * 0.24, fill=(0.90, 0.97, 1.0), stroke=COLOR_BLUE)
        self.page.rect(meter_cx - icon * 0.13, meter_cy + icon * 0.05, icon * 0.26, icon * 0.10, fill=(1, 1, 1), stroke=COLOR_BRAND_CYAN)
        self.page.circle(meter_cx, meter_cy - icon * 0.10, icon * 0.065, fill=COLOR_BRAND_YELLOW, stroke=COLOR_BLUE)
        self.page.circle(x + icon * 0.88, y - icon * 0.06, icon * 0.06, fill=COLOR_BRAND_YELLOW, stroke=COLOR_BRAND_YELLOW)
        if wordmark:
            self.page.text(x + icon + 7 * scale, y - 5 * scale, "MyGlico", size=11 * scale, bold=True, color=COLOR_BLUE)

    def _header(self) -> None:
        patient = self.context["patient"]
        filters = self.context["filters"]
        summary = self.context["summary"]
        generated_at = datetime.now(REPORT_TIMEZONE).strftime("%m/%d/%Y %H:%M" if self.lang == "en-US" else "%d/%m/%Y %H:%M")

        self.page.rect(0, self.page_height - 104, self.page_width, 104, fill=(0.94, 0.98, 1.0))
        self._myglico_logo(MARGIN_X, self.page_height - 24, scale=0.82)
        title_x = MARGIN_X + 112
        self.page.text(title_x, self.page_height - 48, self._t("report_title"), size=20, bold=True, color=(0.05, 0.13, 0.22))
        self.page.text(title_x, self.page_height - 66, self._t("header_subtitle"), size=8.8, color=COLOR_MUTED)
        self.page.rect(self.page_width - MARGIN_X - 134, self.page_height - 76, 134, 42, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.text(self.page_width - MARGIN_X - 124, self.page_height - 50, self._t("generated_at_label"), size=7.6, bold=True, color=COLOR_MUTED)
        self.page.text(self.page_width - MARGIN_X - 124, self.page_height - 64, generated_at, size=10.2, bold=True, color=COLOR_TEXT)
        self.y = self.page_height - 128
        self._identification_panel(generated_at)
        self._space(16)

        joiner = self._t("period_joiner")
        period = f"{_format_date(filters.get('start_date'), self.lang)}{joiner}{_format_date(filters.get('end_date'), self.lang)}"
        intro = self._t("header_intro", period=period)
        self.y = self._wrapped_text(MARGIN_X, self.y, intro, self.content_width, size=8.8, color=COLOR_MUTED)
        self._space(10)
        self._summary_cards()
        self._space(8)

    def _identification_panel(self, generated_at: str) -> None:
        patient = self.context["patient"]
        filters = self.context["filters"]
        summary = self.context["summary"]
        indicators = self.context["daily_indicators_json"]
        height = 74
        self._ensure(height + 6)
        top = self.y
        self.page.rect(MARGIN_X, top - height, self.content_width, height, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.rect(MARGIN_X, top - height, 3, height, fill=COLOR_BLUE)
        left_x = MARGIN_X + 12
        right_x = MARGIN_X + 280
        joiner = self._t("period_joiner")
        period = f"{_format_date(filters.get('start_date'), self.lang)}{joiner}{_format_date(filters.get('end_date'), self.lang)}"
        rows = [
            (left_x, top - 17, self._t("label_patient"), patient.display_name),
            (left_x, top - 35, self._t("label_period_analyzed"), period),
            (left_x, top - 53, self._t("generated_at_label"), generated_at),
            (right_x, top - 17, self._t("label_measurements"), summary.get("glucose_measurements", "-")),
            (right_x, top - 35, self._t("label_days_observed"), summary.get("days_observed", "-")),
            (right_x, top - 53, self._t("label_period_profile"), _period_profile(summary, self.lang)),
        ]
        for x, y, label, value in rows:
            self.page.text(x, y, f"{label}:", size=7.7, bold=True, color=COLOR_MUTED)
            self._wrapped_text(x + 92, y, str(value), 162 if x == left_x else 146, size=8.4, bold=True, color=COLOR_TEXT)
        self.y -= height

    def _summary_cards(self) -> None:
        summary = self.context["summary"]
        stats = _event_stats(self.context["glucose_events_json"])
        attention_count = len([item for item in self.daily_summaries if item.is_attention])
        cards = [
            (self._t("card_avg_glucose"), f"{_format_number(summary.get('avg_glucose') or stats['avg'], lang=self.lang)} mg/dL"),
            (self._t("card_pct_hypo"), _format_number(summary.get("pct_hypo", stats["pct_hypo"]), "%", lang=self.lang)),
            (self._t("card_pct_range"), _format_number(summary.get("pct_in_range", stats["pct_in_range"]), "%", lang=self.lang)),
            (self._t("card_pct_hyper"), _format_number(summary.get("pct_hyper", stats["pct_hyper"]), "%", lang=self.lang)),
            (self._t("card_critical_risk"), str(stats["critical_count"])),
            (self._t("card_min_max"), f"{_format_number(stats['min'], lang=self.lang)} / {_format_number(stats['max'], lang=self.lang)}"),
            (self._t("card_anomaly_days"), str(summary.get("anomaly_days", "-"))),
            (self._t("card_attention_points"), str(attention_count)),
        ]
        self._ensure(96)
        gap = 7
        columns = 4
        width = (self.content_width - gap * (columns - 1)) / columns
        height = 42
        top = self.y
        for index, (label, value) in enumerate(cards):
            col = index % columns
            row = index // columns
            x = MARGIN_X + col * (width + gap)
            y = top - row * (height + 7)
            self.page.rect(x, y - height, width, height, fill=COLOR_PANEL, stroke=COLOR_BORDER)
            self.page.text(x + 7, y - 14, label, size=7.3, bold=True, color=COLOR_MUTED)
            self._wrapped_text(x + 7, y - 29, value, width - 14, size=10.5, bold=True, color=COLOR_TEXT)
        self.y -= height * 2 + 7

    def _metric_row(self, items: list[tuple[str, object, str | None] | tuple[str, object]], *, columns: int = 4, compact: bool = False) -> None:
        gap = 7
        width = (self.content_width - gap * (columns - 1)) / columns
        height = 42 if compact else 52
        self._ensure(height + 4)
        x = MARGIN_X
        top = self.y
        for item in items:
            label = item[0]
            value = item[1]
            helper = item[2] if len(item) > 2 else None
            self.page.rect(x, top - height, width, height, fill=COLOR_PANEL, stroke=COLOR_BORDER)
            self.page.text(x + 7, top - 14, label, size=7.5, bold=True, color=COLOR_MUTED)
            self._wrapped_text(x + 7, top - 29, str(value), width - 14, size=10.5 if compact else 12, bold=True, color=COLOR_TEXT)
            if helper:
                self.page.text(x + 7, top - height + 8, helper, size=7.6, color=COLOR_MUTED)
            x += width + gap
        self.y -= height

    def _summary(self) -> None:
        summary = self.context["summary"]
        events = self.context["glucose_events_json"]
        stats = _event_stats(events)
        pct_hypo = float(summary.get("pct_hypo", stats["pct_hypo"]) or 0)
        pct_range = float(summary.get("pct_in_range", stats["pct_in_range"]) or 0)
        pct_hyper = float(summary.get("pct_hyper", stats["pct_hyper"]) or 0)
        avg = float(summary.get("avg_glucose") or stats["avg"] or 0)

        self._section_title(self._t("summary_title"), keep_with=95)
        rows = [
            [
                self._t("row_avg_glucose_daily"),
                f"{_format_number(avg, lang=self.lang)} mg/dL",
                self._t("ref_operational_range"),
            ],
            [
                self._t("row_pct_hypo_daily"),
                _format_number(pct_hypo, "%", lang=self.lang),
                self._t("ref_hypo"),
            ],
            [
                self._t("row_pct_range_daily"),
                _format_number(pct_range, "%", lang=self.lang),
                self._t("ref_target"),
            ],
            [
                self._t("row_pct_hyper_daily"),
                _format_number(pct_hyper, "%", lang=self.lang),
                self._t("ref_hyper"),
            ],
            [
                self._t("row_critical_events"),
                self._t("n_readings", n=stats["critical_count"]),
                self._t("ref_critical"),
            ],
            [
                self._t("row_min_max_reading"),
                f"{_format_number(stats['min'], lang=self.lang)} / {_format_number(stats['max'], lang=self.lang)} mg/dL",
                self._t("ref_thresholds_used"),
            ],
            [
                self._t("row_anomaly_days"),
                str(summary.get("anomaly_days", "-")),
                self._t("ref_auto_flagging"),
            ],
        ]
        self._table([self._t("col_exam_indicator"), self._t("col_result"), self._t("col_reference_value")], rows, [185, 112, self.content_width - 297], font_size=7.5)
        # A interpretação de resultados foi removida do relatório final a pedido do produto.
        # Para reativar no futuro, adicionar a quarta coluna e chamar _interpretation_panel(self._clinical_notes(stats)).

    def _metric_grid(self, items: list[tuple[str, object, str | None]]) -> None:
        for index in range(0, len(items), 4):
            self._metric_row(items[index : index + 4], columns=4)
            self._space(7)

    def _clinical_notes(self, stats: dict[str, object]) -> list[str]:
        summary = self.context["summary"]
        notes: list[str] = []
        avg = float(summary.get("avg_glucose") or stats["avg"] or 0)
        pct_hypo = float(summary.get("pct_hypo") or stats["pct_hypo"] or 0)
        pct_hyper = float(summary.get("pct_hyper") or stats["pct_hyper"] or 0)
        anomaly_days = int(summary.get("anomaly_days") or 0)
        if pct_hypo >= 10:
            notes.append(self._t("notes_hypo_relevant"))
        if pct_hyper >= 65 or avg >= 185:
            notes.append(self._t("notes_hyper_predominance"))
        if int(stats["critical_count"]) > 0:
            notes.append(self._t("notes_critical_readings", n=stats["critical_count"]))
        if anomaly_days > 0:
            notes.append(self._t("notes_anomaly_days", n=anomaly_days))
        if not notes:
            notes.append(self._t("notes_no_alerts"))
        notes.append(self._t("notes_pct_follow_detail"))
        return notes

    def _threshold_legend(self) -> None:
        self._section_title(self._t("threshold_legend_title"), keep_with=78)
        columns = 2
        gap = 10
        width = (self.content_width - gap) / columns
        height = 34
        self._ensure(height * 2 + 8)
        for index, (code, range_label, color) in enumerate(THRESHOLDS):
            col = index % columns
            row = index // columns
            x = MARGIN_X + col * (width + gap)
            y = self.y - row * (height + 6)
            self.page.rect(x, y - height, width, height, fill=COLOR_PANEL, stroke=COLOR_BORDER)
            self.page.line(x + 8, y - 15, x + 30, y - 15, color=color, width=2, dashed=True)
            self.page.text(x + 38, y - 14, self._t(f"threshold_{code}"), size=9, bold=True, color=COLOR_TEXT)
            self.page.text(x + 38, y - 27, range_label, size=8.2, color=COLOR_MUTED)
        self.y -= height * 2 + 10

    def _distribution(self) -> None:
        summary = self.context["summary"]
        stats = _event_stats(self.context["glucose_events_json"])
        self._section_title(self._t("distribution_title"), keep_with=70)
        values = [
            (self._t("threshold_hypo"), summary.get("pct_hypo", stats["pct_hypo"]), COLOR_HYPO),
            (self._t("threshold_target"), summary.get("pct_in_range", stats["pct_in_range"]), COLOR_TARGET),
            (self._t("threshold_hyper"), summary.get("pct_hyper", stats["pct_hyper"]), COLOR_HYPER),
        ]
        self._ensure(70)
        bar_width = self.content_width - 128
        y = self.y
        for label, value, color in values:
            pct = max(0.0, min(100.0, float(value or 0)))
            self.page.text(MARGIN_X, y - 1, label, size=9, bold=True, color=COLOR_TEXT)
            self.page.text(MARGIN_X + 88, y - 1, _format_number(pct, "%", lang=self.lang), size=9, color=COLOR_MUTED)
            self.page.rect(MARGIN_X + 128, y - 8, bar_width, 8, fill=(0.90, 0.93, 0.96))
            self.page.rect(MARGIN_X + 128, y - 8, bar_width * pct / 100, 8, fill=color)
            y -= 18
        self.y = y - 2

    def _chart_y(self, value: float, min_value: float, max_value: float, bottom: float, height: float) -> float:
        return bottom + ((value - min_value) / max(max_value - min_value, 1)) * height

    def _line_chart(self, title: str, points: list[tuple[str, float]]) -> None:
        chart_width = self.content_width
        chart_height = 190
        self._ensure(chart_height + 84)
        self._section_title(title, keep_with=chart_height + 36)
        top = self.y
        bottom = top - chart_height
        left = MARGIN_X + 38
        right = MARGIN_X + chart_width - 10
        plot_width = right - left
        plot_height = chart_height - 38
        plot_bottom = bottom + 25
        values = [value for _, value in points]
        if not values:
            self.page.text(MARGIN_X, self.y - 18, self._t("chart_no_data"), size=9, color=COLOR_MUTED)
            self.y -= 34
            return

        min_value = max(0, min(50, min(values), HYPO_LIMIT) - 10)
        max_value = max(260, max(values), CRITICAL_HYPER_LIMIT) + 10
        y70 = self._chart_y(HYPO_LIMIT, min_value, max_value, plot_bottom, plot_height)
        y180 = self._chart_y(HYPER_LIMIT, min_value, max_value, plot_bottom, plot_height)
        y250 = self._chart_y(CRITICAL_HYPER_LIMIT, min_value, max_value, plot_bottom, plot_height)

        self.page.rect(left, plot_bottom, plot_width, max(y70 - plot_bottom, 0), fill=(0.985, 0.985, 0.985))
        self.page.rect(left, y70, plot_width, max(y180 - y70, 0), fill=(0.945, 0.975, 0.962))
        self.page.rect(left, y180, plot_width, max(y250 - y180, 0), fill=(0.968, 0.972, 0.976))
        self.page.rect(left, y250, plot_width, max(plot_bottom + plot_height - y250, 0), fill=(0.952, 0.958, 0.968))
        self.page.rect(left, plot_bottom, plot_width, plot_height, stroke=COLOR_BORDER)

        for limit, color, label in [
            (HYPO_LIMIT, COLOR_HYPO, "70"),
            (HYPER_LIMIT, COLOR_HYPER, "180"),
            (CRITICAL_HYPER_LIMIT, COLOR_CRITICAL, "250"),
        ]:
            y = self._chart_y(limit, min_value, max_value, plot_bottom, plot_height)
            self.page.line(left, y, right, y, color=color, width=1.1, dashed=True)
            self.page.text(left + 4, y + 4, f"{label} mg/dL", size=8.0, bold=True, color=COLOR_TEXT)

        coords: list[tuple[float, float]] = []
        for index, (_, value) in enumerate(points):
            x = left + (plot_width / 2 if len(points) == 1 else (index * plot_width / (len(points) - 1)))
            y = self._chart_y(value, min_value, max_value, plot_bottom, plot_height)
            coords.append((x, y))
        self.page.polyline(coords, color=(0.42, 0.50, 0.58), width=0.75)
        for (_, value), (x, y) in zip(points, coords):
            classification, color = _classify_glucose(value)
            radius = 4.2 if classification in {"hypo", "critical"} else 3.6
            self.page.circle(x, y, radius, fill=color, stroke=(1, 1, 1))
            if classification in {"hypo", "critical"}:
                self.page.text(x + 5, y + 4, _format_number(value, lang=self.lang), size=7.0, bold=True, color=COLOR_TEXT)

        step = max(1, ceil(len(points) / 7))
        for index, (label, _) in enumerate(points):
            if index in (0, len(points) - 1) or index % step == 0:
                x, _ = coords[index]
                self.page.text(x - 12, bottom + 7, label, size=7.6, color=COLOR_MUTED)
        self._legend_line(bottom - 12)
        self.y = bottom - 32

    def _legend_line(self, y: float) -> None:
        x = MARGIN_X
        for code, range_label, color in THRESHOLDS:
            label = self._t(f"threshold_{code}")
            self.page.line(x, y + 4, x + 15, y + 4, color=color, width=1.5, dashed=(code != "target"))
            self.page.text(x + 19, y, f"{label} {range_label}", size=7.2, color=COLOR_MUTED)
            x += 126

    def _hourly_extremes(self) -> None:
        self._section_title(self._t("hourly_extremes_title"), keep_with=62)
        low_by_hour = {hour: 0 for hour in range(24)}
        critical_by_hour = {hour: 0 for hour in range(24)}
        for event in self.context["glucose_events_json"]:
            value = event.get("glucose_mg_dl")
            occurred_at = _parse_datetime(event.get("occurred_at"))
            if value is None or occurred_at is None:
                continue
            glucose = float(value)
            if glucose < HYPO_LIMIT:
                low_by_hour[occurred_at.hour] += 1
            if glucose >= CRITICAL_HYPER_LIMIT:
                critical_by_hour[occurred_at.hour] += 1
        rows = []
        for hour in range(24):
            low = low_by_hour.get(hour, 0)
            critical = critical_by_hour.get(hour, 0)
            if not low and not critical:
                continue
            if low and critical:
                note = self._t("note_hypo_and_critical")
            elif low:
                note = self._t("note_hypo_only")
            else:
                note = self._t("note_critical_only")
            rows.append([f"{hour:02d}h", low, critical, note])
        if not rows:
            rows = [["-", 0, 0, self._t("no_critical_occurrences")]]
        self._table(
            [self._t("col_time"), self._t("col_lt_70"), self._t("col_gte_250"), self._t("col_observation")],
            rows,
            [82, 110, 120, self.content_width - 312],
            font_size=8.4,
        )

    def _daily_table(self) -> None:
        self._section_title(self._t("daily_table_title"), keep_with=64)
        headers = [
            self._t("col_date"), self._t("col_count"), self._t("col_avg"), self._t("col_min"), self._t("col_max"),
            self._t("col_pct_hypo"), self._t("col_pct_range"), self._t("col_pct_hyper"), self._t("col_alert"),
        ]
        rows = [
            [
                _format_date(item.date, self.lang),
                item.count,
                f"{_format_number(item.avg_glucose, lang=self.lang)}",
                _format_number(item.min_glucose, lang=self.lang),
                _format_number(item.max_glucose, lang=self.lang),
                _format_number(item.pct_hypo, "%", lang=self.lang),
                _format_number(item.pct_in_range, "%", lang=self.lang),
                _format_number(item.pct_hyper, "%", lang=self.lang),
                item.primary_attention_reason,
            ]
            for item in self.daily_summaries
        ]
        self._table(
            headers,
            rows,
            [64, 38, 62, 54, 54, 62, 68, 62, self.content_width - 462],
            font_size=7.6,
            row_flags=[item.is_attention for item in self.daily_summaries],
            flag_fill=(0.965, 0.975, 0.985),
        )
        self._attention_marker_legend()

    def _attention_marker_legend(self) -> None:
        legend_height = 24
        self._ensure(legend_height + 10)
        self._space(4)

        top = self.y
        self.page.rect(
            MARGIN_X,
            top - legend_height,
            self.content_width,
            legend_height,
            fill=(1, 1, 1),
            stroke=COLOR_BORDER,
        )

        # Mesmo marcador lateral usado nas linhas da tabela com ponto de atenção.
        self.page.rect(MARGIN_X + 8, top - 18, 2.2, 12, fill=COLOR_HYPER)

        self.page.text(
            MARGIN_X + 18,
            top - 14,
            self._t("attention_marker_label"),
            size=7.8,
            bold=True,
            color=COLOR_TEXT,
        )
        self.page.text(
            MARGIN_X + 280,
            top - 14,
            self._t("attention_marker_desc"),
            size=7.4,
            color=COLOR_MUTED,
        )

        self.y -= legend_height + 8

    def _attention_days_table(self) -> None:
        self._section_title(self._t("attention_days_title"), keep_with=74)
        attention_days = [item for item in self.daily_summaries if item.is_attention]
        if not attention_days:
            self._ensure(26)
            self.page.rect(MARGIN_X, self.y - 24, self.content_width, 24, fill=COLOR_PANEL, stroke=COLOR_BORDER)
            self.page.text(MARGIN_X + 8, self.y - 15, self._t("attention_days_empty"), size=8.2, color=COLOR_MUTED)
            self.y -= 30
            return

        rows = [
            [
                _format_date(item.date, self.lang),
                item.attention_classification,
                item.attention_note,
                _format_number(item.avg_glucose, lang=self.lang),
                f"{_format_number(item.min_glucose, lang=self.lang)} / {_format_number(item.max_glucose, lang=self.lang)}",
                item.count,
                f"{_format_number(item.pct_hypo, '%', lang=self.lang)} | {_format_number(item.pct_in_range, '%', lang=self.lang)} | {_format_number(item.pct_hyper, '%', lang=self.lang)}",
                ", ".join(item.extreme_times) or "-",
                ", ".join(item.extreme_contexts[:2]) or "-",
            ]
            for item in attention_days
        ]
        self._table(
            [
                self._t("col_date"), self._t("col_alert_h"), self._t("col_reason"), self._t("col_avg"),
                self._t("col_min_max"), self._t("col_count"), self._t("col_hfhiper"), self._t("col_extremes"), self._t("col_context"),
            ],
            rows,
            [56, 130, 185, 48, 68, 32, 88, 62, self.content_width - 669],
            font_size=6.9,
            row_flags=[True for _ in rows],
        )

    def _readings_table(self) -> None:
        events = self.context["glucose_events_json"]
        self._section_title(self._t("readings_table_title"), keep_with=64)
        rows = []
        for event in events:
            rows.append(
                [
                    _format_datetime(event.get("occurred_at"), self.lang),
                    self._localized_event_field(event, "event_type", "event_type_label", LOCALIZED_EVENT_TYPE_LABELS),
                    self._localized_event_field(event, "event_subtype", "event_subtype_label", LOCALIZED_EVENT_SUBTYPE_LABELS),
                    f"{_format_number(event.get('glucose_mg_dl'), lang=self.lang)} mg/dL",
                    self._localized_event_field(event, "context_label", "context_label_display", LOCALIZED_CONTEXT_LABELS),
                ]
            )
        self._table(
            [self._t("col_when"), self._t("col_type"), self._t("col_subtype"), self._t("col_value"), self._t("col_context")],
            rows,
            [106, 96, 136, 76, self.content_width - 414],
            font_size=7.3,
        )

    def _daily_point(self, event: dict[str, object], left: float, bottom: float, width: float, height: float, min_value: float, max_value: float) -> tuple[float, float]:
        x = left + (_event_time_minutes(event) / (24 * 60)) * width
        glucose = float(event.get("glucose_mg_dl") or 0)
        y = self._chart_y(glucose, min_value, max_value, bottom, height)
        return x, y

    def _draw_daily_glucose_chart(self, summary: DailyGlucoseSummary, x: float, y: float, width: float, height: float) -> None:
        values = [float(event["glucose_mg_dl"]) for event in summary.events if event.get("glucose_mg_dl") is not None]
        min_value = max(0, min([40, HYPO_LIMIT] + values) - 10)
        max_value = max([300, CRITICAL_HYPER_LIMIT] + values) + 10
        y70 = self._chart_y(HYPO_LIMIT, min_value, max_value, y, height)
        y180 = self._chart_y(HYPER_LIMIT, min_value, max_value, y, height)
        y250 = self._chart_y(CRITICAL_HYPER_LIMIT, min_value, max_value, y, height)

        self.page.rect(x, y, width, max(y70 - y, 0), fill=(0.995, 0.925, 0.935))
        self.page.rect(x, y70, width, max(y180 - y70, 0), fill=(0.925, 0.985, 0.955))
        self.page.rect(x, y180, width, max(y250 - y180, 0), fill=(1.0, 0.965, 0.885))
        self.page.rect(x, y250, width, max(y + height - y250, 0), fill=(0.955, 0.93, 1.0))
        self.page.rect(x, y, width, height, stroke=COLOR_BORDER)

        for hour in [0, 6, 12, 18, 24]:
            tick_x = x + (hour / 24) * width
            self.page.line(tick_x, y, tick_x, y + height, color=(0.86, 0.90, 0.94), width=0.35)
            self.page.text(tick_x - 5, y - 10, f"{hour:02d}h", size=6.4, color=COLOR_MUTED)
        for limit, color, label in [(HYPO_LIMIT, COLOR_HYPO, "70"), (HYPER_LIMIT, COLOR_HYPER, "180"), (CRITICAL_HYPER_LIMIT, COLOR_CRITICAL, "250")]:
            line_y = self._chart_y(limit, min_value, max_value, y, height)
            self.page.line(x, line_y, x + width, line_y, color=color, width=0.65, dashed=True)
            self.page.text(x + width + 4, line_y - 2, label, size=6.2, color=color, bold=True)

        points = [
            self._daily_point(event, x, y, width, height, min_value, max_value)
            for event in summary.events
            if event.get("glucose_mg_dl") is not None
        ]
        if len(points) > 1:
            self.page.polyline(points, color=(0.42, 0.50, 0.58), width=0.55)
        for event, (point_x, point_y) in zip([event for event in summary.events if event.get("glucose_mg_dl") is not None], points):
            classification, color = _classify_glucose(event.get("glucose_mg_dl"))
            radius = 3.4 if classification in {"hypo", "critical"} else 2.6
            self.page.circle(point_x, point_y, radius, fill=color, stroke=(1, 1, 1))
            if classification in {"hypo", "critical"}:
                self.page.text(point_x + 4, point_y + 3, _format_number(event.get("glucose_mg_dl"), lang=self.lang), size=6.2, bold=True, color=COLOR_TEXT)

    def _draw_day_detail_block(self, summary: DailyGlucoseSummary) -> None:
        block_height = 218
        self._ensure(block_height + 10)
        top = self.y
        self.page.rect(MARGIN_X, top - block_height, self.content_width, block_height, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.rect(MARGIN_X, top - block_height, 3, block_height, fill=COLOR_HYPER if summary.is_attention else COLOR_BLUE)
        title = f"{_format_date(summary.date, self.lang)} | {_weekday_label(summary.date, self.lang)}"
        self.page.text(MARGIN_X + 10, top - 15, title, size=10, bold=True, color=COLOR_TEXT)
        badge = self._t("badge_attention") if summary.is_attention else self._t("badge_no_alert")
        self.page.text(self.page_width - MARGIN_X - 116, top - 15, badge, size=7.5, bold=True, color=COLOR_HYPER if summary.is_attention else COLOR_MUTED)

        metrics = [
            (self._t("metric_readings"), summary.count),
            (self._t("metric_avg"), f"{_format_number(summary.avg_glucose, lang=self.lang)} mg/dL"),
            (self._t("metric_min_max"), f"{_format_number(summary.min_glucose, lang=self.lang)} / {_format_number(summary.max_glucose, lang=self.lang)}"),
            (self._t("metric_pct_hfhiper"), f"{_format_number(summary.pct_hypo, '%', lang=self.lang)} | {_format_number(summary.pct_in_range, '%', lang=self.lang)} | {_format_number(summary.pct_hyper, '%', lang=self.lang)}"),
        ]
        metric_x = MARGIN_X + 10
        for index, (label, value) in enumerate(metrics):
            x = metric_x + index * 126
            self.page.text(x, top - 32, label, size=6.5, bold=True, color=COLOR_MUTED)
            self.page.text(x, top - 44, str(value), size=7.7, bold=True, color=COLOR_TEXT)

        chart_x = MARGIN_X + 16
        chart_y = top - 145
        chart_width = min(500, self.content_width - 238)
        self._draw_daily_glucose_chart(summary, chart_x, chart_y, chart_width, 78)
        self.page.text(chart_x, chart_y - 23, self._t("day_chart_caption"), size=6.4, color=COLOR_MUTED)

        table_x = chart_x + chart_width + 28
        self.page.text(table_x, top - 63, self._t("day_readings_title"), size=7.5, bold=True, color=COLOR_TEXT)
        header_y = top - 78
        headers = [
            (self._t("col_hour"), 0), (self._t("col_value_short"), 34),
            (self._t("col_context_short"), 78), (self._t("col_class"), 154),
        ]
        for header, offset in headers:
            self.page.text(table_x + offset, header_y, header, size=6.2, bold=True, color=COLOR_MUTED)
        row_y = header_y - 12
        for event in summary.events[:7]:
            classification, color = _classify_glucose(event.get("glucose_mg_dl"))
            context = self._localized_event_field(event, "context_label", "context_label_display", LOCALIZED_CONTEXT_LABELS)
            self.page.text(table_x, row_y, str(event.get("event_time") or "-"), size=6.3, color=COLOR_TEXT)
            self.page.text(table_x + 34, row_y, _format_number(event.get("glucose_mg_dl"), lang=self.lang), size=6.3, bold=True, color=color)
            self.page.text(table_x + 78, row_y, _wrap_text(context, 6.3, 72)[0], size=6.3, color=COLOR_TEXT)
            self.page.text(table_x + 154, row_y, self._t(f"classify_{classification}") if classification != "-" else "-", size=6.3, color=color)
            row_y -= 11
        if len(summary.events) > 7:
            self.page.text(table_x, row_y, self._t("more_readings", n=len(summary.events) - 7), size=6.2, color=COLOR_MUTED)

        if summary.is_attention:
            reason = _wrap_text(self._t("reason_prefix", note=summary.attention_note), 7.1, self.content_width - 24)
            note_y = top - 198
            for line in reason[:2]:
                self.page.text(MARGIN_X + 10, note_y, line, size=7.1, color=COLOR_HYPER)
                note_y -= 10
        self.y -= block_height + 10

    def _detailed_period_analysis(self) -> None:
        self._section_title(self._t("detailed_analysis_title"), keep_with=260)
        self.y = self._wrapped_text(
            MARGIN_X,
            self.y,
            self._t("detailed_analysis_intro"),
            self.content_width,
            size=8.2,
            color=COLOR_MUTED,
        )
        self._space(10)
        for index in range(0, len(self.daily_summaries), 7):
            week_days = self.daily_summaries[index : index + 7]
            start = _format_date(week_days[0].date, self.lang)
            end = _format_date(week_days[-1].date, self.lang)
            self._ensure(42)
            self.page.text(MARGIN_X, self.y, self._t("block_label", n=index // 7 + 1, start=start, end=end), size=11, bold=True, color=COLOR_BLUE)
            self._space(16)
            for summary in week_days:
                self._draw_day_detail_block(summary)

    def _table(
        self,
        headers: list[str],
        rows: list[list[object]],
        widths: list[float],
        *,
        font_size: float = 7.8,
        row_flags: list[bool] | None = None,
        flag_fill: tuple[float, float, float] = (1.0, 0.975, 0.93),
    ) -> None:
        header_font_size = max(7.5, font_size + 0.2)
        header_height = max(18, header_font_size + 10.5)
        line_height = font_size + 2.4
        x_positions = [MARGIN_X]
        for width in widths[:-1]:
            x_positions.append(x_positions[-1] + width)

        def draw_header() -> None:
            self._ensure(header_height + 18)
            self.page.rect(MARGIN_X, self.y - header_height, sum(widths), header_height, fill=(0.95, 0.97, 0.99), stroke=COLOR_BORDER)
            for x, header in zip(x_positions, headers):
                self.page.text(x + 4, self.y - 12, header, size=header_font_size, bold=True, color=COLOR_MUTED)
            self.y -= header_height

        draw_header()
        for row_index, row in enumerate(rows):
            wrapped_cells = [
                _wrap_text(str(value), font_size, max(width - 8, 24))
                for width, value in zip(widths, row)
            ]
            row_height = max(17, 8 + max(len(lines) for lines in wrapped_cells) * line_height)
            if self._needs_page(row_height):
                self._new_page()
                draw_header()
            is_flagged = bool(row_flags[row_index]) if row_flags and row_index < len(row_flags) else False
            if is_flagged:
                self.page.rect(MARGIN_X, self.y - row_height, sum(widths), row_height, fill=flag_fill)
                self.page.rect(MARGIN_X, self.y - row_height, 2.2, row_height, fill=COLOR_HYPER)
            elif row_index % 2 == 1:
                self.page.rect(MARGIN_X, self.y - row_height, sum(widths), row_height, fill=(0.99, 0.995, 1.0))
            self.page.line(MARGIN_X, self.y - row_height, MARGIN_X + sum(widths), self.y - row_height, color=COLOR_BORDER, width=0.4)
            for x, lines in zip(x_positions, wrapped_cells):
                text_y = self.y - 11
                for line in lines:
                    self.page.text(x + 4, text_y, line, size=font_size, color=COLOR_TEXT)
                    text_y -= line_height
            self.y -= row_height
        self._space(4)

    def render(self) -> bytes:
        self._header()
        self._summary()
        self._new_page()
        self._distribution()
        self._threshold_legend()
        daily_points = [
            (_format_date(item.get("date"), self.lang)[:5], float(item.get("avg_glucose")))
            for item in self.context["daily_indicators_json"]
            if item.get("avg_glucose") is not None
        ]
        self._line_chart(self._t("chart_daily_avg_title"), daily_points)
        self._hourly_extremes()
        self._attention_days_table()
        self._daily_table()
        self._readings_table()
        self._detailed_period_analysis()
        return self._finish()


def build_patient_report_pdf(context: dict[str, object], lang: str = DEFAULT_LANG) -> bytes:
    return ClinicalReportPdf.create(context, lang=lang).render()


def patient_report_filename(context: dict[str, object], lang: str = DEFAULT_LANG) -> str:
    patient = context["patient"]
    filters = context["filters"]
    patient_name = _safe_filename(patient.display_name)
    strings = STRINGS.get(lang) or STRINGS[DEFAULT_LANG]
    start = filters.get("start_date") or strings.get("filename_start_fallback", "inicio")
    end = filters.get("end_date") or strings.get("filename_end_fallback", "fim")
    prefix = strings.get("filename_prefix", "relatorio-glicemico")
    return f"{prefix}-{patient_name}-{start}-{end}.pdf"
