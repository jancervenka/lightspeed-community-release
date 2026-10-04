#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: bash init.sh NEW_VERSION CONTAINER_IMAGE_TAG" >&2
    exit 1
fi

NEW_VERSION=$1
CONTAINER_IMAGE_TAG=$2
if [[ ! "$NEW_VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    echo "NEW_VERSION must have the form X.Y.Z (for example, 0.0.3)." >&2
    exit 1
fi
if [[ ! "$CONTAINER_IMAGE_TAG" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ ]]; then
    echo "CONTAINER_IMAGE_TAG must be a valid container image tag." >&2
    exit 1
fi

REPO_PATH=${REPO_PATH:-/tmp/community-operators-prod}
REPO_URL=${REPO_URL:-https://github.com/redhat-openshift-ecosystem/community-operators-prod.git}
BASE_BRANCH=${BASE_BRANCH:-main}
RELEASE_BRANCH="openstack-lightspeed-release-${NEW_VERSION}"
RELEASE_PATH="${REPO_PATH}/operators/openstack-lightspeed-operator/${NEW_VERSION}"
IMAGE="quay.io/openstack-lightspeed/operator-bundle:${CONTAINER_IMAGE_TAG}"

if [[ ! -d "${REPO_PATH}/.git" ]]; then
    git clone --filter=blob:none --sparse --single-branch --branch "$BASE_BRANCH" "$REPO_URL" "$REPO_PATH"
    git -C "$REPO_PATH" sparse-checkout set operators/openstack-lightspeed-operator
fi
if [[ -n "$(git -C "$REPO_PATH" status --porcelain)" ]]; then
    echo "The checkout at $REPO_PATH must be clean before preparing a release." >&2
    exit 1
fi
if git -C "$REPO_PATH" show-ref --verify --quiet "refs/heads/${RELEASE_BRANCH}"; then
    git -C "$REPO_PATH" checkout "$RELEASE_BRANCH"
else
    git -C "$REPO_PATH" checkout -b "$RELEASE_BRANCH"
fi

BUNDLE_PATH=$(mktemp -d)
CONTAINER_ID=""
cleanup() {
    if [[ -n "$CONTAINER_ID" ]]; then
        podman rm "$CONTAINER_ID" >/dev/null || true
    fi
    rm -rf -- "$BUNDLE_PATH"
}
trap cleanup EXIT

podman pull "$IMAGE"
# Use the pulled image ID so a moving tag cannot change between pull and create.
IMAGE_ID=$(podman image inspect --format '{{.Id}}' "$IMAGE")
CONTAINER_ID=$(podman create "$IMAGE_ID")
for directory in manifests metadata tests; do
    podman cp "${CONTAINER_ID}:/${directory}" "$BUNDLE_PATH"
done

mkdir -p "$RELEASE_PATH"
for directory in manifests metadata tests; do
    # Replace each directory so reruns also remove files removed from the bundle.
    rm -rf -- "${RELEASE_PATH:?}/${directory}"
    mv "${BUNDLE_PATH}/${directory}" "$RELEASE_PATH/"
done
