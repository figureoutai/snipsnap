#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

STAGE="${1:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
SERVICE_NAME="test-project-service"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REPO_NAME="${SERVICE_NAME}-${STAGE}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command '$1' not found in PATH." >&2
    exit 1
  fi
}

require aws
require docker
require npm

log "Deploying infrastructure with Serverless (stage: ${STAGE})"
npm run deploy

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

log "Validating ECR repository ${REPO_NAME}"
if ! aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "Error: ECR repository '${REPO_NAME}' not found. Ensure serverless deployment succeeded and created it." >&2
  exit 1
fi

log "Authenticating Docker with ECR"
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

log "Building Docker image ${ECR_URI}:${IMAGE_TAG}"
DOCKER_BUILDKIT=1 docker build -f Dockerfile -t "${ECR_URI}:${IMAGE_TAG}" .

log "Pushing image to ECR"
docker push "${ECR_URI}:${IMAGE_TAG}"

log "Forcing ECS service deployment to pick up the new image"
aws ecs update-service \
  --cluster "${SERVICE_NAME}-${STAGE}" \
  --service "${SERVICE_NAME}-${STAGE}-service" \
  --force-new-deployment \
  --region "$AWS_REGION" >/dev/null

log "Deployment complete"
