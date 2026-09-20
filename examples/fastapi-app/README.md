# FastAPI Demo Application

This is a sample FastAPI application demonstrating all pyoci integrations.

## Quick Start

### Build with pyoci (CLI)

```bash
cd examples/fastapi-app
# Base image auto-detected from pyproject.toml (requires-python: ">=3.11")
pyoci build --tag fastapi-demo:latest --include-deps

# Or with custom base image
pyoci build --tag fastapi-demo:latest --base-image python:3.12-slim --include-deps
```

### Build with Poetry Plugin

```bash
cd examples/fastapi-app
poetry install
poetry self add poetry-oci
poetry build-container --tag fastapi-demo:latest
```

### Build with Hatch Plugin

```bash
cd examples/fastapi-app
pip install hatch hatch-oci
hatch build  # Builds both wheel and container
```

### Deploy with Azure Developer CLI

Create `azure.yaml`:

```yaml
name: fastapi-demo

services:
  api:
    project: ./
    language: python
    host: containerapp
    hooks:
      prebuild:
        run: pip install pyoci
      build:
        run: |
          pyoci build \
            --tag ${SERVICE_IMAGE_NAME}:${SERVICE_IMAGE_TAG} \
            --include-deps \
            --push
```

Then deploy:

```bash
azd up
```

### CI/CD with GitHub Actions

Create `.github/workflows/build.yml`:

```yaml
name: Build Container

on:
  push:
    branches: [main]

jobs:
  build:
    uses: willena/pyoci/.github/workflows/pyoci.yml@main
    with:
      tag: ghcr.io/${{ github.repository }}/fastapi-demo:${{ github.sha }}
      context: ./examples/fastapi-app
      include-deps: true
      push: true
    permissions:
      contents: read
      packages: write
```

## Run Locally (Testing)

```bash
# Build the container
pyoci build --tag fastapi-demo:latest --include-deps

# Run with Docker (for testing only)
docker run -p 8000:8000 fastapi-demo:latest

# Or directly with Python
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit http://localhost:8000 for the app and http://localhost:8000/docs for API documentation.

## Configuration

This example includes configuration for all integrations:

- **pyoci CLI**: Uses `pyproject.toml` [project] section
- **Poetry plugin**: Uses `[tool.pyoci]` section
- **Hatch plugin**: Uses `[tool.hatch.build.hooks.pyoci]` section
- **GitHub Actions**: Example workflow provided above
- **Azure Developer CLI**: Example azure.yaml provided above

## Endpoints

- `GET /` - Welcome message
- `GET /health` - Health check
- `GET /info` - Application information
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Features Demonstrated

- ✅ **Base image auto-detection** - Python version detected from `requires-python` in pyproject.toml
- ✅ **Framework auto-detection** - FastAPI automatically configured with proper entrypoint
- ✅ **Entry point auto-detection** - Reads `[project.scripts]` from pyproject.toml
- ✅ **Dependency packaging** - Include pip packages with `--include-deps`
- ✅ **Environment variable configuration** - Custom env vars for production
- ✅ **OCI label metadata** - Maintainer, description, and custom labels
- ✅ **Multiple integration methods** - CLI, Poetry, Hatch, GitHub Actions, azd

## Learn More

- [Poetry Plugin Documentation](../../plugins/poetry-oci/)
- [Hatch Plugin Documentation](../../plugins/hatch-oci/)
- [GitHub Actions Documentation](../../docs/github-actions.md)
- [Azure Developer CLI Documentation](../../docs/azd-integration.md)
