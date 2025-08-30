# Unstable Fusion

Unstable Fusion is a web application that allows users to generate images from text prompts using Stable Diffusion models with PyTorch and stuff. It provides a React frontend and a FastAPI backend, all containerized with Docker for easy deployment. The main process is FastAPI, which hosts the static files built by React and handles POST API requests for image generation.

## Deploy

The app is containerized with Docker. You can build it with the following commands:

```bash
docker build -t unstable-fusion .
```

Then use the included `compose.yml` to run the app with:

```bash
docker compose -d compose.yml up
```

## REST API

The backend exposes a REST API endpoint at `/api/generate` that accepts POST requests with a JSON payload containing the text prompt and other parameters for image generation. The API processes the request, generates the image using the selected Stable Diffusion model, and returns the generated image in the response.

### Persistence & Queue

Jobs are stored in the jobs table with status fields. The worker thread polls DB for queued jobs, marks them processing, and runs the generator. On startup the app resets any processing jobs back to queued so they can be picked up again. If the app is restarted, processing jobs are moved back to queued on startup so they will be re-executed.

### Endpoints

- `POST /jobs` - enqueue image generation: body { "prompt": "...", "model": "supported_model", "width": 256, "height": 256 }
- `GET /jobs` - list user's jobs with optional status filter and pagination
- `GET /jobs/{id}` - job status and details
- `POST /jobs/{id}/cancel` - cancel queued job (best-effort)
- `GET /queue` - queue snapshot (queued count, processing count, next jobs)
- `GET /images` - list user's images with pagination and prompt_contains filter
- `GET /images/{id}` - image details
- `DELETE /images/{id}` - delete own image file + DB record
- `GET /images/{id}/download` - download file (own or admin)
- `POST /images/{id}/like` - like/unlike toggle for current user

## Frontend/Web Client

The frontend is statically built with React + Vite and provides a user-friendly interface for interacting with the backend API. It interfaces with all of the REST API endpoints. The frontend is served by FastAPI as static files.