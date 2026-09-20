#!/bin/bash
# Multi-platform build demonstration script

set -e

echo "🐍 pyoci Cross-Platform Demo"
echo "=========================================="
echo ""

# Check if pyoci is installed
if ! command -v pyoci &> /dev/null; then
    echo "❌ pyoci not found. Please install it first:"
    echo "   pip install -e /path/to/pyoci"
    exit 1
fi

# Create demo directory
DEMO_DIR="cross-platform-demo"
if [ -d "$DEMO_DIR" ]; then
    echo "📁 Cleaning existing demo directory..."
    rm -rf "$DEMO_DIR"
fi

mkdir "$DEMO_DIR"
cd "$DEMO_DIR"

echo "📝 Creating demo application..."

# Create app
cat > app.py << 'EOF'
import platform
import sys

def main():
    print("=" * 50)
    print("Cross-Platform Container Demo")
    print("=" * 50)
    print(f"Python Version: {sys.version}")
    print(f"Machine: {platform.machine()}")
    print(f"Architecture: {platform.architecture()}")
    print(f"System: {platform.system()}")
    print(f"Platform: {platform.platform()}")
    print("=" * 50)

if __name__ == "__main__":
    main()
EOF

# Create pyproject.toml
cat > pyproject.toml << 'EOF'
[project]
name = "cross-platform-demo"
version = "1.0.0"
requires-python = ">=3.11"

[project.scripts]
demo = "app:main"
EOF

echo "✅ Demo application created"
echo ""

# Build for AMD64
echo "🏗️  Building for linux/amd64..."
pyoci build \
  --tag cross-platform-demo:amd64 \
  --platform linux/amd64 \
  --base-image python:3.11-slim

echo "✅ AMD64 build complete"
echo ""

# Inspect AMD64 image
echo "🔍 Inspecting AMD64 image metadata..."
MANIFEST_AMD64=$(jq -r '.manifests[0].digest' dist/image/index.json | cut -d: -f2)
CONFIG_AMD64=$(jq -r '.config.digest' dist/image/blobs/sha256/$MANIFEST_AMD64 | cut -d: -f2)
echo "Platform info:"
jq '{architecture: .architecture, os: .os}' dist/image/blobs/sha256/$CONFIG_AMD64
echo ""

# Build for ARM64
echo "🏗️  Building for linux/arm64..."
rm -rf dist/  # Clean for next build
pyoci build \
  --tag cross-platform-demo:arm64 \
  --platform linux/arm64 \
  --base-image python:3.11-slim

echo "✅ ARM64 build complete"
echo ""

# Inspect ARM64 image
echo "🔍 Inspecting ARM64 image metadata..."
MANIFEST_ARM64=$(jq -r '.manifests[0].digest' dist/image/index.json | cut -d: -f2)
CONFIG_ARM64=$(jq -r '.config.digest' dist/image/blobs/sha256/$MANIFEST_ARM64 | cut -d: -f2)
echo "Platform info:"
jq '{architecture: .architecture, os: .os}' dist/image/blobs/sha256/$CONFIG_ARM64
echo ""

echo "✅ Multi-platform build demonstration complete!"
echo ""
echo "📊 Summary:"
echo "  - AMD64 image: cross-platform-demo:amd64"
echo "  - ARM64 image: cross-platform-demo:arm64"
echo ""
echo "💡 Next steps:"
echo "  1. Load into Docker: docker load -i <(tar -C dist/image -cf - .)"
echo "  2. Run the image: docker run cross-platform-demo:arm64"
echo "  3. Push to registry: pyoci build --tag <registry>/<image> --platform linux/amd64 --push"
echo ""
echo "🔗 More info: https://github.com/willena/pyoci/tree/main/examples/cross-platform"
