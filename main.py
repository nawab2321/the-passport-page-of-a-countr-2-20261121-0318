"""Emit the Republic of Varrenn passport spread for the make.fun runner."""

from pathlib import Path
from struct import unpack_from

ARTWORK = Path(__file__).resolve().parent / "artwork" / "varrenn.png"
OUTPUT = Path("/output/entry.png")
MAX_BYTES = 1_048_576
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"


def main() -> None:
    image = ARTWORK.read_bytes()
    if len(image) < 24 or len(image) > MAX_BYTES or not image.startswith(PNG_HEADER):
        raise ValueError("The stored artwork must be a PNG within the make.fun size limit")
    if unpack_from(">II", image, 16) != (1024, 1024):
        raise ValueError("The stored artwork must be exactly 1024 × 1024")
    OUTPUT.write_bytes(image)


if __name__ == "__main__":
    main()
