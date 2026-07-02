FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Production run: no --reload (that's a dev-only feature — watches the FS and
# widens the surface). For hot-reload dev, run uvicorn from the host venv per
# INSTALL.md, or add a docker-compose.override.yml. See SECURITY_REVIEW.md M-1.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
