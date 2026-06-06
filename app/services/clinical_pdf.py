from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
import re
import textwrap


PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
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
COLOR_HYPO = (0.79, 0.23, 0.31)
COLOR_TARGET = (0.09, 0.53, 0.35)
COLOR_HYPER = (0.78, 0.47, 0.09)
COLOR_CRITICAL = (0.46, 0.32, 0.72)

THRESHOLDS = [
    ("Hipoglicemia", "< 70 mg/dL", COLOR_HYPO),
    ("Faixa alvo", "70 a 180 mg/dL", COLOR_TARGET),
    ("Hiperglicemia", "> 180 mg/dL", COLOR_HYPER),
    ("Risco elevado", "> 250 mg/dL", COLOR_CRITICAL),
]


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


def _format_number(value: object, suffix: str = "") -> str:
    try:
        if value is None:
            return "-"
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    formatted = f"{number:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}{suffix}"


def _format_date(value: object) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        date_value = value.date()
    else:
        date_value = datetime.fromisoformat(str(value)).date()
    return date_value.strftime("%d/%m/%Y")


def _format_datetime(value: object) -> str:
    if not value:
        return "-"
    date_value = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return date_value.strftime("%d/%m/%Y %H:%M")


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
    try:
        glucose = float(value)
    except (TypeError, ValueError):
        return "-", COLOR_MUTED
    if glucose < HYPO_LIMIT:
        return "Hipoglicemia", COLOR_HYPO
    if glucose > CRITICAL_HYPER_LIMIT:
        return "Risco elevado", COLOR_CRITICAL
    if glucose > HYPER_LIMIT:
        return "Hiperglicemia", COLOR_HYPER
    return "Em faixa", COLOR_TARGET


def _event_stats(events: list[dict[str, object]]) -> dict[str, object]:
    values = [float(event["glucose_mg_dl"]) for event in events if event.get("glucose_mg_dl") is not None]
    total = len(values)
    low = len([value for value in values if value < HYPO_LIMIT])
    high = len([value for value in values if value > HYPER_LIMIT])
    critical = len([value for value in values if value > CRITICAL_HYPER_LIMIT])
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


def _period_profile(summary: dict[str, object]) -> str:
    avg = float(summary.get("avg_glucose") or 0)
    pct_hypo = float(summary.get("pct_hypo") or 0)
    pct_hyper = float(summary.get("pct_hyper") or 0)
    if pct_hyper >= 65 or avg >= 185:
        return "Perfil hiperglicêmico"
    if pct_hypo >= 10:
        return "Perfil hipoglicêmico"
    return "Perfil em faixa"


class PdfDocument:
    def __init__(self) -> None:
        self.pages: list[bytes] = []

    def add_page(self, content: bytes) -> None:
        self.pages.append(content)

    def render(self) -> bytes:
        objects: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        }
        page_refs: list[str] = []
        next_object = 5
        for content in self.pages:
            content_object = next_object
            next_object += 1
            page_object = next_object
            next_object += 1
            objects[content_object] = b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream"
            objects[page_object] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_object} 0 R >>"
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

    def render(self) -> bytes:
        return b"".join(self.commands)


@dataclass(slots=True)
class ClinicalReportPdf:
    context: dict[str, object]
    document: PdfDocument
    page: PdfPage
    y: float
    page_number: int = 0

    @classmethod
    def create(cls, context: dict[str, object]) -> "ClinicalReportPdf":
        report = cls(context=context, document=PdfDocument(), page=PdfPage(), y=PAGE_HEIGHT - MARGIN_TOP)
        report._new_page()
        return report

    def _new_page(self) -> None:
        if self.page_number:
            self._footer()
            self.document.add_page(self.page.render())
        self.page = PdfPage()
        self.page_number += 1
        self.y = PAGE_HEIGHT - MARGIN_TOP
        if self.page_number > 1:
            self._running_header()

    def _footer(self) -> None:
        footer = "MyGlico - relatório gerado automaticamente para apoio à revisão clínica. Não substitui avaliação médica."
        self.page.line(MARGIN_X, 25, PAGE_WIDTH - MARGIN_X, 25, color=COLOR_BORDER, width=0.6)
        self.page.text(MARGIN_X, 14, footer, size=7.8, color=COLOR_MUTED)
        self.page.text(PAGE_WIDTH - MARGIN_X - 34, 14, f"Página {self.page_number}", size=7.8, color=COLOR_MUTED)

    def _finish(self) -> bytes:
        self._footer()
        self.document.add_page(self.page.render())
        return self.document.render()

    def _ensure(self, height: float) -> None:
        if self._needs_page(height):
            self._new_page()

    def _needs_page(self, height: float) -> bool:
        return self.y - height < MARGIN_BOTTOM + 28

    def _space(self, amount: float) -> None:
        self.y -= amount

    def _section_title(self, title: str) -> None:
        self._ensure(32)
        self.page.line(MARGIN_X, self.y, PAGE_WIDTH - MARGIN_X, self.y, color=COLOR_BORDER, width=0.8)
        self._space(18)
        self.page.text(MARGIN_X, self.y, title, size=14, bold=True, color=(0.06, 0.15, 0.25))
        self._space(14)

    def _running_header(self) -> None:
        patient = self.context["patient"]
        filters = self.context["filters"]
        period = f"{_format_date(filters.get('start_date'))} a {_format_date(filters.get('end_date'))}"
        self.page.text(MARGIN_X, self.y, "MyGlico", size=10, bold=True, color=COLOR_BLUE)
        self.page.text(MARGIN_X + 64, self.y, "Relatório clínico glicêmico", size=8.2, bold=True, color=COLOR_TEXT)
        self.page.text(MARGIN_X + 64, self.y - 11, f"{patient.display_name} | {period}", size=7.8, color=COLOR_MUTED)
        self.page.text(PAGE_WIDTH - MARGIN_X - 58, self.y, f"Página {self.page_number}", size=7.8, color=COLOR_MUTED)
        self.page.line(MARGIN_X, self.y - 19, PAGE_WIDTH - MARGIN_X, self.y - 19, color=COLOR_BORDER, width=0.6)
        self.y -= 36

    def _wrapped_text(self, x: float, y: float, text: str, width: float, *, size: float, bold: bool = False, color=COLOR_TEXT) -> float:
        line_height = size + 3
        current_y = y
        for line in _wrap_text(text, size, width, bold=bold):
            self.page.text(x, current_y, line, size=size, bold=bold, color=color)
            current_y -= line_height
        return current_y

    def _header(self) -> None:
        patient = self.context["patient"]
        filters = self.context["filters"]
        summary = self.context["summary"]
        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

        self.page.rect(0, PAGE_HEIGHT - 104, PAGE_WIDTH, 104, fill=(0.94, 0.98, 1.0))
        self.page.text(MARGIN_X, PAGE_HEIGHT - 36, "MyGlico", size=11, bold=True, color=COLOR_BLUE)
        self.page.text(MARGIN_X, PAGE_HEIGHT - 64, "Relatório clínico glicêmico", size=24, bold=True, color=(0.05, 0.13, 0.22))
        self.page.text(MARGIN_X, PAGE_HEIGHT - 82, "Acompanhamento glicêmico com base no detalhamento do paciente", size=9.2, color=COLOR_MUTED)
        self.page.rect(PAGE_WIDTH - MARGIN_X - 134, PAGE_HEIGHT - 76, 134, 42, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.text(PAGE_WIDTH - MARGIN_X - 124, PAGE_HEIGHT - 50, "Data da geração", size=7.6, bold=True, color=COLOR_MUTED)
        self.page.text(PAGE_WIDTH - MARGIN_X - 124, PAGE_HEIGHT - 64, generated_at, size=10.2, bold=True, color=COLOR_TEXT)
        self.y = PAGE_HEIGHT - 128
        self._identification_panel(generated_at)
        self._space(8)

        period = f"{_format_date(filters.get('start_date'))} a {_format_date(filters.get('end_date'))}"
        intro = (
            f"Este laudo consolida o período {period}, com {summary.get('glucose_measurements', '-')} medições "
            "e os mesmos indicadores exibidos no detalhamento do paciente."
        )
        self.y = self._wrapped_text(MARGIN_X, self.y, intro, PAGE_WIDTH - 2 * MARGIN_X, size=8.8, color=COLOR_MUTED)
        self._space(6)

    def _identification_panel(self, generated_at: str) -> None:
        patient = self.context["patient"]
        filters = self.context["filters"]
        summary = self.context["summary"]
        indicators = self.context["daily_indicators_json"]
        height = 92
        self._ensure(height + 6)
        top = self.y
        self.page.rect(MARGIN_X, top - height, PAGE_WIDTH - 2 * MARGIN_X, height, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.rect(MARGIN_X, top - height, 3, height, fill=COLOR_BLUE)
        left_x = MARGIN_X + 12
        right_x = MARGIN_X + 280
        rows = [
            (left_x, top - 17, "Paciente", patient.display_name),
            (left_x, top - 35, "Fonte de dados", patient.source_file or "-"),
            (left_x, top - 53, "Período analisado", f"{_format_date(filters.get('start_date'))} a {_format_date(filters.get('end_date'))}"),
            (left_x, top - 71, "Data da geração", generated_at),
            (right_x, top - 17, "Medições", summary.get("glucose_measurements", "-")),
            (right_x, top - 35, "Dias observados", summary.get("days_observed", "-")),
            (right_x, top - 53, "Perfil do período", _period_profile(summary)),
            (right_x, top - 71, "Perfil predominante", _dominant_profile(indicators)),
        ]
        for x, y, label, value in rows:
            self.page.text(x, y, f"{label}:", size=7.7, bold=True, color=COLOR_MUTED)
            self._wrapped_text(x + 92, y, str(value), 162 if x == left_x else 146, size=8.4, bold=True, color=COLOR_TEXT)
        self.y -= height

    def _metric_row(self, items: list[tuple[str, object, str | None] | tuple[str, object]], *, columns: int = 4, compact: bool = False) -> None:
        gap = 7
        width = (PAGE_WIDTH - (2 * MARGIN_X) - gap * (columns - 1)) / columns
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

        self._section_title("Resultados do acompanhamento glicêmico")
        rows = [
            [
                "Média glicêmica diária",
                f"{_format_number(avg)} mg/dL",
                "Faixa operacional do painel: 70 a 180 mg/dL",
                "Acima da faixa operacional"
                if avg > HYPER_LIMIT
                else "Média em faixa; avaliar distribuição diária"
                if pct_hyper >= 65
                else "Dentro da faixa operacional",
            ],
            [
                "% médio diário em hipoglicemia",
                _format_number(pct_hypo, "%"),
                "Hipoglicemia: < 70 mg/dL",
                "Ocorrência relevante" if pct_hypo >= 10 else "Baixa ocorrência no recorte",
            ],
            [
                "% médio diário em faixa alvo",
                _format_number(pct_range, "%"),
                "Faixa alvo: 70 a 180 mg/dL",
                "Baixa permanência em faixa" if pct_range < 50 else "Permanência adequada no recorte",
            ],
            [
                "% médio diário em hiperglicemia",
                _format_number(pct_hyper, "%"),
                "Hiperglicemia: > 180 mg/dL",
                "Predomínio hiperglicêmico" if pct_hyper >= 65 else "Monitorar tendência",
            ],
            [
                "Eventos de risco elevado",
                f"{stats['critical_count']} leitura(s)",
                "Risco elevado: > 250 mg/dL",
                "Requer revisão clínica do contexto" if int(stats["critical_count"]) else "Sem eventos no recorte",
            ],
            [
                "Menor / maior leitura",
                f"{_format_number(stats['min'])} / {_format_number(stats['max'])} mg/dL",
                "Limiares usados: 70, 180 e 250 mg/dL",
                "Oscilação importante" if (stats["min"] is not None and stats["max"] is not None and float(stats["max"]) - float(stats["min"]) >= 150) else "Variação moderada",
            ],
            [
                "Dias atípicos",
                str(summary.get("anomaly_days", "-")),
                "Sinalização automática do detalhamento",
                "Há dia(s) sinalizado(s)" if int(summary.get("anomaly_days") or 0) else "Sem sinalização",
            ],
        ]
        self._table(["Exame / indicador", "Resultado", "Valor de referência", "Interpretação"], rows, [145, 82, 158, 138], font_size=7.5)
        self._space(8)
        self._interpretation_panel(self._clinical_notes(stats))

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
            notes.append("Percentual relevante de hipoglicemia; revisar horários, alimentação e conduta em contexto clínico.")
        if pct_hyper >= 65 or avg >= 185:
            notes.append("Predomínio hiperglicêmico no período, conforme critérios de triagem do painel.")
        if int(stats["critical_count"]) > 0:
            notes.append(f"{stats['critical_count']} leitura(s) atingiram faixa de risco elevado (> 250 mg/dL).")
        if anomaly_days > 0:
            notes.append(f"{anomaly_days} dia(s) foram sinalizados como atípicos pela análise automatizada.")
        if not notes:
            notes.append("Sem alertas automáticos relevantes no recorte, considerando os limiares configurados.")
        notes.append("Percentuais do resumo seguem o detalhamento do paciente e representam médias dos indicadores diários no período.")
        return notes

    def _interpretation_panel(self, notes: list[str]) -> None:
        line_height = 11.5
        wrapped_notes = []
        for note in notes:
            wrapped_notes.append(_wrap_text(f"- {note}", 8.2, PAGE_WIDTH - 2 * MARGIN_X - 28))
        height = 24 + sum(max(1, len(lines)) * line_height for lines in wrapped_notes)
        self._ensure(height + 6)
        self.page.rect(MARGIN_X, self.y - height, PAGE_WIDTH - 2 * MARGIN_X, height, fill=(0.96, 0.98, 1.0), stroke=COLOR_BORDER)
        self.page.rect(MARGIN_X, self.y - height, 3, height, fill=COLOR_BLUE)
        self.page.text(MARGIN_X + 12, self.y - 14, "Conclusão interpretativa automatizada", size=8.5, bold=True, color=COLOR_TEXT)
        note_y = self.y - 29
        for lines in wrapped_notes:
            for line in lines:
                self.page.text(MARGIN_X + 12, note_y, line, size=8.2, color=COLOR_TEXT)
                note_y -= line_height
        self.y -= height

    def _threshold_legend(self) -> None:
        self._section_title("Legenda dos limiares glicêmicos")
        columns = 2
        gap = 10
        width = (PAGE_WIDTH - 2 * MARGIN_X - gap) / columns
        height = 34
        self._ensure(height * 2 + 8)
        for index, (label, range_label, color) in enumerate(THRESHOLDS):
            col = index % columns
            row = index // columns
            x = MARGIN_X + col * (width + gap)
            y = self.y - row * (height + 6)
            self.page.rect(x, y - height, width, height, fill=COLOR_PANEL, stroke=COLOR_BORDER)
            self.page.line(x + 8, y - 15, x + 30, y - 15, color=color, width=2, dashed=True)
            self.page.text(x + 38, y - 14, label, size=9, bold=True, color=COLOR_TEXT)
            self.page.text(x + 38, y - 27, range_label, size=8.2, color=COLOR_MUTED)
        self.y -= height * 2 + 10

    def _distribution(self) -> None:
        summary = self.context["summary"]
        stats = _event_stats(self.context["glucose_events_json"])
        self._section_title("Distribuição glicêmica do período")
        values = [
            ("Hipoglicemia", summary.get("pct_hypo", stats["pct_hypo"]), COLOR_HYPO),
            ("Faixa alvo", summary.get("pct_in_range", stats["pct_in_range"]), COLOR_TARGET),
            ("Hiperglicemia", summary.get("pct_hyper", stats["pct_hyper"]), COLOR_HYPER),
        ]
        self._ensure(70)
        bar_width = PAGE_WIDTH - 2 * MARGIN_X - 128
        y = self.y
        for label, value, color in values:
            pct = max(0.0, min(100.0, float(value or 0)))
            self.page.text(MARGIN_X, y - 1, label, size=9, bold=True, color=COLOR_TEXT)
            self.page.text(MARGIN_X + 88, y - 1, _format_number(pct, "%"), size=9, color=COLOR_MUTED)
            self.page.rect(MARGIN_X + 128, y - 8, bar_width, 8, fill=(0.90, 0.93, 0.96))
            self.page.rect(MARGIN_X + 128, y - 8, bar_width * pct / 100, 8, fill=color)
            y -= 18
        self.y = y - 2

    def _chart_y(self, value: float, min_value: float, max_value: float, bottom: float, height: float) -> float:
        return bottom + ((value - min_value) / max(max_value - min_value, 1)) * height

    def _line_chart(self, title: str, points: list[tuple[str, float]]) -> None:
        chart_width = PAGE_WIDTH - 2 * MARGIN_X
        chart_height = 190
        self._ensure(chart_height + 84)
        self._section_title(title)
        top = self.y
        bottom = top - chart_height
        left = MARGIN_X + 38
        right = MARGIN_X + chart_width - 10
        plot_width = right - left
        plot_height = chart_height - 38
        plot_bottom = bottom + 25
        values = [value for _, value in points]
        if not values:
            self.page.text(MARGIN_X, self.y - 18, "Sem dados suficientes para o gráfico.", size=9, color=COLOR_MUTED)
            self.y -= 34
            return

        min_value = max(0, min(50, min(values), HYPO_LIMIT) - 10)
        max_value = max(260, max(values), CRITICAL_HYPER_LIMIT) + 10
        y70 = self._chart_y(HYPO_LIMIT, min_value, max_value, plot_bottom, plot_height)
        y180 = self._chart_y(HYPER_LIMIT, min_value, max_value, plot_bottom, plot_height)
        y250 = self._chart_y(CRITICAL_HYPER_LIMIT, min_value, max_value, plot_bottom, plot_height)

        self.page.rect(left, plot_bottom, plot_width, max(y70 - plot_bottom, 0), fill=(0.99, 0.92, 0.93))
        self.page.rect(left, y70, plot_width, max(y180 - y70, 0), fill=(0.92, 0.98, 0.95))
        self.page.rect(left, y180, plot_width, max(y250 - y180, 0), fill=(1.0, 0.96, 0.88))
        self.page.rect(left, y250, plot_width, max(plot_bottom + plot_height - y250, 0), fill=(0.95, 0.92, 1.0))
        self.page.rect(left, plot_bottom, plot_width, plot_height, stroke=COLOR_BORDER)

        for limit, color, label in [
            (HYPO_LIMIT, COLOR_HYPO, "70"),
            (HYPER_LIMIT, COLOR_HYPER, "180"),
            (CRITICAL_HYPER_LIMIT, COLOR_CRITICAL, "250"),
        ]:
            y = self._chart_y(limit, min_value, max_value, plot_bottom, plot_height)
            self.page.line(left, y, right, y, color=color, width=1.1, dashed=True)
            self.page.text(left + 4, y + 4, f"{label} mg/dL", size=7.3, bold=True, color=COLOR_TEXT)

        coords: list[tuple[float, float]] = []
        for index, (_, value) in enumerate(points):
            x = left + (plot_width / 2 if len(points) == 1 else (index * plot_width / (len(points) - 1)))
            y = self._chart_y(value, min_value, max_value, plot_bottom, plot_height)
            coords.append((x, y))
        self.page.polyline(coords, color=COLOR_BLUE, width=2)
        for x, y in coords:
            self.page.circle(x, y, 3, fill=(1, 1, 1), stroke=COLOR_BLUE)

        step = max(1, ceil(len(points) / 7))
        for index, (label, _) in enumerate(points):
            if index in (0, len(points) - 1) or index % step == 0:
                x, _ = coords[index]
                self.page.text(x - 12, bottom + 7, label, size=7, color=COLOR_MUTED)
        self._legend_line(bottom - 12)
        self.y = bottom - 32

    def _legend_line(self, y: float) -> None:
        x = MARGIN_X
        for label, range_label, color in THRESHOLDS:
            self.page.line(x, y + 4, x + 15, y + 4, color=color, width=1.5, dashed=(label != "Faixa alvo"))
            self.page.text(x + 19, y, f"{label} {range_label}", size=7.2, color=COLOR_MUTED)
            x += 126

    def _hourly_extremes(self) -> None:
        self._section_title("Ocorrências críticas por horário")
        low_by_hour = {int(row["hour"]): int(row["count"]) for row in self.context["hourly_lows"]}
        critical_by_hour = {int(row["hour"]): int(row["count"]) for row in self.context["hourly_highs_250"]}
        rows = []
        for hour in range(24):
            low = low_by_hour.get(hour, 0)
            critical = critical_by_hour.get(hour, 0)
            if not low and not critical:
                continue
            if low and critical:
                note = "Hipoglicemia e risco > 250 mg/dL"
            elif low:
                note = "Hipoglicemia < 70 mg/dL"
            else:
                note = "Risco > 250 mg/dL"
            rows.append([f"{hour:02d}h", low, critical, note])
        if not rows:
            rows = [["-", 0, 0, "Sem ocorrências críticas no período"]]
        self._table(["Horário", "< 70 mg/dL", "> 250 mg/dL", "Observação"], rows, [72, 82, 92, 277], font_size=7.7)

    def _daily_table(self) -> None:
        indicators = self.context["daily_indicators_json"]
        self._section_title("Indicadores diários consolidados")
        headers = ["Data", "Média", "% hipo", "% faixa", "% hiper", "Atípico", "Perfil do dia"]
        rows = [
            [
                _format_date(item.get("date")),
                f"{_format_number(item.get('avg_glucose'))} mg/dL",
                _format_number(item.get("pct_hypo"), "%"),
                _format_number(item.get("pct_in_range"), "%"),
                _format_number(item.get("pct_hyper"), "%"),
                "Sim" if item.get("anomaly_flag") else "Não",
                _profile_label(item),
            ]
            for item in indicators
        ]
        self._table(headers, rows, [58, 62, 50, 56, 56, 42, 199], font_size=7.0)

    def _readings_table(self) -> None:
        events = self.context["glucose_events_json"]
        self._section_title("Registros glicêmicos do período")
        rows = []
        for event in events:
            rows.append(
                [
                    _format_datetime(event.get("occurred_at")),
                    str(event.get("event_type_label") or event.get("event_type") or "-"),
                    str(event.get("event_subtype_label") or event.get("event_subtype") or "-"),
                    f"{_format_number(event.get('glucose_mg_dl'))} mg/dL",
                    str(event.get("context_label_display") or event.get("context_label") or "-"),
                    str(event.get("timestamp_quality_label") or event.get("timestamp_quality") or "-"),
                ]
            )
        self._table(["Quando", "Tipo", "Subtipo", "Valor", "Contexto", "Confiabilidade"], rows, [84, 78, 100, 62, 106, 93], font_size=6.8)

    def _table(self, headers: list[str], rows: list[list[object]], widths: list[float], *, font_size: float = 7.8) -> None:
        header_height = 18
        line_height = font_size + 2.4
        x_positions = [MARGIN_X]
        for width in widths[:-1]:
            x_positions.append(x_positions[-1] + width)

        def draw_header() -> None:
            self._ensure(header_height + 18)
            self.page.rect(MARGIN_X, self.y - header_height, sum(widths), header_height, fill=(0.95, 0.97, 0.99), stroke=COLOR_BORDER)
            for x, header in zip(x_positions, headers):
                self.page.text(x + 4, self.y - 12, header, size=7.5, bold=True, color=COLOR_MUTED)
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
            if row_index % 2 == 1:
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
        self._threshold_legend()
        self._distribution()
        daily_points = [
            (_format_date(item.get("date"))[:5], float(item.get("avg_glucose")))
            for item in self.context["daily_indicators_json"]
            if item.get("avg_glucose") is not None
        ]
        self._line_chart("Média glicêmica diária", daily_points)
        self._hourly_extremes()
        self._daily_table()
        self._readings_table()
        return self._finish()


def build_patient_report_pdf(context: dict[str, object]) -> bytes:
    return ClinicalReportPdf.create(context).render()


def patient_report_filename(context: dict[str, object]) -> str:
    patient = context["patient"]
    filters = context["filters"]
    patient_name = _safe_filename(patient.display_name)
    start = filters.get("start_date") or "inicio"
    end = filters.get("end_date") or "fim"
    return f"relatorio-glicemico-{patient_name}-{start}-{end}.pdf"
