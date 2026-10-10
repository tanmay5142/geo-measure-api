# Start from a small official Python image.
# Use the same major.minor version as on your computer (run: python --version).
FROM python:3.12-slim

# Don't create .pyc files, and print logs straight away.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Install libraries first. Docker remembers this step, so rebuilding after
# a code change is fast.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the application code (no tests, no virtual environment).
COPY app ./app

# Don't run as the root user. /code must be writable for the SQLite fallback.
RUN useradd --create-home appuser && chown appuser /code
USER appuser

EXPOSE 8000

# Docker checks this every 30 seconds to see if the app is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]