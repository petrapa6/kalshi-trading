#!/usr/bin/env bash
# Verify the add-on image builds for aarch64 (RPi5) locally, before pushing.
#
# Production deploy does NOT use this: HAOS Supervisor builds the image itself,
# natively on the Pi, from this repo's Dockerfile + config.yaml. This script
# only catches an arm64 build break on your x86_64 dev machine first, so a bad
# push doesn't fail the Supervisor build.
#
# Requires: docker buildx + arm64 emulation (`docker run --privileged --rm
# tonistiigi/binfmt --install arm64` once).
set -euo pipefail

IMAGE_NAME="kalshi-trading"
TAG="arm64-test"
PLATFORM="linux/arm64"

# network=host lets the builder container resolve DNS / pull images through the
# host — without it the docker-container driver can time out reaching registries.
docker buildx inspect haos-builder >/dev/null 2>&1 || \
  docker buildx create --name haos-builder --driver-opt network=host --use

echo "==> Building ${IMAGE_NAME}:${TAG} for ${PLATFORM}..."
echo "    (Slow: the dashboard build runs under QEMU emulation to get arm64 @next/swc)"

docker buildx build \
  --builder haos-builder \
  --platform "${PLATFORM}" \
  --load \
  -t "${IMAGE_NAME}:${TAG}" \
  .

echo ""
echo "==> arm64 build OK: ${IMAGE_NAME}:${TAG}"
echo "    Smoke-run it (needs binfmt) with:"
echo "        docker run --rm --platform linux/arm64 -p 8000:8000 \\"
echo "          -e API_TOKEN=x -e DASHBOARD_PASSWORD=x \\"
echo "          -e KALSHI_API_KEY=x -e KALSHI_PRIVATE_KEY=\"\$(openssl genrsa 2048)\" \\"
echo "          ${IMAGE_NAME}:${TAG}"
