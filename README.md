# Unstable Fusion

Unstable Fusion is a relatively simple API that allows users to generate images from text prompts using a variety of pre-selected Stable Diffusion models. It uses FastAPI for the API and is RESTful. It also includes a web client built with React for easy interaction with the API.

## Context

This project was built for CAB432 Cloud Computing at QUT, where I explored the deployment of EC2 instances with heavy CPU load. The goal was to use older models that could run on CPU-only instances, as GPU instances were not feasible within the project constraints.

## Deployment

The app is containerized with Docker and deployed with Docker Compose as a single stack that includes MariaDB. Just run the following command to start the app:

```bash
docker compose compose.yml up
```

If needed you can manually build it with the following commands:

```bash
docker build -t unstable-fusion:manual .
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

## Generative AI Disclaimer

A portion of the code in this project was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

## References

This code was adapted from the following articles:
- https://medium.com/@nttp/text-to-image-on-cpu-only-hardware-bd98f291dead
- https://medium.com/latinxinai/text-to-image-with-stable-diffusion-4df16da2cfd5

The following models are downloaded and used by the Python app:
- https://huggingface.co/stabilityai/sd-turbo
- https://huggingface.co/CompVis/stable-diffusion-v1-4
- https://huggingface.co/Stable-Diffusion-v1-5/stable-diffusion-v1-5
