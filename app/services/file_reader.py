import json
import zipfile
from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry.base import BaseGeometry

from app.config import MAX_UNZIPPED_BYTES


class InvalidFileError(Exception):
    """The uploaded file can't be read or is not supported."""


@dataclass
class ParsedFeature:
    index: int
    geometry_type: str
    geometry: BaseGeometry | None
    properties: dict


@dataclass
class ParsedFile:
    crs: str
    features: list[ParsedFeature]


def read_geo_file(path: str, filename: str) -> ParsedFile:
    """Read a .kml or a zipped Shapefile from disk."""
    name = filename.lower()
    if name.endswith(".zip"):
        gdf = _read_shapefile_zip(path)
    elif name.endswith(".kml"):
        gdf = _read_kml(path)
    else:
        raise InvalidFileError(
            "Unsupported file type. Upload a .zip (Shapefile) or a .kml file."
        )
    return _to_parsed_file(gdf)


def _find_shapefile_in_zip(path: str) -> str:
    if not zipfile.is_zipfile(path):
        raise InvalidFileError("The file is not a valid zip archive.")

    with zipfile.ZipFile(path) as zf:
        infos = [
            i for i in zf.infolist()
            if not i.is_dir() and not i.filename.startswith("__MACOSX/")
        ]
        if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
            raise InvalidFileError("The zip file is too large when unpacked.")
        names = [i.filename for i in infos]

    shp_files = [n for n in names if n.lower().endswith(".shp")]
    if not shp_files:
        raise InvalidFileError("No .shp file found inside the zip.")
    if len(shp_files) > 1:
        raise InvalidFileError("The zip has more than one Shapefile. Upload one at a time.")

    shp = shp_files[0]
    stem = shp[:-4].lower()
    lowered = {n.lower() for n in names}
    missing = [ext for ext in (".shx", ".dbf") if stem + ext not in lowered]
    if missing:
        raise InvalidFileError(f"The Shapefile is missing required part(s): {', '.join(missing)}")
    return shp


def _read_shapefile_zip(path: str) -> gpd.GeoDataFrame:
    shp = _find_shapefile_in_zip(path)
    try:
        return gpd.read_file(f"zip://{path}!{shp}")
    except Exception as exc:  # the libraries raise many different error types
        raise InvalidFileError(f"Could not read the Shapefile: {exc}") from exc


def _read_kml(path: str) -> gpd.GeoDataFrame:
    try:
        # A KML file can have several folders. Each folder is a "layer".
        layer_names = pyogrio.list_layers(path)[:, 0]
        frames = [gpd.read_file(path, layer=name) for name in layer_names]
    except Exception as exc:
        raise InvalidFileError(f"Could not read the KML file: {exc}") from exc

    frames = [f for f in frames if not f.empty]
    if not frames:
        raise InvalidFileError("The KML file has no features.")
    return pd.concat(frames, ignore_index=True)


def _properties_as_dicts(gdf: gpd.GeoDataFrame) -> list[dict]:
    props = gdf.drop(columns=gdf.geometry.name)
    if props.shape[1] == 0:
        return [{} for _ in range(len(gdf))]
    # to_json turns NaN into null and dates into text, so the result is JSON-safe
    return json.loads(props.to_json(orient="records", date_format="iso"))


def _to_parsed_file(gdf: gpd.GeoDataFrame) -> ParsedFile:
    if gdf.empty:
        raise InvalidFileError("The file has no features.")
    if gdf.crs is None:
        raise InvalidFileError(
            "The file has no CRS information (a Shapefile needs a .prj file), "
            "so measurements can't be calculated safely."
        )

    epsg = gdf.crs.to_epsg()
    crs_label = f"EPSG:{epsg}" if epsg else gdf.crs.name

    features = []
    for i, (geom, props) in enumerate(zip(gdf.geometry, _properties_as_dicts(gdf))):
        features.append(
            ParsedFeature(
                index=i,
                geometry_type=geom.geom_type if geom is not None else "None",
                geometry=geom,
                properties=props,
            )
        )
    return ParsedFile(crs=crs_label, features=features)