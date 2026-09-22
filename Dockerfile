# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
RUN npm ci && npm run build

# ---------- 阶段 2：后端运行时 ----------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
