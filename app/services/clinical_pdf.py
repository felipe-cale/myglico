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
    ("Hipoglicemia", "< 70 mg/dL", COLOR_HYPO),
    ("Faixa alvo", "70 a 180 mg/dL", COLOR_TARGET),
    ("Hiperglicemia", "> 180 mg/dL", COLOR_HYPER),
    ("Risco elevado", ">= 250 mg/dL", COLOR_CRITICAL),
]

LOGO_IMAGE_PATH = Path(__file__).resolve().parents[2] / "frontend-react" / "public" / "img" / "myglico-logo.png"
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
    if glucose >= CRITICAL_HYPER_LIMIT:
        return "Risco elevado", COLOR_CRITICAL
    if glucose > HYPER_LIMIT:
        return "Hiperglicemia", COLOR_HYPER
    return "Em faixa", COLOR_TARGET


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


def _period_profile(summary: dict[str, object]) -> str:
    avg = float(summary.get("avg_glucose") or 0)
    pct_hypo = float(summary.get("pct_hypo") or 0)
    pct_hyper = float(summary.get("pct_hyper") or 0)
    if pct_hyper >= 65 or avg >= 185:
        return "Perfil hiperglicêmico"
    if pct_hypo >= 10:
        return "Perfil hipoglicêmico"
    return "Perfil em faixa"


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


def _weekday_label(date_value: object) -> str:
    names = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
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

    @property
    def is_attention(self) -> bool:
        return bool(self.attention_reasons)

    @property
    def primary_attention_reason(self) -> str:
        return self.attention_reasons[0] if self.attention_reasons else "-"

    @property
    def attention_classification(self) -> str:
        if not self.attention_reasons:
            return "Sem alerta"
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


def _detect_attention_for_day(summary: DailyGlucoseSummary) -> None:
    reasons: list[str] = []
    notes: list[str] = []

    if summary.anomaly_flag:
        reasons.append("Dia estatisticamente atípico")
        notes.append("sinalizado pela análise automatizada")
    if summary.low_count:
        reasons.append("Hipoglicemia")
        notes.append(f"{summary.low_count} leitura(s) < 70 mg/dL")
    if summary.critical_count:
        reasons.append("Risco elevado")
        notes.append(f"{summary.critical_count} leitura(s) >= 250 mg/dL")
    if summary.count and summary.pct_hyper >= 50:
        reasons.append("Predomínio hiperglicêmico")
        notes.append(f"{_format_number(summary.pct_hyper, '%')} das leituras do dia > 180 mg/dL")
    if summary.count and summary.pct_in_range == 0:
        reasons.append("100% fora da faixa alvo")
        notes.append("nenhuma leitura entre 70 e 180 mg/dL")
    if summary.amplitude is not None and summary.amplitude >= 100:
        reasons.append("Alta variabilidade")
        notes.append(f"amplitude diária de {_format_number(summary.amplitude)} mg/dL")
    if summary.avg_glucose is not None and summary.avg_glucose < HYPO_LIMIT:
        reasons.append("Média diária muito baixa")
        notes.append("média do dia abaixo de 70 mg/dL")
    if summary.avg_glucose is not None and summary.avg_glucose >= CRITICAL_HYPER_LIMIT:
        reasons.append("Média diária muito alta")
        notes.append("média do dia >= 250 mg/dL")

    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason not in deduped_reasons:
            deduped_reasons.append(reason)
    summary.attention_reasons = deduped_reasons
    summary.attention_note = "; ".join(notes[:3]) if notes else "-"

    extreme_events = [
        event
        for event in summary.events
        if event.get("glucose_mg_dl") is not None
        and (float(event["glucose_mg_dl"]) < HYPO_LIMIT or float(event["glucose_mg_dl"]) >= CRITICAL_HYPER_LIMIT)
    ]
    summary.extreme_times = [str(event.get("event_time") or _format_datetime(event.get("occurred_at"))[-5:]) for event in extreme_events]
    contexts = [
        str(event.get("context_label_display") or event.get("context_label") or "-")
        for event in extreme_events
        if event.get("context_label_display") or event.get("context_label")
    ]
    summary.extreme_contexts = list(dict.fromkeys(contexts))


def build_daily_glucose_summaries(context: dict[str, object]) -> list[DailyGlucoseSummary]:
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
        _detect_attention_for_day(summary)
        summaries.append(summary)

    return summaries


def build_attention_days(context: dict[str, object]) -> list[DailyGlucoseSummary]:
    return [summary for summary in build_daily_glucose_summaries(context) if summary.is_attention]


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

    @classmethod
    def create(cls, context: dict[str, object]) -> "ClinicalReportPdf":
        report = cls(
            context=context,
            document=PdfDocument(),
            page=PdfPage(),
            y=PAGE_HEIGHT - MARGIN_TOP,
            page_width=PAGE_WIDTH,
            page_height=PAGE_HEIGHT,
            daily_summaries=build_daily_glucose_summaries(context),
        )
        report.document.add_image(_load_png_image(LOGO_IMAGE_PATH))
        report._new_page()
        return report

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
        footer = "MyGlico - relatório gerado automaticamente para apoio à revisão clínica. Não substitui avaliação médica."
        self.page.line(MARGIN_X, 25, self.page_width - MARGIN_X, 25, color=COLOR_BORDER, width=0.6)
        self.page.text(MARGIN_X, 14, footer, size=7.8, color=COLOR_MUTED)
        self.page.text(self.page_width - MARGIN_X - 34, 14, f"Página {self.page_number}", size=7.8, color=COLOR_MUTED)

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
        period = f"{_format_date(filters.get('start_date'))} a {_format_date(filters.get('end_date'))}"
        self._myglico_logo(MARGIN_X, self.y + 3, scale=0.34)
        self.page.text(MARGIN_X + 44, self.y, "Relatório glicêmico", size=8.2, bold=True, color=COLOR_TEXT)
        self.page.text(MARGIN_X + 44, self.y - 11, f"{patient.display_name} | {period}", size=7.8, color=COLOR_MUTED)
        self.page.text(self.page_width - MARGIN_X - 58, self.y, f"Página {self.page_number}", size=7.8, color=COLOR_MUTED)
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
        generated_at = datetime.now(REPORT_TIMEZONE).strftime("%d/%m/%Y %H:%M")

        self.page.rect(0, self.page_height - 104, self.page_width, 104, fill=(0.94, 0.98, 1.0))
        self._myglico_logo(MARGIN_X, self.page_height - 24, scale=0.82)
        title_x = MARGIN_X + 112
        self.page.text(title_x, self.page_height - 48, "Relatório glicêmico", size=20, bold=True, color=(0.05, 0.13, 0.22))
        self.page.text(title_x, self.page_height - 66, "Resumo do controle glicêmico no período analisado", size=8.8, color=COLOR_MUTED)
        self.page.rect(self.page_width - MARGIN_X - 134, self.page_height - 76, 134, 42, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.text(self.page_width - MARGIN_X - 124, self.page_height - 50, "Data da geração", size=7.6, bold=True, color=COLOR_MUTED)
        self.page.text(self.page_width - MARGIN_X - 124, self.page_height - 64, generated_at, size=10.2, bold=True, color=COLOR_TEXT)
        self.y = self.page_height - 128
        self._identification_panel(generated_at)
        self._space(16)

        period = f"{_format_date(filters.get('start_date'))} a {_format_date(filters.get('end_date'))}"
        intro = f"Relatório glicêmico referente ao período de {period}, gerado para apoio à revisão clínica."
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
        rows = [
            (left_x, top - 17, "Paciente", patient.display_name),
            (left_x, top - 35, "Período analisado", f"{_format_date(filters.get('start_date'))} a {_format_date(filters.get('end_date'))}"),
            (left_x, top - 53, "Data da geração", generated_at),
            (right_x, top - 17, "Medições", summary.get("glucose_measurements", "-")),
            (right_x, top - 35, "Dias observados", summary.get("days_observed", "-")),
            (right_x, top - 53, "Perfil do período", _period_profile(summary)),
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
            ("Média glicêmica", f"{_format_number(summary.get('avg_glucose') or stats['avg'])} mg/dL"),
            ("% hipo", _format_number(summary.get("pct_hypo", stats["pct_hypo"]), "%")),
            ("% faixa alvo", _format_number(summary.get("pct_in_range", stats["pct_in_range"]), "%")),
            ("% hiper", _format_number(summary.get("pct_hyper", stats["pct_hyper"]), "%")),
            ("Risco elevado", str(stats["critical_count"])),
            ("Mín / Máx", f"{_format_number(stats['min'])} / {_format_number(stats['max'])}"),
            ("Dias atípicos", str(summary.get("anomaly_days", "-"))),
            ("Pontos atenção", str(attention_count)),
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

        self._section_title("Resultados do acompanhamento glicêmico", keep_with=95)
        rows = [
            [
                "Média glicêmica diária",
                f"{_format_number(avg)} mg/dL",
                "Faixa operacional do painel: 70 a 180 mg/dL",
            ],
            [
                "% médio diário em hipoglicemia",
                _format_number(pct_hypo, "%"),
                "Hipoglicemia: < 70 mg/dL",
            ],
            [
                "% médio diário em faixa alvo",
                _format_number(pct_range, "%"),
                "Faixa alvo: 70 a 180 mg/dL",
            ],
            [
                "% médio diário em hiperglicemia",
                _format_number(pct_hyper, "%"),
                "Hiperglicemia: > 180 mg/dL",
            ],
            [
                "Eventos de risco elevado",
                f"{stats['critical_count']} leitura(s)",
                "Risco elevado: >= 250 mg/dL",
            ],
            [
                "Menor / maior leitura",
                f"{_format_number(stats['min'])} / {_format_number(stats['max'])} mg/dL",
                "Limiares usados: 70, 180 e 250 mg/dL",
            ],
            [
                "Dias atípicos",
                str(summary.get("anomaly_days", "-")),
                "Sinalização automática do detalhamento",
            ],
        ]
        self._table(["Exame / indicador", "Resultado", "Valor de referência"], rows, [185, 112, self.content_width - 297], font_size=7.5)
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
            notes.append("Percentual relevante de hipoglicemia; revisar horários, alimentação e conduta em contexto clínico.")
        if pct_hyper >= 65 or avg >= 185:
            notes.append("Predomínio hiperglicêmico no período, conforme critérios de triagem do painel.")
        if int(stats["critical_count"]) > 0:
            notes.append(f"{stats['critical_count']} leitura(s) atingiram faixa de risco elevado (>= 250 mg/dL).")
        if anomaly_days > 0:
            notes.append(f"{anomaly_days} dia(s) foram sinalizados como atípicos pela análise automatizada.")
        if not notes:
            notes.append("Sem alertas automáticos relevantes no recorte, considerando os limiares configurados.")
        notes.append("Percentuais do resumo seguem o detalhamento do paciente e representam médias dos indicadores diários no período.")
        return notes

    def _threshold_legend(self) -> None:
        self._section_title("Legenda dos limiares glicêmicos", keep_with=78)
        columns = 2
        gap = 10
        width = (self.content_width - gap) / columns
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
        self._section_title("Distribuição glicêmica do período", keep_with=70)
        values = [
            ("Hipoglicemia", summary.get("pct_hypo", stats["pct_hypo"]), COLOR_HYPO),
            ("Faixa alvo", summary.get("pct_in_range", stats["pct_in_range"]), COLOR_TARGET),
            ("Hiperglicemia", summary.get("pct_hyper", stats["pct_hyper"]), COLOR_HYPER),
        ]
        self._ensure(70)
        bar_width = self.content_width - 128
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
            self.page.text(MARGIN_X, self.y - 18, "Sem dados suficientes para o gráfico.", size=9, color=COLOR_MUTED)
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
            radius = 4.2 if classification in {"Hipoglicemia", "Risco elevado"} else 3.6
            self.page.circle(x, y, radius, fill=color, stroke=(1, 1, 1))
            if classification in {"Hipoglicemia", "Risco elevado"}:
                self.page.text(x + 5, y + 4, _format_number(value), size=7.0, bold=True, color=COLOR_TEXT)

        step = max(1, ceil(len(points) / 7))
        for index, (label, _) in enumerate(points):
            if index in (0, len(points) - 1) or index % step == 0:
                x, _ = coords[index]
                self.page.text(x - 12, bottom + 7, label, size=7.6, color=COLOR_MUTED)
        self._legend_line(bottom - 12)
        self.y = bottom - 32

    def _legend_line(self, y: float) -> None:
        x = MARGIN_X
        for label, range_label, color in THRESHOLDS:
            self.page.line(x, y + 4, x + 15, y + 4, color=color, width=1.5, dashed=(label != "Faixa alvo"))
            self.page.text(x + 19, y, f"{label} {range_label}", size=7.2, color=COLOR_MUTED)
            x += 126

    def _hourly_extremes(self) -> None:
        self._section_title("Ocorrências críticas por horário", keep_with=62)
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
                note = "Hipoglicemia e risco >= 250 mg/dL"
            elif low:
                note = "Hipoglicemia < 70 mg/dL"
            else:
                note = "Risco >= 250 mg/dL"
            rows.append([f"{hour:02d}h", low, critical, note])
        if not rows:
            rows = [["-", 0, 0, "Sem ocorrências críticas no período"]]
        self._table(
            ["Horário", "< 70 mg/dL", ">= 250 mg/dL", "Observação"],
            rows,
            [82, 110, 120, self.content_width - 312],
            font_size=8.4,
        )

    def _daily_table(self) -> None:
        self._section_title("Indicadores diários consolidados", keep_with=64)
        headers = ["Data", "Qtd", "Média", "Mín", "Máx", "% hipo", "% faixa", "% hiper", "Alerta"]
        rows = [
            [
                _format_date(item.date),
                item.count,
                f"{_format_number(item.avg_glucose)}",
                _format_number(item.min_glucose),
                _format_number(item.max_glucose),
                _format_number(item.pct_hypo, "%"),
                _format_number(item.pct_in_range, "%"),
                _format_number(item.pct_hyper, "%"),
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
            "Traço lateral bege/laranja: dia com ponto de atenção",
            size=7.8,
            bold=True,
            color=COLOR_TEXT,
        )
        self.page.text(
            MARGIN_X + 280,
            top - 14,
            "Indica dias que atingiram critérios automáticos de alerta.",
            size=7.4,
            color=COLOR_MUTED,
        )

        self.y -= legend_height + 8

    def _attention_days_table(self) -> None:
        self._section_title("Dias atípicos e pontos de atenção", keep_with=74)
        attention_days = [item for item in self.daily_summaries if item.is_attention]
        if not attention_days:
            self._ensure(26)
            self.page.rect(MARGIN_X, self.y - 24, self.content_width, 24, fill=COLOR_PANEL, stroke=COLOR_BORDER)
            self.page.text(MARGIN_X + 8, self.y - 15, "Nenhum dia do período atingiu os critérios automáticos de ponto de atenção.", size=8.2, color=COLOR_MUTED)
            self.y -= 30
            return

        rows = [
            [
                _format_date(item.date),
                item.attention_classification,
                item.attention_note,
                _format_number(item.avg_glucose),
                f"{_format_number(item.min_glucose)} / {_format_number(item.max_glucose)}",
                item.count,
                f"{_format_number(item.pct_hypo, '%')} | {_format_number(item.pct_in_range, '%')} | {_format_number(item.pct_hyper, '%')}",
                ", ".join(item.extreme_times) or "-",
                ", ".join(item.extreme_contexts[:2]) or "-",
            ]
            for item in attention_days
        ]
        self._table(
            ["Data", "Alerta", "Motivo", "Média", "Mín/Máx", "Qtd", "H/F/Hiper", "Extremos", "Contexto"],
            rows,
            [56, 130, 185, 48, 68, 32, 88, 62, self.content_width - 669],
            font_size=6.9,
            row_flags=[True for _ in rows],
        )

    def _readings_table(self) -> None:
        events = self.context["glucose_events_json"]
        self._section_title("Leituras glicêmicas completas", keep_with=64)
        rows = []
        for event in events:
            rows.append(
                [
                    _format_datetime(event.get("occurred_at")),
                    str(event.get("event_type_label") or event.get("event_type") or "-"),
                    str(event.get("event_subtype_label") or event.get("event_subtype") or "-"),
                    f"{_format_number(event.get('glucose_mg_dl'))} mg/dL",
                    str(event.get("context_label_display") or event.get("context_label") or "-"),
                ]
            )
        self._table(
            ["Quando", "Tipo", "Subtipo", "Valor", "Contexto"],
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
            radius = 3.4 if classification in {"Hipoglicemia", "Risco elevado"} else 2.6
            self.page.circle(point_x, point_y, radius, fill=color, stroke=(1, 1, 1))
            if classification in {"Hipoglicemia", "Risco elevado"}:
                self.page.text(point_x + 4, point_y + 3, _format_number(event.get("glucose_mg_dl")), size=6.2, bold=True, color=COLOR_TEXT)

    def _draw_day_detail_block(self, summary: DailyGlucoseSummary) -> None:
        block_height = 218
        self._ensure(block_height + 10)
        top = self.y
        self.page.rect(MARGIN_X, top - block_height, self.content_width, block_height, fill=(1, 1, 1), stroke=COLOR_BORDER)
        self.page.rect(MARGIN_X, top - block_height, 3, block_height, fill=COLOR_HYPER if summary.is_attention else COLOR_BLUE)
        title = f"{_format_date(summary.date)} | {_weekday_label(summary.date)}"
        self.page.text(MARGIN_X + 10, top - 15, title, size=10, bold=True, color=COLOR_TEXT)
        badge = "Ponto de atenção" if summary.is_attention else "Sem alerta automático"
        self.page.text(self.page_width - MARGIN_X - 116, top - 15, badge, size=7.5, bold=True, color=COLOR_HYPER if summary.is_attention else COLOR_MUTED)

        metrics = [
            ("Leituras", summary.count),
            ("Média", f"{_format_number(summary.avg_glucose)} mg/dL"),
            ("Mín/Máx", f"{_format_number(summary.min_glucose)} / {_format_number(summary.max_glucose)}"),
            ("% H/F/Hiper", f"{_format_number(summary.pct_hypo, '%')} | {_format_number(summary.pct_in_range, '%')} | {_format_number(summary.pct_hyper, '%')}"),
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
        self.page.text(chart_x, chart_y - 23, "Pontos = leituras pontuais. Linha discreta apenas facilita a leitura visual.", size=6.4, color=COLOR_MUTED)

        table_x = chart_x + chart_width + 28
        self.page.text(table_x, top - 63, "Leituras do dia", size=7.5, bold=True, color=COLOR_TEXT)
        header_y = top - 78
        headers = [("Hora", 0), ("Valor", 34), ("Contexto", 78), ("Classe", 154)]
        for header, offset in headers:
            self.page.text(table_x + offset, header_y, header, size=6.2, bold=True, color=COLOR_MUTED)
        row_y = header_y - 12
        for event in summary.events[:7]:
            classification, color = _classify_glucose(event.get("glucose_mg_dl"))
            context = str(event.get("context_label_display") or event.get("context_label") or "-")
            self.page.text(table_x, row_y, str(event.get("event_time") or "-"), size=6.3, color=COLOR_TEXT)
            self.page.text(table_x + 34, row_y, _format_number(event.get("glucose_mg_dl")), size=6.3, bold=True, color=color)
            self.page.text(table_x + 78, row_y, _wrap_text(context, 6.3, 72)[0], size=6.3, color=COLOR_TEXT)
            self.page.text(table_x + 154, row_y, classification, size=6.3, color=color)
            row_y -= 11
        if len(summary.events) > 7:
            self.page.text(table_x, row_y, f"+ {len(summary.events) - 7} leitura(s) no anexo", size=6.2, color=COLOR_MUTED)

        if summary.is_attention:
            reason = _wrap_text(f"Motivo: {summary.attention_note}", 7.1, self.content_width - 24)
            note_y = top - 198
            for line in reason[:2]:
                self.page.text(MARGIN_X + 10, note_y, line, size=7.1, color=COLOR_HYPER)
                note_y -= 10
        self.y -= block_height + 10

    def _detailed_period_analysis(self) -> None:
        self._section_title("Análise detalhada do período", keep_with=260)
        self.y = self._wrapped_text(
            MARGIN_X,
            self.y,
            "Os gráficos diários usam eixo de 00h a 24h e exibem apenas leituras glicêmicas reais registradas no MyGlico.",
            self.content_width,
            size=8.2,
            color=COLOR_MUTED,
        )
        self._space(10)
        for index in range(0, len(self.daily_summaries), 7):
            week_days = self.daily_summaries[index : index + 7]
            start = _format_date(week_days[0].date)
            end = _format_date(week_days[-1].date)
            self._ensure(42)
            self.page.text(MARGIN_X, self.y, f"Bloco {index // 7 + 1}: {start} a {end}", size=11, bold=True, color=COLOR_BLUE)
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
            (_format_date(item.get("date"))[:5], float(item.get("avg_glucose")))
            for item in self.context["daily_indicators_json"]
            if item.get("avg_glucose") is not None
        ]
        self._line_chart("Média glicêmica diária", daily_points)
        self._hourly_extremes()
        self._attention_days_table()
        self._daily_table()
        self._readings_table()
        self._detailed_period_analysis()
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