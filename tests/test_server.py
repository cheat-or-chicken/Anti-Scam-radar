import base64

import pytest

from script.server import decode_extension_payload


def payload(**overrides):
    value = {
        "context": {"url": "https://example.com", "text": "public page text"},
        "screenshot": base64.b64encode(b"\xff\xd8\xffjpeg").decode("ascii"),
    }
    value.update(overrides)
    return value


def test_extension_payload_accepts_bounded_jpeg_without_putting_it_in_context():
    context, screenshot = decode_extension_payload(payload())

    assert context.url == "https://example.com"
    assert screenshot.startswith(b"\xff\xd8\xff")
    assert "screenshot" not in context.model_dump()


@pytest.mark.parametrize("value", ["bad-base64", base64.b64encode(b"not an image").decode("ascii")])
def test_extension_payload_rejects_invalid_images(value):
    with pytest.raises(ValueError):
        decode_extension_payload(payload(screenshot=value))
