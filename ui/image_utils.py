"""Presentation-only image optimization; original Volume files stay unchanged."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps


def make_card_thumbnail(
    content: bytes, *, max_size: tuple[int, int] = (480, 320)
) -> bytes:
    """Encode a small JPEG cover for marketplace cards, preserving source on errors."""
    try:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                rgba = image.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = image.convert("RGB")

            output = BytesIO()
            rgb.save(output, format="JPEG", quality=78, optimize=True)
            return output.getvalue()
    except (OSError, ValueError):
        # Keep existing behavior if an uploaded photo can't be transformed.
        return content
