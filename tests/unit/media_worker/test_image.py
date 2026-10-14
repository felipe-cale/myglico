import io

import pytest
from PIL import Image

from app.media_worker.image import ImageLimits, MediaError, PaddleReadingExtractor, _decode_image, _normalize_paddle
from app.media_worker.service import _assessment


def image_bytes(fmt="PNG", size=(160, 80), color="white"):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format=fmt)
    return stream.getvalue()


def test_decode_accepts_one_bounded_static_image_in_memory():
    decoded = _decode_image(image_bytes(), ImageLimits())
    assert decoded.size == (160, 80)
    assert decoded.mode == "RGB"
    decoded.close()


def test_decode_rejects_oversize_pixels_and_non_image_payloads():
    with pytest.raises(MediaError, match="payload_too_large"):
        _decode_image(image_bytes(), ImageLimits(max_bytes=10),)
    with pytest.raises(MediaError, match="payload_too_large"):
        _decode_image(image_bytes(size=(101, 100)), ImageLimits(max_pixels=1000))
    with pytest.raises(MediaError, match="invalid_image"):
        _decode_image(b"not an image", ImageLimits())


def test_decode_rejects_animated_images():
    stream = io.BytesIO()
    frames = [Image.new("RGB", (8, 8), color) for color in ("white", "black")]
    frames[0].save(stream, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(MediaError, match="unsupported_media_type"):
        _decode_image(stream.getvalue(), ImageLimits())


def test_paddle_output_is_normalized_and_bounded():
    class Result:
        json = {"res": {
            "rec_texts": ["  128 mg/dL\n" + "x" * 200, ""],
            "rec_scores": [0.98, 0.4],
            "dt_polys": [[[3, 4], [15, 4], [15, 9], [3, 9]], []],
        }}

    result = _normalize_paddle([Result()], ImageLimits(max_line_chars=24))
    assert len(result) == 1
    assert result[0].text == "128 mg/dL xxxxxxxxxxxxxx"
    assert len(result[0].text) == 24
    assert result[0].confidence == 0.98
    assert result[0].box == (3, 4, 15, 9)


def test_adapter_fails_closed_without_provisioned_local_models():
    with pytest.raises(MediaError, match="capability_unavailable"):
        PaddleReadingExtractor().extract(image_bytes())


@pytest.mark.parametrize("value", [19, 601, 1006])
def test_assessment_rejects_values_outside_configured_physiological_range(value):
    result = _assessment([value], True, 0.99, ImageLimits())
    assert result["needs_clarification"] is True
    assert result["candidate_value_mg_dl"] is None
    assert "value_out_of_range" in result["clarification_reasons"]


def test_assessment_rejects_low_confidence_and_multiple_competing_values():
    low_confidence = _assessment([128], True, 0.4, ImageLimits())
    competing = _assessment([128, 228], True, 0.99, ImageLimits())
    assert "confidence_below_threshold" in low_confidence["clarification_reasons"]
    assert low_confidence["candidate_value_mg_dl"] is None
    assert "multiple_candidates" in competing["clarification_reasons"]
    assert competing["candidate_value_mg_dl"] is None


def test_assessment_requires_unit_and_confidence_before_returning_single_value():
    missing_unit = _assessment([128], False, 0.99, ImageLimits())
    missing_confidence = _assessment([128], True, None, ImageLimits())
    assert "unit_missing" in missing_unit["clarification_reasons"]
    assert missing_unit["candidate_value_mg_dl"] is None
    assert "confidence_unavailable" in missing_confidence["clarification_reasons"]


class _Replay:
    def __init__(self):
        self.used = set()

    def consume_once(self, nonce, expires_at):
        if nonce in self.used:
            return False
        self.used.add(nonce)
        return True


def _post_image(engine, body, nonce="G" * 24):
    import time
    from fastapi.testclient import TestClient
    from app.media_worker.auth import sign_request
    from app.media_worker.service import create_media_app

    signed = sign_request(b"w" * 32, "POST", "/internal/extract/image", str(int(time.time())), nonce, body)
    headers = {
        "content-type": "application/octet-stream", "x-correlation-id": "syntheticCorrelation123",
        "x-worker-timestamp": signed.timestamp, "x-worker-nonce": signed.nonce,
        "x-worker-content-sha256": signed.body_sha256, "x-worker-signature": signed.signature,
    }
    client = TestClient(create_media_app(b"w" * 32, _Replay(), engine))
    return client.post("/internal/extract/image", content=body, headers=headers)


class _Engine:
    """First pass misreads the LCD as 1006; smoothed copies read 106 (what the real OCR does)."""
    limits = ImageLimits()

    def __init__(self, first, later):
        self.first, self.later, self.calls = first, later, 0

    async def extract_async(self, data):
        from app.media_worker.image import Extraction, TextCandidate
        self.calls += 1
        texts = self.first if self.calls == 1 else self.later
        return Extraction(tuple(TextCandidate(t, 0.9, (0, 0, 40, 60)) for t in texts), "fake-test-only", 5)


def test_a_first_pass_that_does_not_conclude_is_retried_on_smoothed_copies():
    engine = _Engine(["1006", "mg/dL"], ["106", "mg/dL"])
    response = _post_image(engine, image_bytes(size=(240, 240)))
    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["candidate_value_mg_dl"] == 106 and assessment["needs_clarification"] is False
    assert engine.calls == 2


def test_a_conclusive_first_pass_is_never_retried():
    engine = _Engine(["106", "mg/dL"], ["999"])
    assert _post_image(engine, image_bytes(size=(240, 240)), "H" * 24).json()["assessment"]["candidate_value_mg_dl"] == 106
    assert engine.calls == 1


def test_hi_lo_is_not_retried_and_still_never_becomes_a_value():
    engine = _Engine(["HI"], ["120"])
    response = _post_image(engine, image_bytes(size=(240, 240)), "J" * 24)
    assert response.json()["assessment"]["needs_clarification"] is True
    assert engine.calls == 1


class _Scripted:
    """Engine whose successive OCR passes return scripted (text, confidence) lists."""
    limits = ImageLimits()

    def __init__(self, passes):
        self.passes, self.calls = passes, 0

    async def extract_async(self, data):
        from app.media_worker.image import Extraction, TextCandidate
        texts = self.passes[min(self.calls, len(self.passes) - 1)]
        self.calls += 1
        return Extraction(tuple(TextCandidate(t, c, (0, 0, 40, 60)) for t, c in texts), "fake-test-only", 5)


def test_two_reads_that_agree_are_trusted_even_below_the_single_pass_floor():
    # the real Accu-Chek photo: 106 at 0.70, then 106 at 0.72 on a rescaled copy
    engine = _Scripted([[("106", 0.70), ("mg/dL", 1.0)], [("106", 0.72), ("mg/dL", 1.0)]])
    assessment = _post_image(engine, image_bytes(size=(240, 240)), "L" * 24).json()["assessment"]
    assert assessment["needs_clarification"] is False
    assert assessment["candidate_value_mg_dl"] == 106 and assessment["agreed_passes"] >= 2


def test_reads_that_disagree_or_are_too_weak_still_ask_for_clarification():
    disagree = _Scripted([[("106", 0.70)], [("108", 0.72)], [("1106", 0.9)]])
    assert _post_image(disagree, image_bytes(size=(240, 240)), "M" * 24).json()["assessment"]["needs_clarification"] is True
    weak = _Scripted([[("106", 0.40)], [("106", 0.45)], [("106", 0.30)]])
    assert _post_image(weak, image_bytes(size=(240, 240)), "N" * 24).json()["assessment"]["needs_clarification"] is True
    single = _Scripted([[("106", 0.70)], [("12", 0.9)], [("5", 0.9)]])
    assert _post_image(single, image_bytes(size=(240, 240)), "P" * 24).json()["assessment"]["needs_clarification"] is True


def test_the_gateway_accepts_an_agreed_read_but_not_a_weak_single_one():
    from app.api.glico_routes import _trusted_worker_assessment

    base = {"status": "review_required", "needs_clarification": False, "clarification_reasons": [],
            "candidate_value_mg_dl": 106, "candidate_confidence": 0.70, "confidence_threshold": 0.6}
    assert _trusted_worker_assessment({"assessment": {**base, "agreed_passes": 2}}, "image") == 106.0
    assert _trusted_worker_assessment({"assessment": base}, "image") is None


def test_large_photos_are_downscaled_for_ocr_and_small_ones_are_untouched():
    from app.media_worker.image import WORKING_SIDE, prepare_for_ocr

    large = image_bytes(size=(1600, 1200))
    resized = Image.open(io.BytesIO(prepare_for_ocr(large)))
    assert max(resized.size) == WORKING_SIDE and resized.size == (800, 600)
    small = image_bytes(size=(300, 200))
    assert prepare_for_ocr(small) == small
    assert prepare_for_ocr(b"not an image") == b"not an image"


def test_retry_views_are_cheap_first_and_the_original_resolution_is_last():
    from app.media_worker.image import enhanced_variants

    views = [Image.open(io.BytesIO(blob)).size for blob in enhanced_variants(image_bytes(size=(1200, 900)))]
    assert len(views) == 4
    assert max(views[0]) < 800 and max(views[1]) < max(views[0]) and views[2] == (800, 600)
    assert views[3] == (1200, 900)  # the slowest view comes last
    # a very large photo is capped before it is ever used as a retry
    assert max(Image.open(io.BytesIO(enhanced_variants(image_bytes(size=(3000, 2000)))[-1])).size) == 1280
    # a photo already at working size has no separate "original" view
    assert len(enhanced_variants(image_bytes(size=(600, 400)))) == 3


def test_dev_capture_is_off_by_default_and_keeps_photo_and_diagnosis_when_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("GLICO_DEV_SAVE_IMAGE_DIR", raising=False)
    engine = _Engine(["106", "mg/dL"], ["106"])
    assert _post_image(engine, image_bytes(size=(240, 240)), "Q" * 24).status_code == 200
    assert list(tmp_path.iterdir()) == []

    monkeypatch.setenv("GLICO_DEV_SAVE_IMAGE_DIR", str(tmp_path))
    assert _post_image(_Engine(["106", "mg/dL"], ["106"]), image_bytes(size=(240, 240)), "R" * 24).status_code == 200
    saved = sorted(path.name for path in tmp_path.iterdir())
    assert len(saved) == 2 and saved[0].endswith(".json") and saved[1].endswith(".png")
    import json
    note = json.loads((tmp_path / saved[0]).read_text(encoding="utf-8"))
    assert note["assessment"]["candidate_value_mg_dl"] == 106 and note["passes"] == 1
