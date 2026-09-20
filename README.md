# 🐍 pyoci

> **Build OCI container images from Python projects — Docker-free, pure Python**

A native, Docker-free container image builder for Python, inspired by .NET's `PublishContainer`. Create production-ready OCI images using pure Python, without Dockerfiles or Docker daemon.

---

## 🎯 Why This Exists

Today, containerizing Python applications requires:
- Writing and maintaining Dockerfiles
- Installing Docker Desktop or Docker Engine
- Understanding Docker-specific concepts and commands
- Managing multi-stage builds for dependencies

**pyoci** provides a simpler path:

```bash
pyoci build
```

That's it. No Dockerfile. No Docker daemon. Just pure Python creating OCI-compliant container images.
This mirrors the elegant developer experience that .NET provides with its SDK's native container publishing — but for Python.

---

## 🚀 Quick Start

### Installation

```bash
# Use pip or your favourite dependency tool
pip install pyoci
```

### Locally build the Workspace Packages

```bash
# Inspect the workspace members
uv workspace list

# Build every publishable package into ./dist
uv build --all-packages --out-dir dist

# Publish all built artifacts to TestPyPI
uv publish --index testpypi dist/*

# Publish all built artifacts to PyPI
uv publish --index pypi dist/*
```

### Build Your First Image

```bash
# Simple build (auto-detects Python version and base image)
pyoci build --tag myapp:latest

# Build with custom base image and dependencies
pyoci build \
  --tag myapp:v1 \
  --base-image python:3.12-slim \
  --include-deps

# Build FastAPI app (auto-detected, entrypoint configured)
pyoci build --tag api:latest --context ./my-fastapi-app

# Build with SBOM for security compliance
pyoci build \
  --tag myapp:v1 \
  --sbom spdx \
  --config pyoci.toml

# Build and push to registry
pyoci build --tag ghcr.io/user/myapp:v1 --push

# Build for different platform (e.g., amd64 from ARM Mac)
pyoci build --tag myapp:latest --platform linux/amd64

# Dry-run to preview (verbose mode)
pyoci build --tag test:latest --dry-run --verbose

# Remove old output before rebuilding into the same directory
pyoci build --tag test:latest --clean-output-dir
```

### Output

Creates a complete OCI image layout at `dist/image/`:
```
dist/image/
  ├── index.json                  # OCI index (manifest list)
  ├── oci-layout                  # Version marker
  ├── blobs/sha256/
  │   ├── <manifest-digest>       # Manifest blob
  │   ├── <config-digest>         # Config blob
  │   └── <layer-digest>          # Application layer (tar)
  └── refs/tags/
      └── <tag-name>              # Tag reference
```

### Testing Locally

**Important**: `PyOCI` creates OCI-compliant image layouts, not Docker-specific images. To test locally:

#### Option 1: Use Skopeo (Recommended)

```bash
# Copy OCI layout to Docker
skopeo copy oci:dist/image docker-daemon:myapp:latest
docker run -p 8000:8000 myapp:latest
```

#### Option 2: Use Podman (Native OCI Support)

```bash
# Run directly from OCI layout
podman run --rm -p 8000:8000 oci:dist/image:myapp
```

#### Option 3: Push to Registry (Production)

```bash
# Build and push (works with any container runtime)
pyoci build --tag ghcr.io/user/myapp:latest --push

# Pull and run with Docker or Podman
docker pull ghcr.io/user/myapp:latest
docker run -p 8000:8000 ghcr.io/user/myapp:latest
```

**See [Local Development Guide](docs/local-development.md) for detailed testing instructions.**

---

## ✨ Features

### Current Capabilities

**Foundation & Registry**:
- ✅ **Zero Docker dependencies** — Pure Python implementation
- ✅ **Auto-detects Python project structure** — Finds `src/`, `app/`, entry points
- ✅ **Infers entrypoints** — Reads `pyproject.toml` scripts, falls back to `python -m`
- ✅ **Creates OCI-compliant images** — Complete OCI image layout v1
- ✅ **Command-line interface** — Simple `pyoci build` workflow
- ✅ **Programmatic API** — Use as a library in your tools
- ✅ **Registry push support** — Push to GHCR, ACR, Docker Hub via Registry v2 API
- ✅ **Blob existence checks** — Skip uploading layers that already exist
- ✅ **Progress reporting** — Visual feedback during push operations
- ✅ **Multi-provider authentication** — GitHub tokens, Docker config, Azure CLI, env vars
- ✅ **OAuth2 token exchange** — Automatic bearer token flow with Www-Authenticate
- ✅ **Credential auto-discovery** — Tries multiple auth sources automatically
- ✅ **Layer caching** — Content-addressable storage with LRU eviction
- ✅ **Cache invalidation** — Detects file changes via mtime + size checks
- ✅ **Fast incremental builds** — Reuses unchanged layers from cache

**Base Images & Dependencies**:
- ✅ **Smart base image detection** — Auto-selects Python base image from `requires-python` in pyproject.toml
- ✅ **Base image support** — Build on top of `python:3.11-slim`, `python:3.12-slim`, distroless, etc.
- ✅ **Layer merging** — Combines base image layers with application layers
- ✅ **Config inheritance** — Merges env vars, labels, working dir from base images
- ✅ **Dependency packaging** — Include pip packages from venv or requirements.txt
- ✅ **Distroless detection** — Auto-handles shell-less base images

**Production Features**:
- ✅ **Framework auto-detection** — FastAPI, Flask, Django automatically configured
- ✅ **Configuration files** — Load settings from `pyoci.toml`
- ✅ **SBOM generation** — Create SPDX 2.3 or CycloneDX 1.4 security manifests
- ✅ **Reproducible builds** — Deterministic layer creation with fixed timestamps
- ✅ **Cross-platform builds** — Build linux/amd64 from ARM, linux/arm64 from x86, etc.
- ✅ **Platform auto-selection** — Pulls correct architecture variant from multi-arch base images
- ✅ **Verbose logging** — Detailed build progress with `--verbose`
- ✅ **Dry-run mode** — Preview builds with `--dry-run`

**Toolchain integrations**:
- ✅ Hatch (using `hatch-oci` )
- ✅ Poetry (using `poetry-oci`)

---

## 📖 How It Works

### Architecture Overview

```
cli.py (entry point)
  └─> builder.py (orchestrates build)
       ├─> config.py (build configuration)
       ├─> project.py (Python project introspection)
       ├─> oci.py (OCI spec structs)
       └─> fs_utils.py (file system helpers)
```

### Build Process

1. **Project Discovery** — Reads `pyproject.toml`, detects entry points and structure
2. **File Collection** — Gathers source files based on auto-detected or configured paths
3. **Layer Creation** — Packs files into tar archive with correct `/app/` prefixes
4. **OCI Generation** — Creates manifest and config JSON per OCI Image Spec v1
5. **Output** — Writes the OCI image layout to disk and optionally pushes it when `--push` is set

---

## 🧩 Programmatic Usage

Use as a library in your Python tools:

```python
from pyoci.config import BuildConfig
from pyoci.builder import ImageBuilder

config = BuildConfig(
    tag="myapp:latest",
    context_dir="/path/to/app",
    env={"ENV": "production"},
    include_paths=["src/", "pyproject.toml"],
)

builder = ImageBuilder(config)
builder.build()  # Creates dist/image/
```

Perfect for integration with:
- **Azure Developer CLI (azd)** — Custom build strategies ([docs](docs/azd-integration.md))
- **GitHub Actions** — Automated CI/CD workflows ([docs](docs/github-actions.md))
- **Poetry/Hatch** — Build plugins in [`packages/`](packages/)
- **AI agents** — Copilot, MCP servers, automated scaffolding

## 🔌 Integrations

pyoci integrates seamlessly with popular Python tools:

### Poetry Plugin

```bash
poetry self add poetry-oci
poetry build-container --tag myapp:latest --push
```

[See full documentation →](packages/poetry-oci/)

### Hatch Plugin

```bash
pip install hatch-oci
hatch build  # Builds both wheel and container
```

[See full documentation →](packages/hatch-oci/)

### GitHub Actions

```yaml
jobs:
  build:
    uses: willena/pyoci/.github/workflows/pyoci.yml@main
    with:
      tag: ghcr.io/${{ github.repository }}:latest
      push: true
```

[See full documentation →](docs/github-actions.md)

### Azure Developer CLI

```yaml
# azure.yaml
hooks:
  build:
    run: pyoci build --tag ${SERVICE_IMAGE_NAME} --push
```

[See full documentation →](docs/azd-integration.md)

---

## 🎓 Configuration

### Auto-Detection (Zero Config)

By default, `pyoci` auto-detects:

- **Base image**: Python version from `requires-python` in `pyproject.toml` (e.g., `>=3.11` → `python:3.11-slim`)
- **Entry point**: First `[project.scripts]` entry in `pyproject.toml`
- **Include paths**: `src/`, `app/`, or `<package>/` dirs + `pyproject.toml`, `requirements.txt`
- **Working directory**: `/app/`
- **Architecture**: `linux/amd64`

### Explicit Configuration

```bash
# Full configuration with all options
pyoci build \
  --tag myapp:v1.2.3 \
  --context /my/project \
  --base-image python:3.11-slim \
  --include-deps \
  --workdir /app \
  --env KEY=value \
  --env ANOTHER=value \
  --platform linux/amd64 \
  --sbom cyclonedx \
  --config pyoci.toml \
  --verbose \
  --push \
  --no-cache

# Build for ARM64 (e.g., for AWS Graviton, Apple Silicon containers)
pyoci build \
  --tag myapp:arm64 \
  --platform linux/arm64 \
  --push
```

**Base Image & Dependencies**:
- `--base-image IMAGE` — Base image to build on (auto-detected from `requires-python` if not specified, e.g., `python:3.11-slim`)
- `--include-deps` — Package dependencies from venv or requirements.txt

**Container Metadata**:
- `--workdir PATH` — Set the container working directory
- `--env KEY=VALUE` — Add environment variables to the image
- `--label KEY=VALUE` — Add OCI labels to the image

**Caching Options**:
- `--no-cache` — Disable layer caching, force full rebuild
- `--cache-dir PATH` — Custom cache directory (default: `~/.pyoci/cache`)

**Production Features**:
- `--config FILE` — Load settings from `pyoci.toml`
- `--sbom FORMAT` — Generate SBOM (`spdx` or `cyclonedx`)
- `--platform PLATFORM` — Target platform (e.g., `linux/arm64`)
- `--verbose` / `-v` — Detailed build progress
- `--dry-run` — Preview build without creating artifacts
- `--clean-output-dir` / `--no-clean-output-dir` — Control whether the output directory is deleted before building
- `--no-reproducible` — Disable deterministic builds

The cache automatically:
- Reuses unchanged layers across builds (content-addressable by SHA256)
- Invalidates on file content changes (mtime + size checks)
- Evicts old entries using LRU when size limit reached (default: 5GB)

### Python API

```python
from pyoci.config import BuildConfig
from pyoci.builder import ImageBuilder

config = BuildConfig(
    tag="myapp:latest",
    context_dir=".",
    base_image="python:3.11-slim",  # Optional: auto-detected if omitted
    include_deps=True,
    workdir="/app",
    env={"DEBUG": "false", "ENV": "production"},
    labels={"version": "1.0", "maintainer": "team@example.com"},
    include_paths=["src/", "lib/", "pyproject.toml"],
    entrypoint=["python", "-m", "myapp"],
    generate_sbom="spdx",
    reproducible=True,
    verbose=True,
)

builder = ImageBuilder(config)
builder.build()
```

### Configuration File (`pyoci.toml`)

```toml
[build]
base_image = "python:3.11-slim"
workdir = "/app"
include_deps = true
reproducible = true
clean_output_dir = false

[build.labels]
maintainer = "team@example.com"
version = "1.0.0"

[build.env]
PORT = "8080"
ENV = "production"
DEBUG = "false"
```

Use the image tag itself or `--registry` at build time to control the push target.

---

## 🎯 Design Goals

### **1. Native Python Experience**
Container building should feel like a native Python operation, not a Docker side quest.

### **2. Zero External Dependencies**
No Docker daemon, CLI tools, or system packages required. Pure Python stdlib + OCI specs.

### **3. Language-Integrated**
Understand Python projects natively — entry points, modules, dependencies, project structure.

### **4. AI-Friendly API**
Simple, programmable interface for agentic workflows and Copilot-generated scaffolding.

### **5. Cross-Platform & Daemonless**
Works in GitHub Codespaces, Dev Box, locked-down environments — anywhere Python runs.

---

## 🤝 Why This Matters

### For Python Developers
- Simpler workflow than Dockerfiles
- No Docker requirement
- Faster onboarding for containerization

### For the Python Ecosystem
- A modern, standards-based approach to container builds
- Foundation for Poetry, Hatch, and other tool integrations
- Opens new possibilities for Python in cloud-native environments

---

## 🔬 Current Limitations

Known limitations and future enhancements:

- **Framework detection** — Supports FastAPI, Flask, Django only (easy to extend)
- **SBOM scope** — Python packages only; doesn't parse OS packages from base images

**Note**: Cross-platform builds pull the correct architecture variant from multi-platform base images and generate proper OCI metadata. For Python applications (interpreted language), no actual cross-compilation is needed.

---

## 🛠️ Development

### Prerequisites

- Python 3.11+ (uses `tomllib`)
- No other dependencies — pure stdlib

### Install for Development

```bash
git clone https://github.com/willena/pyoci.git
cd pyoci
uv sync --all-packages --group dev

# Format the whole workspace
uv run ruff format .
```

### Workspace Packaging

From the repository root, `uv` now treats `packages/*` as a workspace.

```bash
# Inspect the workspace packages
uv workspace list

# Build a single package
uv build --package pyoci --out-dir dist

# Build every publishable package
uv build --all-packages --out-dir dist

# Publish to TestPyPI first, then PyPI
uv publish --index testpypi dist/*
uv publish --index pypi dist/*
```

### Test a Build

```bash
# Create a test project
mkdir test_app && cd test_app
echo 'print("Hello from container!")' > app.py
cat > pyproject.toml << EOF
[project]
name = "test-app"
version = "0.1.0"
EOF

# Build it
pyoci build --tag test:latest --verbose

# Test with skopeo + Docker
skopeo copy oci:dist/image docker-daemon:test:latest
docker run test:latest

# Or test with Podman (native OCI support)
podman run oci:dist/image:test
```

---

## 📚 Resources

### Documentation

- **[Local Development Guide](docs/local-development.md)** — Complete guide for using pyoci locally
- **[Azure Developer CLI Integration](docs/azd-integration.md)** — Deploy to Azure with azd
- **[GitHub Actions Guide](docs/github-actions.md)** — Automate builds in CI/CD

### External References

- **OCI Image Spec**: [opencontainers/image-spec](https://github.com/opencontainers/image-spec)
- **Docker Registry v2 API**: [Docker Registry HTTP API V2](https://docs.docker.com/registry/spec/api/)

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details

---

## 🙏 Acknowledgments

Inspired by:

- [spboyer/pycontainer-build](https://github.com/spboyer/pycontainer-build) — The original repository that served as base for this work.  
- [.NET SDK's native container support](https://github.com/dotnet/sdk-container-builds)
- [Jib (Java)](https://github.com/GoogleContainerTools/jib) — Daemonless container builds
- [ko (Go)](https://github.com/ko-build/ko) — Simple container images for Go
