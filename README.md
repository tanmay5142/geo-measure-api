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


### Docker

- The image uses `python:3.12-slim`. The geospatial libraries are
  installed from prebuilt wheels that include GDAL, PROJ and GEOS, so no
  system packages are needed.
- Dependencies are installed before the code is copied, so rebuilds after
  a code change are fast.
- The container runs as a non-root user and has a health check on `/health`.
- `docker-compose.yml` starts PostgreSQL and waits for it to be healthy
  before starting the API.


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

the server receives the whole upload before our size check runs. In production, a reverse proxy such as nginx should also set a maximum body size

## Future Scope
- Improve accuracy for very large features that cross UTM zones, by using
  an equal-area projection or geodesic measurement (`pyproj.Geod`) when a
  feature's bounding box spans more than one zone.
- support zips with several Shapefiles, and try to repair a missing .shx
- use Alembic for migrations, and use PostgreSQL with PostGIS for spatial queries and indexes

- A multi-stage docker build, separate dev and productionnrequirements, running Alembic migrations on startup, and running several workers in production.

- Background processing with Celery or RQ (with Redis) for very large
  files. The `status` field is already in place for this.
- List and delete endpoints for uploaded files.
- Authentication, so each user only sees their own files.
- Database migrations with Alembic.
- PostgreSQL with PostGIS for spatial queries.
- Better accuracy for features that cross UTM zones (equal-area
  projection or geodesic measurement).
- Support zips with several Shapefiles.



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

### Request processing

- Files are processed synchronously, inside the upload request. This keeps
  the system simple and works well for the 50 MB upload limit. Endpoints
  are plain `def` functions, so FastAPI runs them in a worker thread and
  one slow upload doesn't block other requests.
- For very large files, processing would move to a background worker
  (Celery or RQ with Redis). The `status` field (PROCESSING / COMPLETED /
  FAILED) is already in place, so the API would not need to change much.

### Error handling

- A file that can't be read is saved with status FAILED and the reason,
  and the API answers 422 with the file id and the reason.
- A single bad feature (empty, invalid or unsupported geometry) gets its
  own error message. The rest of the file is still processed and the file
  is COMPLETED.
- Measurements are paged (`limit`, `offset`), because a file may contain
  thousands of features. The summary always counts the whole file.
- The 50 MB upload limit is checked while reading the upload. In
  production, a reverse proxy should also limit the request body size.

### API section
#	README section	What goes in it
1	Title and short description	What the service does
2	Setup	Install and run (Step 1)
3	API	Endpoints, status codes table, example requests and responses (this question)
4	Architecture	Folder structure, file-processing flow, measurement flow, CRS handling
5	Design Decisions	CRS choice and limit (Step 2), file handling (Step 4), database (Step 5), request processing and error handling (Step 6)
6	Testing	How to run pytest
7	Learning	What you learned
8	Future Scope	Everything you listed along the way, including Celery/RQ, delete and list endpoints, and authentication

## API

Interactive docs are available at http://127.0.0.1:8000/docs while the
server is running.

### 1. Upload a file

`POST /api/files/`

Accepts a `.kml` file or a `.zip` containing one Shapefile. The file is
processed right away.

```bash
curl -X POST http://127.0.0.1:8000/api/files/ -F "file=@survey.kml"
```

On Windows PowerShell, use `curl.exe` instead of `curl`.

Response `201 Created`:

```json
{
  "id": "870fc184-2632-45e7-b53a-a66da1f50c2b",
  "filename": "survey.kml",
  "feature_count": 1,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-09T10:15:30.123456Z"
}
```

### 2. Get file information

`GET /api/files/{id}/`

```bash
curl http://127.0.0.1:8000/api/files/870fc184-2632-45e7-b53a-a66da1f50c2b/
```

Returns the same JSON as the upload response.

### 3. Get measurements

`GET /api/files/{id}/measurements/`

Optional query parameters: `limit` (default 1000, max 5000) and `offset`
(default 0), for paging through large files.

```bash
curl "http://127.0.0.1:8000/api/files/870fc184-2632-45e7-b53a-a66da1f50c2b/measurements/"
```

Response `200 OK` (properties shortened here):

```json
{
  "file_id": "870fc184-2632-45e7-b53a-a66da1f50c2b",
  "crs": "EPSG:4326",
  "feature_count": 1,
  "limit": 1000,
  "offset": 0,
  "summary": {"measured": 1, "no_measurement": 0, "errors": 0},
  "features": [
    {
      "index": 0,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[77.59, 12.97, 0], [77.6, 12.97, 0], [77.6, 12.98, 0],
                         [77.59, 12.98, 0], [77.59, 12.97, 0]]]
      },
      "crs": "EPSG:4326",
      "properties": {"Name": "Test Square", "description": null},
      "measurement": {
        "type": "area",
        "value": 1201683.9190970361,
        "unit": "m2",
        "crs_used": "EPSG:32643"
      },
      "error": null
    }
  ]
}
```

- `measurement` is `null` for points (no measurement is needed) and for
  features that failed.
- A failed feature has an `error` message. The other features in the
  file are still measured.
- `summary` counts the whole file, even when `limit` and `offset` show
  only some of the features.

### Error responses

A file that can't be read (here, a fake zip) returns `422`:

```json
{
  "detail": "The file is not a valid zip archive.",
  "id": "4c1d9a52-0b3e-4f7a-9d61-2e8b7a5c3f10",
  "status": "FAILED"
}
```

Other errors return `{"detail": "..."}`, for example:

```json
{"detail": "File not found."}
```

### Status codes

| Situation | Code |
|---|---|
| Success | `201` |
| Wrong file extension or no file name | `400` |
| File too large (over 50 MB) | `413` |
| File can't be read (bad zip, no CRS, and so on) | `422` |
| Unknown file id | `404` |
| Measurements asked for a file that is not `COMPLETED` | `409` |
| Unexpected server error | `500` |



## Testing

Install the requirements, then run from the project root:

```bash
pytest -v
```

The tests use an in-memory SQLite database, so the real `geo.db` is
never touched. Each test starts with a clean database.

| File | What it covers |
|---|---|
| `tests/test_crs.py` | UTM zone selection and conversion to EPSG:4326 |
| `tests/test_measurement.py` | Area and length, compared with geodesic results; errors for bad geometry |
| `tests/test_file_reader.py` | Reading KML and zipped Shapefiles; rejecting bad files |
| `tests/test_models.py` | Database tables, defaults, ordering and cascade delete |
| `tests/test_api.py` | The full API: upload, file info, measurements, paging, validation, error cases and cleanup |

Important cases tested: a bad feature doesn't stop the rest of the file
(both for invalid geometry and for an unexpected crash while measuring),
a file with no CRS is rejected, and temporary files are always deleted.



## Setup

### Requirements

- Python 3.11 or newer (3.12 recommended)
- Docker (optional, for the PostgreSQL setup)

### Run locally (SQLite)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000 and the interactive docs are at
http://127.0.0.1:8000/docs. By default it stores data in a local
`geo.db` SQLite file.

### Run with Docker (PostgreSQL)

```bash
docker compose up --build
```

This starts the API and a PostgreSQL database. Data is kept in a Docker
volume. Stop with `docker compose down` (add `-v` to erase the data).

### Configuration

| Setting | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./geo.db` | Any SQLAlchemy database URL |

The upload limits (50 MB upload, 200 MB unpacked) are constants in
`app/config.py`. The passwords in `docker-compose.yml` are for local use
only.