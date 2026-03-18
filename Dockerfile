FROM python:3.12-slim AS backend

WORKDIR /app
COPY backend/pyproject.toml .
RUN pip install --no-cache-dir .

COPY backend/app/ app/
COPY backend/alembic/ alembic/
COPY backend/alembic.ini .
COPY backend/roles_config/ roles_config/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM node:22-alpine AS frontend-build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --frozen-lockfile || npm install

COPY frontend/ .
RUN npm run build


FROM node:22-alpine AS frontend

WORKDIR /app
COPY --from=frontend-build /app/.next ./.next
COPY --from=frontend-build /app/node_modules ./node_modules
COPY --from=frontend-build /app/package.json .
COPY --from=frontend-build /app/public ./public
COPY --from=frontend-build /app/next.config.js .

EXPOSE 3000
CMD ["npm", "start"]
