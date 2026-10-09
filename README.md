# Geospatial File Measurement API

Backend service that accepts a Shapefile (.zip) or KML file, extracts the features, and returns area/length measurements.


## Design Decisions
 CRS Handling
### Choosing the projected CRS

Latitude/longitude values are in degrees, so area and length can't be
calculated from them directly. For each feature, the service:

1. Converts the geometry to EPSG:4326 (if it is not already in it).
2. Finds the feature's center point (centroid).
3. Picks the UTM zone for that point (EPSG:326xx for the northern
   hemisphere, EPSG:327xx for the southern).
4. Projects the geometry into that zone and measures it in meters.

**Why UTM per feature:** UTM is very accurate inside a single zone, it is
simple to explain, and picking the zone per feature means a file with
shapes in different places still gets sensible results.

**Alternatives I considered:**
- One UTM zone for the whole file: simpler, but wrong for files that
  cover several zones.
- An equal-area projection (such as Albers): good for large areas, but
  it needs a good choice of parameters for each region.
- Geodesic calculation with `pyproj.Geod`: the most accurate, because it
  measures on the earth's curved surface, but it is a different approach
  from the "project then measure" flow in the task.

### Database
- SQLAlchemy with SQLite by default. Set `DATABASE_URL` to use Postgres
  (or any other SQLAlchemy-supported database) with no code changes.
- Measurements are calculated once, at upload time, and stored in the
  database. Reading them later is a simple query and needs no
  reprocessing.
- One row per feature. A failed feature stores its own error message, so
  one bad feature never fails the whole file.
- Feature properties are stored as JSON because attribute names differ
  from file to file.
- Geometry is stored as GeoJSON in the file's original CRS; the CRS is
  stored next to it.
- Tables are created on startup for simplicity.

### Known limitation

UTM zones are 6 degrees wide. A very large feature that crosses several
zones (for example, a long pipeline or a state boundary) is measured
using only the zone of its center point, so the result is slightly less
accurate. For typical survey-sized features the error is small.

## Future Scope
- Improve accuracy for very large features that cross UTM zones, by using
  an equal-area projection or geodesic measurement (`pyproj.Geod`) when a
  feature's bounding box spans more than one zone.
- support zips with several Shapefiles, and try to repair a missing .shx
- use Alembic for migrations, and use PostgreSQL with PostGIS for spatial queries and indexes



Result
For a 1km square near Bengaluru, the UTM result differs from the geodesic calculation by 0.1161%.
UTM area:      1201683.92
Geodesic area: 1200289.84
Difference %:  0.1161

### File handling

- Supported uploads: a `.zip` containing one Shapefile, or a `.kml` file.
- A Shapefile without a `.prj` (no CRS) is rejected. Guessing the CRS
  could silently give wrong measurements, so a clear error is safer.
- A zip with more than one Shapefile is rejected (one upload = one dataset).
- The zip is read in place and never unpacked to disk, which avoids
  "zip slip" attacks. The total unpacked size is also limited to protect
  against zip bombs.
- For KML files, all layers (folders) are read and combined.