# Build frontend web client
FROM node:latest AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ ./

RUN npm run build

# Run Python backend and serve
FROM python:latest

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY .env ./
COPY *.py ./
COPY routers/ ./routers/

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create directories (may not be needed if using S3)
RUN mkdir -p ./generated_images

# Run database migration on startup if needed
COPY migrate_db.py ./

EXPOSE 3001

# Start the application directly (migrations should be run manually during setup)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]