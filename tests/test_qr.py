import pytest

from app.qr import QRDecodeError, create_qr_png, decode_qr_image
from app.security import make_pass, new_nonce


def test_generated_qr_can_be_decoded() -> None:
    payload = make_pass(new_nonce(), "example-testing-key" * 4)
    png = create_qr_png(payload)
    assert png.startswith(b"\x89PNG")
    assert decode_qr_image(png) == payload


def test_reject_invalid_image() -> None:
    with pytest.raises(QRDecodeError):
        decode_qr_image(b"not an image")
    with pytest.raises(QRDecodeError):
        decode_qr_image(b"a" * (8 * 1024 * 1024 + 1))
