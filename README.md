# UnstableFusion

Unstable Fusion is a Stable Diffusion API that allows users to generate images from text prompts using pre-selected models. It features a FastAPI backend and React frontend with comprehensive AWS integrations.

## Quick Start

### Option 1: Docker (Recommended)
```bash
# Start the application
docker compose up

# Access the application
# Frontend: http://localhost:3001
# API docs: http://localhost:3001/docs
```

**Default Users:**
- Username: `admin`, Password: `admin` (Admin access)
- Username: `demo`, Password: `demo` (Standard user)

### Option 2: Full AWS Deployment
```bash
# Deploy infrastructure and configure AWS services
./deploy.sh deploy

# Start the application with Docker
./deploy.sh docker
```

## Documentation

📖 **Complete documentation is available in [`DEPLOYMENT_GUIDE.md`](./DEPLOYMENT_GUIDE.md)**

This comprehensive guide covers:
- Basic and advanced deployment options
- AWS services integration (Parameter Store, Secrets Manager, Cognito, etc.)
- Architecture overview and API documentation
- Configuration management
- Troubleshooting and performance tuning

## Features

### Core Application
- **AI Image Generation**: Multiple Stable Diffusion models
- **User Authentication**: JWT-based with role management
- **Job Queue System**: Background processing with status tracking
- **Image Gallery**: With likes, filtering, and pagination
- **Real-time Updates**: WebSocket/SSE progress tracking

### AWS Integrations (16 marks total)
- ✅ **Parameter Store** (2 marks) - Configuration management
- ✅ **Secrets Manager** (2 marks) - Secure credential storage
- ✅ **Cognito Authentication** (9 marks) - Full auth with MFA, groups, federated login
- ✅ **Stateless Architecture** (3 marks) - Horizontal scaling support
- ✅ **Persistent Connections** (2 marks) - Graceful WebSocket handling

### Advanced Features
- **Stateless Design**: Horizontal scaling with DynamoDB journaling
- **Session Management**: Redis-based distributed sessions
- **Connection Resilience**: Automatic reconnection with fallback
- **Load Balancer Ready**: Health checks and scaling support

## Project Structure

```
unstablefusion/
├── DEPLOYMENT_GUIDE.md      # 📖 Complete documentation
├── deploy.sh               # 🚀 Unified deployment script
├── app.py                  # FastAPI application
├── compose.yml             # Docker deployment
├── frontend/               # React TypeScript frontend
├── terraform/              # Infrastructure as Code
├── routers/                # API route modules
└── *_service.py           # AWS service integrations
```

## Deployment Commands

The unified `deploy.sh` script handles all deployment scenarios:

```bash
# Full deployment
./deploy.sh deploy

# Infrastructure only
./deploy.sh infrastructure

# Update configuration
./deploy.sh config

# Test connectivity
./deploy.sh test

# Show outputs
./deploy.sh outputs

# Docker deployment
./deploy.sh docker

# Clean up
./deploy.sh clean

# Help
./deploy.sh help
```

## Supported Models

- `CompVis/stable-diffusion-v1-4` (Default)
- `stabilityai/sd-turbo` 
- `stable-diffusion-v1-5/stable-diffusion-v1-5`

## Requirements

- Docker & Docker Compose
- AWS CLI (for AWS features)
- Terraform (for infrastructure)
- Python 3.12+ (for local development)
- Node.js 18+ (for frontend development)

## Support

For detailed setup instructions, troubleshooting, and architecture information, see the [**DEPLOYMENT_GUIDE.md**](./DEPLOYMENT_GUIDE.md).

---

*This project demonstrates cloud-native application architecture with comprehensive AWS integrations for a university cloud computing course.*