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
