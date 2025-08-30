# Build front end web client
FROM node:22.19.0-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ ./

RUN npm run build

# Run Python backend (POST API and serve frontend)
FROM python:3.12.3-slim

WORKDIR /app

# RUN apt-get update && apt-get install -y \
#     gcc \
#     g++ \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

RUN mkdir -p ./generated_images

EXPOSE 3001

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3001"]