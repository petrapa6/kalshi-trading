#!/usr/bin/env bash
# Build the HAOS add-on image locally (x86_64/amd64) for testing.
# Run from the repo root.
set -euo pipefail

IMAGE_NAME="kalshi-trading"
TAG="dev"
PLATFORM="linux/amd64"

# network=host lets the builder container resolve DNS / pull images through the
# host — without it the docker-container driver can time out reaching registries.
docker buildx inspect haos-builder >/dev/null 2>&1 || \
  docker buildx create --name haos-builder --driver-opt network=host --use

echo "==> Building ${IMAGE_NAME}:${TAG} for ${PLATFORM}..."

docker buildx build \
  --builder haos-builder \
  --platform "${PLATFORM}" \
  --load \
  -t "${IMAGE_NAME}:${TAG}" \
  .

echo "==> Build complete: ${IMAGE_NAME}:${TAG}"
echo "    Image size: $(docker image inspect "${IMAGE_NAME}:${TAG}" --format='{{.Size}}' | numfmt --to=iec 2>/dev/null || docker image inspect "${IMAGE_NAME}:${TAG}" --format='{{.Size}}')"
