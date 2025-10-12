#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

STAGE="${STAGE:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
SERVICE_NAME="test-project-service"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
DEPLOY_INFRA=true

if [[ $# -gt 0 ]]; then
  if [[ "$1" == "--image-only" ]]; then
    DEPLOY_INFRA=false
    shift
  else
    echo "Unsupported argument: $1" >&2
    echo "Usage: ./deploy.sh [--image-only]" >&2
    exit 1
  fi
fi

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

if [ "$DEPLOY_INFRA" = true ]; then
  log "Deploying infrastructure with Serverless (stage: ${STAGE})"
  npm run deploy
else
  log "Skipping Serverless deploy (--image-only)"
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

log "Validating ECR repository ${REPO_NAME}"
if ! aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "Error: ECR repository '${REPO_NAME}' not found. Deploy infrastructure first (omit --ecs-only)." >&2
  exit 1
fi

log "Authenticating Docker with ECR"
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

log "Building Docker image ${ECR_URI}:${IMAGE_TAG} for platform ${IMAGE_PLATFORM}"
DOCKER_BUILDKIT=1 docker build \
  --platform "${IMAGE_PLATFORM}" \
  -f Dockerfile \
  -t "${ECR_URI}:${IMAGE_TAG}" \
  .

log "Pushing image to ECR"
docker push "${ECR_URI}:${IMAGE_TAG}"

log "Verifying AWS Batch compute environment is available"
aws batch describe-compute-environments \
  --compute-environments "${SERVICE_NAME}-${STAGE}-compute-env" \
  --region "$AWS_REGION" >/dev/null

log "Verifying AWS Batch job queue"
aws batch describe-job-queues \
  --job-queues "${SERVICE_NAME}-${STAGE}-queue" \
  --region "$AWS_REGION" >/dev/null

log "Deployment complete"
