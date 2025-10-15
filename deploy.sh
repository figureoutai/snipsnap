#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

STAGE="${STAGE:-main}"
AWS_REGION="${AWS_REGION:-us-east-1}"
SERVICE_NAME="highlight-clipping-service"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
DEPLOY_INFRA=true
DEPLOY_IMAGE=true
DEPLOY_FRONTEND=true

usage() {
  cat >&2 <<USAGE
Usage: ./deploy.sh [--image-only | --infra-only | --frontend]

No args: deploy infra + image + frontend.
--image-only: build and push container image only.
--infra-only: deploy Serverless stack only.
--frontend: build Vite app and upload to S3, then invalidate CloudFront.
USAGE
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    --image-only)
      DEPLOY_INFRA=false
      DEPLOY_FRONTEND=false
      ;;
    --infra-only)
      DEPLOY_IMAGE=false
      DEPLOY_FRONTEND=false
      ;;
    --frontend)
      DEPLOY_INFRA=false
      DEPLOY_IMAGE=false
      ;;
    -h|--help)
      usage; exit 0;
      ;;
    *)
      echo "Unsupported argument: $1" >&2
      usage; exit 1;
      ;;
  esac
  shift || true
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
require npm
require docker

if [ "$DEPLOY_INFRA" = true ]; then
  log "Deploying infrastructure with Serverless (stage: ${STAGE})"
  npm run deploy
else
  log "Skipping Serverless deploy (--image-only)"
fi

if [ "$DEPLOY_IMAGE" = true ]; then
  ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")"
  ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

  log "Validating ECR repository ${REPO_NAME}"
  if ! aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "Error: ECR repository '${REPO_NAME}' not found. Deploy infrastructure first (omit --image-only)." >&2
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
fi

cf_output() {
  local key="$1"
  aws cloudformation describe-stacks \
    --stack-name "${SERVICE_NAME}-${STAGE}" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='${key}'].OutputValue" \
    --output text
}

if [ "$DEPLOY_FRONTEND" = true ]; then
  log "Building frontend (Vite)"
  pushd frontend >/dev/null
  npm ci
  npm run build
  popd >/dev/null

  BUCKET_NAME="$(cf_output FrontendBucketName || true)"
  DIST_ID="$(cf_output FrontendDistributionId || true)"

  if [[ -z "$BUCKET_NAME" || -z "$DIST_ID" ]]; then
    echo "Error: Frontend outputs not found in CloudFormation stack ${SERVICE_NAME}-${STAGE}. Did you deploy infrastructure?" >&2
    exit 1
  fi

  log "Syncing frontend/dist to s3://${BUCKET_NAME} (long-cache for assets)"
  aws s3 sync frontend/dist "s3://${BUCKET_NAME}" \
    --delete \
    --cache-control "max-age=31536000,public" \
    --exclude "index.html"

  log "Uploading index.html with no-cache"
  aws s3 cp frontend/dist/index.html "s3://${BUCKET_NAME}/index.html" \
    --cache-control "no-cache, no-store, must-revalidate" \
    --content-type "text/html"

  log "Creating CloudFront invalidation on ${DIST_ID}"
  aws cloudfront create-invalidation \
    --distribution-id "$DIST_ID" \
    --paths "/*" \
    --region "$AWS_REGION" >/dev/null
fi

log "Deployment complete"
