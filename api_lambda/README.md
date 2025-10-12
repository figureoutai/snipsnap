## Local Testing

- **Run the HTTP API with serverless-offline**:
  ```bash
  npm run offline
  ```
  The plugin serves the HTTP API on `http://localhost:3000/send`. In another terminal you can send requests, for example:
  ```bash
  curl -X POST "http://localhost:3000/video-url" \
    -H "Content-Type: application/json" \
    -d '{"message": "hello from offline"}'
  ```
## Environment Variables

- `BATCH_JOB_QUEUE` (required): name or ARN of the AWS Batch job queue that receives submitted jobs.
- `BATCH_JOB_DEFINITION` (required): name or ARN of the AWS Batch job definition used for video processing jobs.
- `SECRET_NAME` (required): name or ARN of the Secrets Manager secret that stores database credentials.
- `DB_URL` (required): hostname of the Aurora cluster endpoint to connect to.
- `DB_NAME` (required): database name in the Aurora cluster.
- `DB_PORT` (optional): database port; defaults to `3306` when unset.
- `AWS_REGION` (optional): AWS region to use for Secrets Manager lookups; defaults to `us-east-1`.

## Deployment

1. Deploy with the Serverless Framework:
   ```bash
   npm run deploy
   ```
2. Retrieve the deployed endpoints:
   ```bash
   npm run info
   ```
3. (Optional) Remove the stack when no longer needed:
   ```bash
   npm run remove
   ```

The deployment uses the IAM permissions defined in `../serverless.yaml` to grant the Lambda function access to AWS Batch and AWS Secrets Manager.
