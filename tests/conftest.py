import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models # noqa: F401
from app.database import Base

DATA_DIR = Path(__file__).parent / "data"

MIXED_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Plot A</name>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.98,0 77.59,12.97,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
    <Placemark>
      <name>Road B</name>
      <LineString><coordinates>77.59,12.97,0 77.59,12.98,0</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Tower C</name>
      <Point><coordinates>77.595,12.975,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""


def make_shapefile_zip(folder: Path, include_prj=True, skip=()) -> Path:
    """Build a small zipped Shapefile with two polygons."""
    gdf = gpd.GeoDataFrame(
        {"name": ["Plot A", "Plot B"], "area_ha": [1.5, None]},
        geometry=[
            Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)]),
            Polygon([(77.61, 12.97), (77.62, 12.97), (77.62, 12.98), (77.61, 12.98)]),
        ],
        crs="EPSG:4326",
    )
    gdf.to_file(folder / "plots.shp")

    zip_path = folder / "plots.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for part in folder.glob("plots.*"):
            if part.suffix == ".zip" or part.suffix in skip:
                continue
            if part.suffix == ".prj" and not include_prj:
                continue
            zf.write(part, arcname=part.name)
    return zip_path


@pytest.fixture
def shapefile_zip(tmp_path):
    return make_shapefile_zip(tmp_path)


@pytest.fixture
def shapefile_zip_no_prj(tmp_path):
    return make_shapefile_zip(tmp_path, include_prj=False)


@pytest.fixture
def shapefile_zip_no_dbf(tmp_path):
    return make_shapefile_zip(tmp_path, skip=(".dbf",))


@pytest.fixture
def mixed_kml(tmp_path):
    path = tmp_path / "mixed.kml"
    path.write_text(MIXED_KML)
    return path


@pytest.fixture
def sample_kml():
    return DATA_DIR / "square.kml"

@pytest.fixture
def db_session():
    """A fresh, empty in-memory database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # keeps one shared in-memory database
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()