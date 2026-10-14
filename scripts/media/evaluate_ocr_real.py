"""Run the signed worker endpoint against the four authorized local F1 images."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

import psutil
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.media_worker.service import create_media_app
from app.media_worker.image import ImageLimits, PaddleReadingExtractor


class LocalReplayStore:
    """Single-process nonce store for this local, signed endpoint evaluation."""

    def __init__(self):
        self.values: set[str] = set()
        self.lock = threading.Lock()

    def consume_once(self, nonce: str, expires_at: int) -> bool:  # noqa: ARG002
        with self.lock:
            if nonce in self.values:
                return False
            self.values.add(nonce)
            return True


def _worker_headers(secret: bytes, body: bytes, path: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(("POST", path, timestamp, nonce, digest)).encode("ascii")
    signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/octet-stream",
        "X-Correlation-Id": secrets.token_urlsafe(24),
        "X-Worker-Timestamp": timestamp,
        "X-Worker-Nonce": nonce,
        "X-Worker-Content-Sha256": digest,
        "X-Worker-Signature": signature,
    }


def evaluate(images: Path, model_root: Path, deadline_seconds: float) -> list[dict]:
    os.environ["PADDLE_PDX_MODEL_SOURCE"] = "LOCAL"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    secret = b"local-ocr-f1-evaluation-secret-32bytes!"
    extractor = PaddleReadingExtractor(
        str(model_root / "paddle-det"),
        str(model_root / "paddle-rec"),
        limits=ImageLimits(deadline_seconds=deadline_seconds),
    )
    cases = (("foto1.png", 106), ("foto2.png", 172), ("foto3.png", 125), ("foto4.png", 107))
    results: list[dict] = []
    cold_samples, warm_samples = [], []
    for filename, expected in cases:
        app = create_media_app(secret, LocalReplayStore(), extractor=extractor)
        parent = psutil.Process()
        stop_sampling = threading.Event()
        peak_rss = [parent.memory_info().rss]

        def sample_memory():
            while not stop_sampling.wait(0.05):
                try:
                    peak_rss[0] = max(peak_rss[0], parent.memory_info().rss + sum(
                        child.memory_info().rss for child in parent.children(recursive=True)))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        sampler = threading.Thread(target=sample_memory, daemon=True)
        sampler.start()
        # Include model import/load in cold latency; app startup owns warmup.
        client = TestClient(app)
        load_started = time.perf_counter()
        client.__enter__()
        cold_startup_ms = round((time.perf_counter() - load_started) * 1000)
        body = (images / filename).read_bytes()
        path = "/internal/extract/image"
        def send_one():
            hdr = _worker_headers(secret, body, path)
            return client.post(path, content=body, headers=hdr)
        start = time.perf_counter()
        response = send_one()
        cold_request_ms = round((time.perf_counter() - start) * 1000)
        cold_total_ms = cold_startup_ms + cold_request_ms
        cold_samples.append(cold_total_ms)
        warm_latencies = []
        for _ in range(2):
            start = time.perf_counter()
            warm_response = send_one()
            warm_latencies.append(round((time.perf_counter() - start) * 1000))
            if warm_response.status_code != 200: response = warm_response
        warm_samples.extend(warm_latencies)
        stop_sampling.set()
        sampler.join(timeout=1)
        payload = response.json()
        candidates = payload.get("candidates", []) if response.status_code == 200 else []
        candidate_texts = [str(item.get("text", "")) for item in candidates]
        numbers = []
        import re
        for text in candidate_texts:
            numbers.extend(re.findall(r"(?<!\d)\d+(?:[.,]\d+)?(?!\d)", text))
        numeric_values = [float(value.replace(",", ".")) for value in numbers]
        recognized = next((value for value in numeric_values if value == expected), None)
        unit_candidates = [text for text in candidate_texts if re.search(r"mg\s*/?\s*d[l1]", text, re.I)]
        assessment = payload.get("assessment", {})
        results.append({
            "file": filename, "expected_mg_dl": expected, "http_status": response.status_code,
            "error": payload.get("detail"), "recognized_expected_value": recognized,
            "value_exact": recognized == expected, "ocr_numeric_candidates": numeric_values,
            "unit_candidates": unit_candidates,
            "candidate_confidences": [item.get("confidence") for item in candidates],
            "candidate_texts": candidate_texts,
            "clarification_requested": assessment.get("needs_clarification"), "assessment": assessment,
            "cold_startup_ms": cold_startup_ms, "cold_request_ms": cold_request_ms,
            "cold_total_ms": cold_total_ms, "warm_request_ms": warm_latencies,
            "elapsed_ms_worker": payload.get("elapsed_ms"), "latency_ms_wall": cold_request_ms,
            "peak_rss_mib_observed": round(peak_rss[0] / 1024**2, 1), "engine": payload.get("engine"),
        })
        del body
        client.__exit__(None, None, None)
    results.append({"summary": {
        "cold_samples_n": len(cold_samples), "cold_p50_ms": _percentile(cold_samples, .50),
        "cold_p95_ms": _percentile(cold_samples, .95), "warm_samples_n": len(warm_samples),
        "warm_p50_ms": _percentile(warm_samples, .50), "warm_p95_ms": _percentile(warm_samples, .95),
    }})
    return results


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values: return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * quantile))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(evaluate(args.images.resolve(), args.models.resolve(), args.deadline_seconds), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
