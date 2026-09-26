"""Hash perceptual de portadas (dHash de 16x16 = 256 bits) y comparación."""
from pathlib import Path

import numpy as np
from PIL import Image

HASH_BYTES = 32
_POPCOUNT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)


def dhash(image: Image.Image) -> bytes:
    gray = image.convert("L").resize((17, 16), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.int16)
    return np.packbits((pixels[:, 1:] > pixels[:, :-1]).ravel()).tobytes()


def dhash_variants(image: Image.Image) -> list[bytes]:
    """Hash de la imagen completa y de versiones sin borde: los escaneos suelen traer márgenes."""
    variants = [dhash(image)]
    for margin in (0.04, 0.08):
        dx, dy = round(image.width * margin), round(image.height * margin)
        variants.append(dhash(image.crop((dx, dy, image.width - dx, image.height - dy))))
    return variants


def dhash_bytes(data: bytes) -> bytes | None:
    """Hash de una imagen en memoria; None si los datos no son una imagen válida."""
    import io
    try:
        with Image.open(io.BytesIO(data)) as image:
            return dhash(image)
    except (OSError, ValueError):
        return None


def dhash_file(path: Path) -> list[bytes]:
    with Image.open(path) as image:
        return dhash_variants(image)


def distances(query: bytes, matrix: np.ndarray) -> np.ndarray:
    """Distancia de Hamming entre `query` y cada fila de `matrix` (N x 32, uint8)."""
    xor = np.bitwise_xor(matrix, np.frombuffer(query, dtype=np.uint8))
    return _POPCOUNT[xor].sum(axis=1, dtype=np.int32)


def similarity(variants: list[bytes], other: bytes) -> float:
    """Mejor similitud de las variantes con `other`: 1.0 = idénticas; ~0.5 = sin relación."""
    matrix = np.frombuffer(other, dtype=np.uint8).reshape(1, -1)
    return 1 - min(int(distances(v, matrix)[0]) for v in variants) / (HASH_BYTES * 8)
