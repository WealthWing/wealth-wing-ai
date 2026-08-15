# AWS ECS Express Mode deployment

This is the beginner-friendly, production-aligned deployment path for Wealth
Wing AI. It deploys the existing Docker image with Amazon ECS Express Mode.
Express Mode creates and manages the Fargate service, HTTPS Application Load
Balancer, networking, health monitoring, scaling, and CloudWatch logging.

The first deployment uses the AWS-provided HTTPS URL. Add a custom domain only
after the service and frontend work correctly.

## Architecture

```text
Local repository
    |
    | build and push Docker image
    v
Amazon ECR
    |
    | deploy image digest
    v
ECS Express Mode ----> Public HTTPS URL
    |                         |
    |                         +----> React frontend
    |
    +----> CloudWatch Logs
    +----> Secrets Manager (TOGETHER_API_KEY)
```

## Important application limitation

The Wing agent currently stores checkpoints in process memory. Keep the service
at one task and one Uvicorn worker:

```text
Minimum tasks: 1
Maximum tasks: 1
```

A task replacement or deployment can clear conversation history. This is
acceptable for the learning deployment. Move checkpoints to durable shared
storage before scaling beyond one task.

## Approximate monthly cost

The following estimate assumes `us-east-1`, 730 hours per month, one Linux/X86
Fargate task with `0.25 vCPU` and `1 GB` memory, very light traffic, the default
public networking created by Express Mode, and one secret.

| Resource | Approximate monthly cost |
| --- | ---: |
| Fargate task | $10.63 |
| Application Load Balancer base charge | $16.43 |
| Public IPv4 addresses (typically two for the ALB and one for the task) | $10.95 |
| Secrets Manager | $0.40 |
| ALB usage, ECR storage, CloudWatch logs, and light data transfer | $0-$2 |
| **Expected backend total** | **about $40-$45/month** |

These prices are estimates, not a billing guarantee. Taxes, traffic, log
volume, additional images, and future AWS price changes can change the total.
Together AI model usage, Cognito charges beyond any applicable free allowance,
the React frontend, and the Wealth Wing Data API are not included.

Before deploying, create an AWS Budget alert at a monthly amount you are
comfortable with. New-account credits can reduce the initial bill, but do not
design around receiving them.

Amazon Lightsail Containers offers a lower-cost Micro plan with `0.25 vCPU` and
`1 GB` memory for about $10/month. It is not the selected workflow because ECS
Express Mode provides the direct Secrets Manager integration and standard ECS
resources that this authenticated financial API should use. Lightsail remains
an option for a short-lived learning demo if its secret-handling tradeoff is
accepted.

Current pricing references:

- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/)
- [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)
- [Amazon VPC public IPv4 pricing](https://aws.amazon.com/vpc/pricing/)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [Amazon ECR pricing](https://aws.amazon.com/ecr/pricing/)
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [Amazon Lightsail pricing](https://aws.amazon.com/lightsail/pricing/)

## 1. Prerequisites

Use the same AWS Region as the Cognito user pool. The current local
configuration uses `us-east-1`.

Prepare the following:

- An AWS account with billing alerts enabled
- AWS CLI v2, authenticated to the intended AWS account
- Docker with Buildx support
- A default VPC with public subnets in at least two Availability Zones
- The deployed React origin, or `http://localhost:3000` for initial testing
- Cognito user-pool values
- Together API credentials
- Reachable Wealth Wing Data API and health URLs

Confirm the AWS identity and Region before creating resources:

```bash
aws sts get-caller-identity
aws configure get region
```

Set deployment variables in the shell:

```bash
DEPLOY_REGION=us-east-1
DEPLOY_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
DEPLOY_IMAGE_TAG="$(git rev-parse --short HEAD)"
DEPLOY_ECR_REPOSITORY=wealth-wing-ai
DEPLOY_ECR_REGISTRY="${DEPLOY_ACCOUNT_ID}.dkr.ecr.${DEPLOY_REGION}.amazonaws.com"
```

## 2. Verify the container locally

Build and recreate the local container so it receives the current `.env`:

```bash
docker compose up -d --build --force-recreate api
curl --fail http://127.0.0.1:8001/health/ping
docker compose ps
```

The health endpoint must return HTTP `200` before continuing.

The local `.env` file is not copied into the image and is not synchronized to
AWS. AWS configuration is entered separately during service creation.

## 3. Create the ECR repository

Create the private repository once:

```bash
aws ecr create-repository \
  --region "${DEPLOY_REGION}" \
  --repository-name "${DEPLOY_ECR_REPOSITORY}" \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true
```

If the repository already exists, do not create it again.

Authenticate Docker to ECR:

```bash
aws ecr get-login-password --region "${DEPLOY_REGION}" \
  | docker login \
      --username AWS \
      --password-stdin "${DEPLOY_ECR_REGISTRY}"
```

## 4. Build and push the image

Express Mode uses Linux/X86_64 by default. The explicit platform is especially
important when building on an Apple Silicon Mac.

```bash
docker buildx build \
  --platform linux/amd64 \
  --target runtime \
  --tag "${DEPLOY_ECR_REGISTRY}/${DEPLOY_ECR_REPOSITORY}:${DEPLOY_IMAGE_TAG}" \
  --push \
  .
```

In the ECR console, confirm that the image exists and review its vulnerability
scan. Deploy by image digest when the ECS console offers that choice. A digest
identifies the exact immutable image being deployed.

## 5. Store the Together API key

Do not place the Together API key in the Docker image, command history, or a
plain ECS environment variable.

In the AWS console:

1. Open **Secrets Manager**.
2. Choose **Store a new secret**.
3. Choose **Other type of secret**.
4. Store the `TOGETHER_API_KEY` value.
5. Name the secret `wealth-wing-ai/together-api-key`.
6. Copy the secret ARN for the ECS configuration.

The ECS task execution role must have `secretsmanager:GetSecretValue`
permission for this specific secret ARN. If the ECS console-created execution
role does not include that access, add this least-privilege inline policy to the
role and replace `<secret-arn>`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "<secret-arn>"
    }
  ]
}
```

## 6. Create the ECS Express Mode service

Open the AWS console and go to:

```text
Amazon ECS -> Express mode -> Create
```

Use these settings:

| Setting | Value |
| --- | --- |
| Service name | `wealth-wing-ai` |
| Image | The ECR image digest from step 4 |
| Container port | `8000` |
| Health-check path | `/health/ping` |
| CPU | `0.25 vCPU` |
| Memory | `1 GB` |
| Minimum tasks | `1` |
| Maximum tasks | `1` |
| Networking | Default public VPC configuration |

Allow the console to create the Express Mode infrastructure role. Select an ECS
task execution role that can pull from ECR, write CloudWatch logs, and read only
the selected Together secret.

Express Mode creates the HTTPS load balancer, target group, security groups,
CloudWatch log group, health monitoring, and AWS-provided URL. Do not create a
separate load balancer, target group, NAT Gateway, or ECS service for this
workflow.

### Plain environment variables

Add these as ordinary environment variables. Replace all placeholder values:

```text
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json
ENABLE_DOCS=false
FE_URL=https://<react-domain>
CORS_ORIGINS=https://<react-domain>
ALLOWED_HOSTS=*
FORWARDED_ALLOW_IPS=*
MODEL=openai/gpt-oss-120b
TOGETHER_API_BASE=https://api.together.xyz/v1
AWS_REGION=us-east-1
COGNITO_USER_POOL_ID=<user-pool-id>
COGNITO_JWKS_URL=<cognito-jwks-url>
COGNITO_ISSUER=<cognito-issuer>
COGNITO_CLIENT_ID=<cognito-client-id>
WEALTH_WING_DATA_URL=<data-api-url>
WEALTH_WING_DATA_HEALTH_URL=<data-health-url>
```

For initial local-frontend testing, use `http://localhost:3000` for `FE_URL`
and `CORS_ORIGINS`. Update both after the React frontend is deployed.

`ALLOWED_HOSTS=*` permits the AWS-provided hostname and load-balancer health
checks. This is acceptable for this learning deployment because Express Mode
creates a task security group that permits inbound application traffic only
from its load balancer. Revisit this setting when customizing networking.

### Secret environment variable

Add one secret reference:

```text
Name: TOGETHER_API_KEY
Value source: <Secrets Manager ARN from step 5>
```

Create the service and wait until the deployment status is active and the
target is healthy.

## 7. Verify the deployment

Copy the application URL displayed by Express Mode:

```text
https://<service-name>.ecs.us-east-1.on.aws
```

Verify the public and protected endpoints:

```bash
DEPLOY_API_URL=https://<service-name>.ecs.us-east-1.on.aws

curl --fail "${DEPLOY_API_URL}/health/ping"
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  "${DEPLOY_API_URL}/agents/wing/invoke"
```

Expected results:

- `/health/ping` returns `200`.
- `/agents/wing/invoke` without a bearer token returns `401`.

Next, confirm that structured logs appear in CloudWatch. Use the React
application to test Cognito login, one authenticated agent request, and a
follow-up request using the returned `thread_id`.

## 8. Connect the React frontend

Set the frontend API base URL to the Express Mode application URL. Update the
backend `FE_URL` and `CORS_ORIGINS` if the deployed React origin differs from
the initial value, then deploy a new ECS service revision.

Use the AWS-provided HTTPS URL until the full application works. A custom API
domain and ACM certificate can be added later without changing the container.

## 9. Deploy updates

### Code, dependency, or Dockerfile change

1. Run the local verification.
2. Choose a new immutable image tag.
3. Build and push the new image to ECR.
4. Update the Express Mode service to the new image digest.
5. Repeat the health, authentication, frontend, and log checks.

Do not overwrite or reuse an existing image tag.

### Environment-variable change

Update the Express Mode environment configuration and deploy the new service
revision. Changing the local `.env` does not update AWS.

### Secret change

Update the value in Secrets Manager, then force a new ECS deployment. A running
container does not automatically receive a changed secret value.

## 10. Control cost and clean up

Check AWS Cost Explorer and the budget alert after the first 24 hours and again
after the first week.

Express Mode resources continue to incur charges while the service exists, even
when the API receives no user traffic. To stop the recurring backend cost,
delete the Express Mode service from the ECS console. Then confirm whether these
separately managed resources should also be deleted:

- Old ECR images or the ECR repository
- The Together API secret
- CloudWatch log groups retained after service deletion
- IAM roles created only for this service
- Custom DNS records or certificates, if added later

Never delete shared IAM roles, load balancers, security groups, or networking
resources without first confirming which services use them.

## Later migration path

When the application and AWS concepts are familiar, move to a custom ECS task
definition and infrastructure as code such as AWS CDK, CloudFormation, or
Terraform. Before scaling out, replace in-memory checkpoints with durable
shared storage. Express Mode leaves the underlying ECS and load-balancer
resources visible in the AWS account, so the learning transfers directly to
standard ECS operations.
