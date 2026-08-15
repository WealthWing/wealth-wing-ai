# AWS ECS Fargate deployment

This guide deploys the Wealth Wing AI container to one Linux/X86_64 ECS Fargate
task behind an HTTPS Application Load Balancer. It intentionally uses one task
because agent checkpoints are stored in process memory.

## 1. Prerequisites

Prepare the following values before deploying:

- AWS account ID and Region
- A DNS name for the API, such as `ai.example.com`
- An ACM certificate in the same Region as the load balancer
- The deployed React origin, such as `https://app.example.com`
- Cognito user-pool values
- Together API credentials
- Reachable Wealth Wing Data API and health URLs

Create an ECR repository named `wealth-wing-ai` and enable image scanning. Use
immutable tags such as a Git commit SHA instead of relying on `latest`.

## 2. Build and push the image

Set shell variables for this deployment:

```bash
AWS_ACCOUNT_ID=<aws-account-id>
AWS_REGION=<aws-region>
IMAGE_TAG=<git-commit-sha>
ECR_REPOSITORY=wealth-wing-ai
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

Authenticate Docker to ECR:

```bash
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
```

Build the AMD64 runtime image and push it directly to ECR. The explicit platform
is required when publishing from an ARM-based Mac for an X86_64 Fargate task.

```bash
docker buildx build \
  --platform linux/amd64 \
  --target runtime \
  --tag "${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}" \
  --push \
  .
```

Confirm that the pushed image passed ECR's vulnerability scan before deploying
it.

## 3. Configure secrets and logs

Store `TOGETHER_API_KEY` in AWS Secrets Manager. Create a CloudWatch log group
for the service with a 14-day retention period.

The ECS task execution role needs permission to:

- Pull the image from ECR
- Write to the CloudWatch log group
- Read the selected Together API secret

The application itself does not currently call AWS APIs, so its task role does
not need additional permissions.

## 4. Create the Fargate task definition

Create a task definition with these task-level settings:

| Setting | Value |
| --- | --- |
| Launch type | Fargate |
| Operating system | Linux |
| CPU architecture | X86_64 |
| Network mode | `awsvpc` |
| CPU | `0.25 vCPU` |
| Memory | `1 GB` |
| Container port | `8000/TCP` |
| Essential container | Yes |
| Init process | Enabled |
| Read-only root filesystem | Enabled |

Create an empty task volume named `tmp` and mount it read/write at `/tmp`. ECS
Fargate does not support the Docker `tmpfs` task parameter, so this writable
ephemeral mount complements the read-only root filesystem.

Configure the `awslogs` log driver and use the image command already defined in
the Dockerfile. Do not add multiple Uvicorn workers.

Define this health check in the ECS container definition. ECS does not monitor a
Dockerfile health check unless it is also present in the task definition.

```text
CMD,python,-c,import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ping', timeout=2)
```

Use an interval of 30 seconds, timeout of 5 seconds, 3 retries, and a 10-second
start period.

### Environment values

Set these ordinary environment values in the container definition:

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
AWS_REGION=<aws-region>
COGNITO_USER_POOL_ID=<user-pool-id>
COGNITO_JWKS_URL=<cognito-jwks-url>
COGNITO_ISSUER=<cognito-issuer>
COGNITO_CLIENT_ID=<cognito-client-id>
WEALTH_WING_DATA_URL=<data-api-url>
WEALTH_WING_DATA_HEALTH_URL=<data-health-url>
```

Map `TOGETHER_API_KEY` from its Secrets Manager ARN through the task
definition's **Secrets** section rather than placing it in plaintext.

`ALLOWED_HOSTS=*` allows ALB health checks, whose Host header contains the
target's private IP. This is acceptable for this demo only when the task
security group permits inbound traffic exclusively from the ALB security
group. `FORWARDED_ALLOW_IPS=*` has the same network-boundary requirement.

## 5. Create networking and the load balancer

For this cost-conscious demo, place the task in public subnets and enable a
public IP so it can reach Cognito, Together, and other public HTTPS endpoints
without a NAT Gateway.

Use two security groups:

1. The ALB security group accepts public HTTPS on port 443. Port 80 may be used
   only to redirect HTTP to HTTPS.
2. The task security group accepts port 8000 only from the ALB security group.
   It must not accept port 8000 directly from the internet.

Create an internet-facing Application Load Balancer and an IP target group:

| Setting | Value |
| --- | --- |
| Target protocol and port | HTTP, `8000` |
| Health path | `/health/ping` |
| Healthy status | `200` |
| Health interval | 30 seconds |
| Health timeout | 5 seconds |
| Healthy threshold | 2 |
| Unhealthy threshold | 3 |

Attach the ACM certificate to the HTTPS listener and redirect HTTP traffic to
HTTPS. Set the ALB idle timeout to 300 seconds so multi-step agent requests are
not cut off by the default timeout. Point the API DNS record at the ALB.

## 6. Create the ECS service

Create a Fargate service using the task definition, public subnets, public IPs,
the task security group, and the ALB target group. Configure:

```text
Desired tasks: 1
Minimum tasks: 1
Maximum tasks: 1
Health-check grace period: 30 seconds
Autoscaling: disabled
```

Do not add tasks or workers while `InMemorySaver` is used. A deployment or task
replacement clears all conversation history, which is expected for this demo.

When a Secrets Manager value changes, force a new ECS deployment so new tasks
receive the updated environment value.

## 7. Verify the deployment

Confirm the following after the ECS target becomes healthy:

```bash
curl --fail "https://<api-domain>/health/ping"
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  "https://<api-domain>/agents/wing/invoke"
```

The health endpoint must return `200`; the protected endpoint without a bearer
token must return `401`. Then use the React application to verify Cognito login,
an authenticated agent request, and a follow-up request with the returned
`thread_id`. Confirm that structured request logs appear in CloudWatch and that
the task cannot be reached directly on port 8000.
