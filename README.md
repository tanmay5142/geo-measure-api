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

### Known limitation

UTM zones are 6 degrees wide. A very large feature that crosses several
zones (for example, a long pipeline or a state boundary) is measured
using only the zone of its center point, so the result is slightly less
accurate. For typical survey-sized features the error is small.

## Future Scope
- Improve accuracy for very large features that cross UTM zones, by using
  an equal-area projection or geodesic measurement (`pyproj.Geod`) when a
  feature's bounding box spans more than one zone.