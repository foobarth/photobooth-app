import io
import logging
from pathlib import Path
from typing import overload

import piexif

from photobooth.services.config.groups.cameras import Orientation

logger = logging.getLogger(__name__)

_TYPE_BYTE = 1
_TYPE_ASCII = 2
_TYPE_SHORT = 3
_TYPE_LONG = 4
_TYPE_RATIONAL = 5
_TYPE_SBYTE = 6
_TYPE_UNDEFINED = 7
_TYPE_SLONG = 9
_TYPE_SRATIONAL = 10

_IFD_TAG_TYPES = {}
for _ifd_name in ("0th", "Exif", "GPS", "1st"):
    _IFD_TAG_TYPES[_ifd_name] = {
        tag_id: info["type"] for tag_id, info in piexif.TAGS.get(_ifd_name, {}).items()
    }

_TYPE_COERCIONS = {
    _TYPE_ASCII: (bytes, lambda v: str(v).encode("ascii") if not isinstance(v, bytes) else v),
    _TYPE_BYTE: (int, lambda v: v if isinstance(v, int) else int(v)),
    _TYPE_SHORT: (int, lambda v: v if isinstance(v, int) else int(v)),
    _TYPE_LONG: (int, lambda v: v if isinstance(v, int) else int(v)),
    _TYPE_SBYTE: (int, lambda v: v if isinstance(v, int) else int(v)),
    _TYPE_SLONG: (int, lambda v: v if isinstance(v, int) else int(v)),
}


def _sanitize_exif_types(exif_dict: dict) -> dict:
    """Coerce EXIF tag values to types piexif.dump() expects.

    Some webcams (e.g. Logitech Brio) write EXIF tags with incorrect types,
    e.g. tag 305 (Software) as int instead of bytes. piexif.dump() validates
    types strictly and raises on mismatch.
    """
    for ifd_name in ("0th", "Exif", "GPS", "1st"):
        if ifd_name not in exif_dict or not isinstance(exif_dict[ifd_name], dict):
            continue
        ifd = exif_dict[ifd_name]
        tag_types = _IFD_TAG_TYPES.get(ifd_name, {})

        for tag_id in list(ifd.keys()):
            expected_type = tag_types.get(tag_id)
            if expected_type is None:
                continue

            coercion = _TYPE_COERCIONS.get(expected_type)
            if coercion is None:
                continue

            accepted_types, converter = coercion
            value = ifd[tag_id]
            if not isinstance(value, accepted_types):
                try:
                    ifd[tag_id] = converter(value)
                    logger.debug(f"exif type coercion: tag {tag_id} in {ifd_name} IFD: {type(value).__name__} -> {type(ifd[tag_id]).__name__}")
                except Exception:
                    logger.warning(f"exif type coercion failed: tag {tag_id} in {ifd_name} IFD has type {type(value).__name__}, expected {accepted_types}. Removing tag.")
                    del ifd[tag_id]

    return exif_dict


@overload
def set_exif_orientation(jpeg_image: Path, orientation_choice) -> Path:
    pass


@overload
def set_exif_orientation(jpeg_image: bytes, orientation_choice) -> bytes:
    pass


def set_exif_orientation(jpeg_image: Path | bytes | bytearray, orientation_choice: Orientation) -> Path | bytes:
    """inserts updated orientation flag in given filepath.
    ref https://sirv.com/help/articles/rotate-photos-to-be-upright/

    Args:
        jpeg_image (Path|bytes): jpeg to modify
        orientation_choice (Literal): Orientierung (1=0°, 3=180°, 5=90°, 7=270°)
    """

    def _get_updated_exif_bytes(maybe_image, orientation_choice: Orientation):
        assert isinstance(orientation_choice, str)

        orientation = int(orientation_choice[0])
        if 1 < orientation > 8:
            raise ValueError(f"invalid orientation choice {orientation_choice} results in invalid value: {orientation}.")

        exif_dict = piexif.load(maybe_image)
        exif_dict["0th"][piexif.ImageIFD.Orientation] = orientation
        _sanitize_exif_types(exif_dict)

        return piexif.dump(exif_dict)

    if isinstance(jpeg_image, Path):
        # File case: update in place
        piexif.insert(_get_updated_exif_bytes(str(jpeg_image), orientation_choice), str(jpeg_image))
        return jpeg_image
    if isinstance(jpeg_image, (bytes, bytearray)):
        # Bytes case: return new data
        output = io.BytesIO()
        piexif.insert(_get_updated_exif_bytes(jpeg_image, orientation_choice), jpeg_image, output)
        return output.getvalue()

    raise TypeError(f"Unsupported jpeg_image type: {type(jpeg_image)}")
