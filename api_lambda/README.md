## Local Testing

- Run the HTTP API with Serverless Offline (from repo root):
  ```bash
  npm run offline
  ```
  The API listens on `http://localhost:3000`. Examples:
  ```bash
  # Submit a video URL for processing
  curl -sS -X POST "http://localhost:3000/video-url" \
    -H "Content-Type: application/json" \
    -d '{"stream_url": "https://example.com/video.mp4"}'

  # List streams (paginated)
  curl -sS "http://localhost:3000/streams?page=1&limit=12"

  # Fetch highlights for a stream
  curl -sS "http://localhost:3000/highlights?stream_id=abc12345"
  ```
## Environment Variables

- `BATCH_JOB_QUEUE` (required): AWS Batch job queue receiving submitted jobs.
- `BATCH_JOB_DEFINITION` (required): AWS Batch job definition for the containerized pipeline.
- `SECRET_NAME` (required): Secrets Manager ARN/name for DB credentials.
- `DB_URL` (required): Aurora cluster endpoint hostname.
- `DB_NAME` (required): Database name in Aurora.
- `STREAM_METADATA_TABLE` (required): table that stores job status and final highlights (e.g., `stream_metadata`).
- `FRONTEND_ORIGIN` (optional): default origin for CORS responses (set to CloudFront domain in deploys).
- `ALLOWED_ORIGINS` (optional): comma‑separated allowlist; if the request `Origin` matches one of these, it is echoed.
- `ACCEPT_STREAMS: `True`/`False` to globally allow submissions; defaults to `True` in `serverless.yaml`.
- `AWS_REGION` (optional): Region for AWS SDK calls; defaults to `us-east-1`.

## Deployment

1. Deploy the full stack (from repo root) or just the API using Serverless:
   ```bash
   npm run deploy
   # or package/info/remove
   npm run info
   npm run remove
   ```
2. Endpoints: see the outputs from `serverless info` or the `functions` block in `../serverless.yaml`.

This Lambda uses the IAM permissions defined in `../serverless.yaml` to access AWS Batch and AWS Secrets Manager.
