"""Generate a deterministic sample patient report PDF for product review.

The production UI exports a report from live patient-detail data. This script
creates a small, static example with synthetic readings so reviewers can inspect
what a PDF version of the clinical report should communicate without requiring a
running browser or database.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from textwrap import shorten

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 42
HYPO_LIMIT = 70
HYPER_LIMIT = 180
CRITICAL_HYPER_LIMIT = 250
OUTPUT_PATH = Path("docs/examples/relatorio-paciente-exemplo.pdf")


@dataclass(frozen=True)
class Reading:
    date: str
    short_date: str
    time: str
    glucose: int
    context: str


READINGS = [
    Reading("2026-05-01", "01/05", "07:10", 64, "Antes do café"),
    Reading("2026-05-01", "01/05", "12:05", 138, "Antes do almoço"),
    Reading("2026-05-01", "01/05", "18:40", 224, "Após jantar"),
    Reading("2026-05-02", "02/05", "06:58", 92, "Antes do café"),
    Reading("2026-05-02", "02/05", "13:12", 172, "Após almoço"),
    Reading("2026-05-02", "02/05", "22:01", 261, "Ceia"),
    Reading("2026-05-03", "03/05", "07:22", 74, "Antes do café"),
    Reading("2026-05-03", "03/05", "11:52", 119, "Antes do almoço"),
    Reading("2026-05-03", "03/05", "19:08", 187, "Após jantar"),
    Reading("2026-05-04", "04/05", "06:45", 58, "Antes do café"),
    Reading("2026-05-04", "04/05", "12:30", 146, "Antes do almoço"),
    Reading("2026-05-04", "04/05", "20:15", 208, "Após jantar"),
    Reading("2026-05-05", "05/05", "07:05", 83, "Antes do café"),
    Reading("2026-05-05", "05/05", "13:35", 155, "Após almoço"),
    Reading("2026-05-05", "05/05", "21:20", 246, "Ceia"),
]


def pdf_string(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text.encode("latin-1", "replace").decode("latin-1")


class PdfCanvas:
    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.commands: list[str] = []

    def new_page(self) -> None:
        if self.commands:
            self.pages.append(self.commands)
        self.commands = []

    def save(self) -> bytes:
        if self.commands:
            self.pages.append(self.commands)
            self.commands = []

        objects: list[bytes] = []
        font_regular_id = 3 + len(self.pages) * 2
        font_bold_id = font_regular_id + 1
        page_ids = [3 + index * 2 for index in range(len(self.pages))]
        content_ids = [page_id + 1 for page_id in page_ids]
        pages_id = 2
        catalog_id = 1

        objects.append(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))
        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1"))

        for page_id, content_id, commands in zip(page_ids, content_ids, self.pages, strict=True):
            page = (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            )
            stream = "\n".join(commands).encode("latin-1")
            objects.append(page.encode("latin-1"))
            objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for object_id, payload in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
            pdf.extend(payload)
            pdf.extend(b"\nendobj\n")
        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        pdf.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        return bytes(pdf)

    def text(self, x: float, y: float, text: object, size: int = 10, bold: bool = False, color: tuple[float, float, float] = (0.09, 0.19, 0.29)) -> None:
        font = "F2" if bold else "F1"
        r, g, b = color
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({pdf_string(text)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, color: tuple[float, float, float] = (0.6, 0.75, 0.86), width: float = 1.0) -> None:
        r, g, b = color
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x: float, y: float, width: float, height: float, fill: tuple[float, float, float] | None = None, stroke: tuple[float, float, float] | None = (0.82, 0.91, 0.97)) -> None:
        if fill:
            r, g, b = fill
            self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f")
        if stroke:
            r, g, b = stroke
            self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG 0.80 w {x:.2f} {y:.2f} {width:.2f} {height:.2f} re S")

    def polyline(self, points: list[tuple[float, float]], color: tuple[float, float, float] = (0.08, 0.49, 0.85), width: float = 2.2) -> None:
        if len(points) < 2:
            return
        r, g, b = color
        path = [f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w {points[0][0]:.2f} {points[0][1]:.2f} m"]
        path.extend(f"{x:.2f} {y:.2f} l" for x, y in points[1:])
        path.append("S")
        self.commands.append(" ".join(path))


def by_day() -> dict[str, list[Reading]]:
    grouped: dict[str, list[Reading]] = {}
    for reading in READINGS:
        grouped.setdefault(reading.date, []).append(reading)
    return grouped


def classify(value: int) -> str:
    if value < HYPO_LIMIT:
        return "Hipo"
    if value > HYPER_LIMIT:
        return "Hiper"
    return "Em faixa"


def stats(readings: list[Reading]) -> dict[str, float | int]:
    values = [reading.glucose for reading in readings]
    total = len(values)
    hypo = sum(1 for value in values if value < HYPO_LIMIT)
    hyper = sum(1 for value in values if value > HYPER_LIMIT)
    return {
        "count": total,
        "avg": mean(values),
        "min": min(values),
        "max": max(values),
        "pct_hypo": (hypo / total) * 100,
        "pct_in_range": ((total - hypo - hyper) / total) * 100,
        "pct_hyper": (hyper / total) * 100,
        "hypo": hypo,
        "hyper": hyper,
    }


def draw_header(pdf: PdfCanvas, title: str, subtitle: str) -> None:
    pdf.rect(0, PAGE_HEIGHT - 115, PAGE_WIDTH, 115, fill=(0.92, 0.98, 1.0), stroke=None)
    pdf.text(MARGIN, PAGE_HEIGHT - 58, title, size=22, bold=True, color=(0.04, 0.30, 0.61))
    pdf.text(MARGIN, PAGE_HEIGHT - 80, subtitle, size=10, color=(0.29, 0.40, 0.52))
    pdf.text(PAGE_WIDTH - 174, PAGE_HEIGHT - 58, "MyGlico", size=16, bold=True, color=(0.04, 0.30, 0.61))
    pdf.text(PAGE_WIDTH - 174, PAGE_HEIGHT - 76, "Exemplo sintético", size=9, color=(0.29, 0.40, 0.52))


def draw_stat_cards(pdf: PdfCanvas, x: float, y: float, cards: list[tuple[str, str]], columns: int = 3) -> float:
    card_width = (PAGE_WIDTH - x - MARGIN - (columns - 1) * 10) / columns
    card_height = 54
    for index, (label, value) in enumerate(cards):
        col = index % columns
        row = index // columns
        cx = x + col * (card_width + 10)
        cy = y - row * (card_height + 10)
        pdf.rect(cx, cy, card_width, card_height, fill=(0.98, 0.99, 1.0))
        pdf.text(cx + 10, cy + 34, label.upper(), size=7, bold=True, color=(0.37, 0.45, 0.54))
        pdf.text(cx + 10, cy + 13, value, size=14, bold=True)
    rows = (len(cards) + columns - 1) // columns
    return y - rows * (card_height + 10)


def draw_distribution(pdf: PdfCanvas, x: float, y: float, period_stats: dict[str, float | int]) -> None:
    pdf.text(x, y, "Distribuição glicêmica do período", size=13, bold=True)
    bars = [
        ("Hipo < 70", period_stats["pct_hypo"], (0.89, 0.36, 0.45)),
        ("Em faixa", period_stats["pct_in_range"], (0.12, 0.67, 0.41)),
        ("Hiper > 180", period_stats["pct_hyper"], (0.96, 0.66, 0.24)),
    ]
    for index, (label, value, color) in enumerate(bars):
        yy = y - 34 - index * 32
        pdf.text(x, yy + 6, label, size=9)
        pdf.rect(x + 92, yy, 170, 13, fill=(0.92, 0.96, 0.99), stroke=None)
        pdf.rect(x + 92, yy, 170 * float(value) / 100, 13, fill=color, stroke=None)
        pdf.text(x + 272, yy + 3, f"{float(value):.1f}%", size=9, bold=True)


def draw_hourly(pdf: PdfCanvas, x: float, y: float) -> None:
    pdf.text(x, y, "Indicativo de hipo/hiperglicemia por hora", size=13, bold=True)
    hourly = {hour: {"hypo": 0, "critical": 0} for hour in range(24)}
    for reading in READINGS:
        hour = int(reading.time[:2])
        if reading.glucose < HYPO_LIMIT:
            hourly[hour]["hypo"] += 1
        if reading.glucose > CRITICAL_HYPER_LIMIT:
            hourly[hour]["critical"] += 1
    max_count = max(max(item["hypo"], item["critical"]) for item in hourly.values()) or 1
    for row, hour in enumerate([6, 7, 11, 12, 13, 18, 19, 20, 21, 22]):
        yy = y - 30 - row * 20
        pdf.text(x, yy, f"{hour:02d}h", size=8)
        pdf.rect(x + 32, yy - 1, 120, 5, fill=(0.92, 0.96, 0.99), stroke=None)
        pdf.rect(x + 32, yy - 1, 120 * hourly[hour]["hypo"] / max_count, 5, fill=(0.15, 0.72, 0.91), stroke=None)
        pdf.rect(x + 160, yy - 1, 120, 5, fill=(0.92, 0.96, 0.99), stroke=None)
        pdf.rect(x + 160, yy - 1, 120 * hourly[hour]["critical"] / max_count, 5, fill=(0.96, 0.66, 0.24), stroke=None)
        pdf.text(x + 290, yy, f"{hourly[hour]['hypo']} hipo / {hourly[hour]['critical']} >250", size=8)


def draw_trend(pdf: PdfCanvas, x: float, y: float, width: float, height: float, title: str, points: list[tuple[str, float]]) -> None:
    pdf.text(x, y + height + 22, title, size=13, bold=True)
    pdf.rect(x, y, width, height, fill=(0.98, 0.99, 1.0))
    values = [point[1] for point in points]
    min_value = min(values + [HYPO_LIMIT])
    max_value = max(values + [CRITICAL_HYPER_LIMIT])
    spread = max(max_value - min_value, 1)

    for limit, color in [(HYPO_LIMIT, (0.89, 0.36, 0.45)), (HYPER_LIMIT, (0.96, 0.66, 0.24)), (CRITICAL_HYPER_LIMIT, (0.48, 0.32, 0.80))]:
        yy = y + 12 + (limit - min_value) / spread * (height - 24)
        pdf.line(x, yy, x + width, yy, color=color, width=0.6)
        pdf.text(x + 4, yy + 3, f"{limit}", size=7, color=color)

    coords = []
    for index, (_label, value) in enumerate(points):
        xx = x + 20 + index * ((width - 40) / max(len(points) - 1, 1))
        yy = y + 12 + (value - min_value) / spread * (height - 24)
        coords.append((xx, yy))
    pdf.polyline(coords)
    for index, (label, _value) in enumerate(points):
        if index in {0, len(points) - 1} or index % 2 == 0:
            pdf.text(coords[index][0] - 10, y - 14, label, size=7, color=(0.37, 0.45, 0.54))


def draw_table(pdf: PdfCanvas, x: float, y: float, headers: list[str], rows: list[list[str]], widths: list[float], row_height: float = 20) -> float:
    pdf.rect(x, y, sum(widths), row_height, fill=(0.94, 0.98, 1.0))
    current_x = x
    for header, width in zip(headers, widths, strict=True):
        pdf.text(current_x + 5, y + 7, header.upper(), size=7, bold=True, color=(0.37, 0.45, 0.54))
        current_x += width
    yy = y - row_height
    for row in rows:
        current_x = x
        pdf.line(x, yy + row_height, x + sum(widths), yy + row_height, color=(0.82, 0.91, 0.97), width=0.5)
        for cell, width in zip(row, widths, strict=True):
            pdf.text(current_x + 5, yy + 7, shorten(cell, width=34, placeholder="..."), size=8)
            current_x += width
        yy -= row_height
    return yy


def create_pdf() -> bytes:
    grouped = by_day()
    daily_points = [(items[0].short_date, mean(reading.glucose for reading in items)) for items in grouped.values()]
    period_stats = stats(READINGS)
    pdf = PdfCanvas()

    pdf.new_page()
    draw_header(pdf, "Relatório glicêmico", "Paciente UCI 12 · Período 01/05/2026 a 05/05/2026")
    pdf.text(MARGIN, 700, "Estatísticas do período", size=15, bold=True)
    y = draw_stat_cards(
        pdf,
        MARGIN,
        632,
        [
            ("Dias observados", str(len(grouped))),
            ("Medições", str(period_stats["count"])),
            ("Média glicêmica", f"{period_stats['avg']:.1f} mg/dL"),
            ("% em hipo", f"{period_stats['pct_hypo']:.1f}%"),
            ("% em faixa", f"{period_stats['pct_in_range']:.1f}%"),
            ("% em hiper", f"{period_stats['pct_hyper']:.1f}%"),
        ],
    )
    draw_distribution(pdf, MARGIN, y - 10, period_stats)
    draw_hourly(pdf, MARGIN, y - 160)

    pdf.new_page()
    draw_header(pdf, "Média glicêmica e detalhamento diário", "Gráfico do período e exemplo de leituras do dia 04/05/2026")
    draw_trend(pdf, MARGIN, 515, 500, 175, "Média de glicemia pelo período", daily_points)
    selected_day = grouped["2026-05-04"]
    selected_stats = stats(selected_day)
    draw_stat_cards(
        pdf,
        MARGIN,
        420,
        [
            ("Leituras do dia", str(selected_stats["count"])),
            ("Média do dia", f"{selected_stats['avg']:.1f} mg/dL"),
            ("Mín / Máx", f"{selected_stats['min']} / {selected_stats['max']}"),
            ("% hipo", f"{selected_stats['pct_hypo']:.1f}%"),
            ("% faixa", f"{selected_stats['pct_in_range']:.1f}%"),
            ("% hiper", f"{selected_stats['pct_hyper']:.1f}%"),
        ],
    )
    pdf.text(MARGIN, 260, "Leituras registradas em 04/05/2026", size=13, bold=True)
    draw_table(
        pdf,
        MARGIN,
        225,
        ["Horário", "Glicemia", "Contexto", "Classificação"],
        [[reading.time, f"{reading.glucose} mg/dL", reading.context, classify(reading.glucose)] for reading in selected_day],
        [70, 90, 210, 130],
    )

    pdf.new_page()
    draw_header(pdf, "Indicadores diários consolidados", "Resumo por dia e todas as leituras do exemplo")
    rows = []
    for date, items in grouped.items():
        item_stats = stats(items)
        rows.append(
            [
                items[0].short_date + "/2026",
                f"{item_stats['avg']:.1f}",
                f"{item_stats['pct_hypo']:.1f}%",
                f"{item_stats['pct_in_range']:.1f}%",
                f"{item_stats['pct_hyper']:.1f}%",
                "Atenção" if item_stats["hypo"] or item_stats["hyper"] else "Estável",
            ]
        )
    y_after = draw_table(pdf, MARGIN, 675, ["Data", "Média", "% Hipo", "% Faixa", "% Hiper", "Perfil"], rows, [80, 75, 75, 75, 75, 120])
    pdf.text(MARGIN, y_after - 10, "Todas as leituras do período", size=13, bold=True)
    draw_table(
        pdf,
        MARGIN,
        y_after - 45,
        ["Data", "Hora", "Glicemia", "Contexto", "Classe"],
        [[reading.short_date, reading.time, f"{reading.glucose} mg/dL", reading.context, classify(reading.glucose)] for reading in READINGS],
        [60, 60, 90, 210, 80],
        row_height=18,
    )

    return pdf.save()


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(create_pdf())
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
