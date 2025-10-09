## Overview

This repository contains a Python 3.11 AWS Lambda function that accepts a JSON payload and forwards the `message` field to an Amazon SQS queue. The function is deployed with the Serverless Framework and can be exercised locally through the same tooling.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- AWS credentials with permission to interact with the target SQS queue (`sqs:SendMessage`)
- An SQS queue URL to use for the `QUEUE_URL` environment variable (you can reuse the production queue or create a separate queue for testing)

## Local Setup

1. Install Node dependencies (installs the Serverless CLI locally):
   ```bash
 npm install
  ```
2. Ensure Python dependencies are available. The function only relies on `boto3`, which is included in the AWS Lambda runtime, but for local invocation you can install it explicitly:
   ```bash
   python3 -m pip install --user boto3
   ```
3. Export the queue URL you want to target when running locally:
   ```bash
   export QUEUE_URL="https://sqs.us-east-1.amazonaws.com/975049899047/sqs-hackathon-2025"
   ```

## Local Testing

- **Invoke the handler directly** with a payload:
  ```bash
  npm run invoke -- --data '{"message": "hello from local"}'
  ```
  The script uses `serverless invoke local`, executes `handler.post_to_sqs`, and prints the JSON response to stdout.

- **Send an empty payload** to exercise the default behaviour:
  ```bash
  npm run invoke -- --data '{}'
  ```

- **Run the HTTP API with serverless-offline**:
  ```bash
  npm run offline
  ```
  The plugin serves the HTTP API on `http://localhost:3000/send`. In another terminal you can send requests, for example:
  ```bash
  curl -X POST "http://localhost:3000/send" \
    -H "Content-Type: application/json" \
    -d '{"message": "hello from offline"}'
  ```
  The offline server uses the `QUEUE_URL` from your environment, so keep it exported in the same shell before starting the process.

> Tip: you can append `--env QUEUE_URL=$QUEUE_URL` to the invoke command if you prefer not to export the variable in your shell.

## Deployment

1. Make sure the `QUEUE_URL` in `serverless.yaml` points at the queue you expect in the target environment.
2. Deploy with the Serverless Framework:
   ```bash
   npm run deploy
   ```
3. Retrieve the deployed endpoints:
   ```bash
   npm run info
   ```
4. (Optional) Remove the stack when no longer needed:
   ```bash
   npm run remove
   ```

The deployment uses the IAM permissions defined in `serverless.yaml` to grant the Lambda function access to SQS and AWS Secrets Manager.

## Environment Variables

- `QUEUE_URL` (required): absolute URL of the SQS queue that should receive messages. During deployment this value is baked into the Lambda configuration from `serverless.yaml`. When running locally, the variable must be set in your shell or passed via `--env`.

## Useful Commands

- `npm run package` – creates the deployment artifact locally without pushing it to AWS.
- `npm run deploy` – deploys the stack to AWS.
- `npm run remove` – removes the deployed stack.
- `npm run invoke` – runs the Lambda locally against your shell environment.
- `npm run info` – prints the deployed resources and endpoints.
- `npm run offline` – serves the HTTP API locally on `http://localhost:3000`.

Refer to the Serverless Framework documentation for additional commands and options.
