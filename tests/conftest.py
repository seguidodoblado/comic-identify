import io
import random
import sqlite3

import pytest
from PIL import Image, ImageDraw

from comic_identify.gcd import GcdIndex, build_index


def make_cover(seed: int, size=(600, 900)) -> Image.Image:
    """Portada sintética: fondo degradado con formas y bloques de color aleatorios pero fijos."""
    rng = random.Random(seed)
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    top, bottom = [tuple(rng.randrange(256) for _ in range(3)) for _ in range(2)]
    for y in range(size[1]):
        t = y / size[1]
        draw.line([(0, y), (size[0], y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    for _ in range(12):
        x, y = rng.randrange(size[0] - 50), rng.randrange(size[1] - 50)
        w, h = rng.randrange(40, 300), rng.randrange(40, 300)
        draw.rectangle([x, y, x + w, y + h], fill=tuple(rng.randrange(256) for _ in range(3)))
    return image


def jpeg(image: Image.Image, quality=60) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


@pytest.fixture
def cover():
    return make_cover


@pytest.fixture
def dump(tmp_path):
    """Mini volcado con las tablas y columnas de GCD que usa el importador."""
    path = tmp_path / "gcd.db"
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE stddata_country (id INTEGER, code TEXT, name TEXT);
    CREATE TABLE stddata_language (id INTEGER, code TEXT, name TEXT);
    CREATE TABLE gcd_publisher (id INTEGER, name TEXT);
    CREATE TABLE gcd_brand (id INTEGER, name TEXT, deleted INTEGER);
    CREATE TABLE gcd_issue_brand_emblem (id INTEGER, issue_id INTEGER, brand_id INTEGER);
    CREATE TABLE gcd_series (id INTEGER, name TEXT, publisher_id INTEGER, country_id INTEGER,
        language_id INTEGER, year_began INTEGER, year_ended INTEGER, issue_count INTEGER, deleted INTEGER);
    CREATE TABLE gcd_issue (id INTEGER, series_id INTEGER, number TEXT, title TEXT, barcode TEXT,
        isbn TEXT, key_date TEXT, variant_of_id INTEGER, deleted INTEGER);
    INSERT INTO stddata_country VALUES (1, 'es', 'Spain'), (2, 'mx', 'Mexico'), (3, 'us', 'United States');
    INSERT INTO stddata_language VALUES (1, 'es', 'Spanish'), (2, 'en', 'English');
    INSERT INTO gcd_publisher VALUES (1, 'Panini España'), (2, 'Novedades'), (3, 'Marvel');
    INSERT INTO gcd_brand VALUES (1, 'Forum; Marvel Comics', 0), (2, 'Marca borrada', 1), (3, 'Panini Comics', 0);
    INSERT INTO gcd_issue_brand_emblem VALUES (1, 100, 1), (2, 100, 2), (3, 100, 3), (4, 103, 3), (5, 106, 1);
    INSERT INTO gcd_series VALUES
      (10, 'Spiderman', 1, 1, 1, 2006, NULL, 189, 0),
      (11, 'Los Cuatro Fantásticos', 1, 1, 1, 2006, 2010, 50, 0),
      (12, 'Spiderman', 2, 2, 1, 1980, 1990, 300, 0),
      (13, 'Amazing Spider-Man', 3, 3, 2, 1963, NULL, 900, 0),
      (14, 'Borrada', 1, 1, 1, 2000, 2001, 1, 1);
    INSERT INTO gcd_issue VALUES
      (100, 10, '12', 'Sombras', '977060120000000012', '', '2006-12-00', NULL, 0),
      (101, 10, '100', '', '', '', '2010-01-00', NULL, 0),
      (102, 10, '12', '', '', '', '2006-12-00', 100, 0),
      (103, 11, '7', '', '', '', '2007-01-00', NULL, 0),
      (104, 12, '12', '', '', '', '1981-01-00', NULL, 0),
      (105, 13, '12', '', '', '', '1964-01-00', NULL, 0),
      (106, 14, '1', '', '', '', '2000-01-00', NULL, 0),
      (107, 10, '13', '', '', '', '2007-01-00', NULL, 1);
    """)
    db.commit()
    db.close()
    return path


@pytest.fixture
def index(dump, tmp_path):
    target = tmp_path / "data" / "gcd_es.db"
    build_index(dump, target)
    return GcdIndex(target)
