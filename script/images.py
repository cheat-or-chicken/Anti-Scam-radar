"""Optional local image helpers; install uv sync --extra images. No image upload."""

from pathlib import Path


def _image(path: str):
    from PIL import Image

    if Path(path).stat().st_size > 10_000_000:
        raise ValueError("image exceeds 10 MB")
    image = Image.open(path)
    if image.width * image.height > 16_000_000:
        image.close()
        raise ValueError("image exceeds 16 megapixels")
    return image


def decode_qr(path: str) -> list[str]:
    import zxingcpp

    with _image(path) as image:
        return [r.text for r in zxingcpp.read_barcodes(image) if r.format == zxingcpp.BarcodeFormat.QRCode][
            :100
        ]


def ocr_image(path: str, language: str = "chi_tra+eng") -> str:
    import pytesseract

    with _image(path) as image:
        return pytesseract.image_to_string(image, lang=language, timeout=10)[:50000]
