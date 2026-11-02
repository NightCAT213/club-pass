from io import BytesIO

import cv2
import numpy as np
import qrcode
from PIL import Image, UnidentifiedImageError
from qrcode.constants import ERROR_CORRECT_H

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000


class QRDecodeError(ValueError):
    pass


def create_qr_png(payload: str) -> bytes:
    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_H, box_size=12, border=4
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def decode_qr_image(data: bytes) -> str:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise QRDecodeError("Изображение слишком большое или пустое")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise QRDecodeError("Слишком большое разрешение изображения")
            image = np.asarray(source.convert("RGB"))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise QRDecodeError("Не удалось прочитать изображение") from exc

    detector = cv2.QRCodeDetector()
    decoded, _, _ = detector.detectAndDecode(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    if not decoded:
        raise QRDecodeError("QR-код не найден. Пришлите фото чётче или вставьте код текстом")
    return decoded.strip()
