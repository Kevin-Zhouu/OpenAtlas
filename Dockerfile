FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && python -m playwright install --with-deps chromium
COPY openatlas ./openatlas
COPY builtins ./builtins
COPY --from=frontend /ui/dist ./frontend/dist
ENV OPENATLAS_DATA=/data OPENATLAS_SKILLS=/skills PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "openatlas.server"]
