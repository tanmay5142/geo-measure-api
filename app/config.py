import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///geo.db")


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  #used by the upload endpoints
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024  #protects against zip bombs