# Unstable Fusion

Unstable Fusion is a relatively simple API that allows users to generate images from text prompts using a variety of pre-selected Stable Diffusion models. It uses FastAPI for the API and is RESTful. It also includes a web client built with React for easy interaction with the API.

## Context

This project was built for CAB432 Cloud Computing at QUT, where I explored the deployment of EC2 instances with heavy CPU load. The goal was to use older models that could run on CPU-only instances, as GPU instances were not feasible within the project constraints.

## Deployment

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

The frontend is statically built with TypeScript + React + Vite and provides a user-friendly interface for interacting with the backend API. It interfaces with all of the REST API endpoints. The frontend is served by FastAPI as static files built during the Docker build.
