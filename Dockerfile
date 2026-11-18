FROM node:22-bookworm-slim AS web
WORKDIR /build/library-seat-web
COPY library-seat-web/package*.json ./
RUN npm ci
COPY library-seat-web/ ./
ENV VITE_RESERVATION_API_URL=/api
ENV VITE_API_ROLE=user
RUN npm run build

FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KOREA_DB_PATH=/var/data/library.db \
    KOREA_CLOCK_ENABLED=1
COPY api/requirements/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY api/ /app/api/
COPY schema.sql seed.sql /app/
COPY deploy/ /app/deploy/
COPY --from=web /build/library-seat-web/dist /app/library-seat-web/dist
EXPOSE 8000
CMD ["python", "-m", "deploy.start"]
