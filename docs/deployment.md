# Deploying the tool API

The image, the registry, the cluster and the load balancer. Nothing here is
automated and nothing was created for you: these are the steps to run, in
us-east-1, with the three standard tags at creation.

| Key | Value |
| --- | --- |
| BatchID | the value ITOps gave the team |
| CreatedBy | asherrell |
| Purpose | dosimeter-tool-api |

## 1. The image

[Dockerfile](../Dockerfile) is two stages: a build stage that produces a wheel,
and a runtime stage that installs it and drops to a non-root user. The base
image is pinned by digest rather than by tag, so a rebuild next week is the
same base as today.

Build and run it locally first. The same image is the compose stand-in, so this
is also how you check it before it ever reaches AWS:

    docker compose up -d --build
    curl http://localhost:8080/health/ready

## 2. ECR

    aws ecr create-repository --repository-name dosimeter-api --image-scanning-configuration scanOnPush=true --region us-east-1

Log in, tag, push, then read back the digest. Deployments reference the digest,
never the tag, so a deployment names exactly one image:

    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
    docker build -t ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/dosimeter-api:latest .
    docker push ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/dosimeter-api:latest
    aws ecr describe-images --repository-name dosimeter-api --region us-east-1 --query "imageDetails[0].imageDigest"

## 3. Roles

Two roles, both tagged:

- `dosimeter-ecs-execution` pulls from ECR and writes container startup logs.
- `dosimeter-ecs-task` is what the code runs as. It needs `rds-db:connect` on
  `arn:aws:rds-db:us-east-1:ACCOUNT:dbuser:RESOURCE-ID/dosimeter_app` and
  CloudWatch Logs. No access keys, and no database password anywhere.

## 4. The cluster, the task and the service

1. ECS console > Clusters > Create cluster: `dosimeter`, Fargate.
2. Task definition:
   - Image: the ECR reference **by digest**, not `:latest`
   - CPU 0.5 vCPU, memory 1 GB, port 8080
   - Task role and execution role from step 3
   - Log configuration: awslogs into `/dosimeter/api`
   - Environment: `DOSIMETER_DB_*` pointing at RDS with
     `DOSIMETER_DB_USE_IAM_AUTH=true`, plus the Bedrock and bucket settings
3. Service:
   - Desired count 2, so one task restarting does not take the API down
   - Private subnets, security group `dosimeter-api-sg`
   - Attached to the load balancer target group from step 5
   - Auto scaling on CPU at around 60 percent, or on request count per target

## 5. The load balancer

1. EC2 console > Load balancers > Create > Application Load Balancer, internet
   facing, public subnets, security group `dosimeter-alb-sg`.
2. Target group: IP targets, port 8080, health check path **`/health/ready`**,
   which is the endpoint that actually opens a database connection. Healthy
   threshold 2, interval 15 seconds.
3. Listener forwarding to that target group.

Confirm both tasks are healthy and screenshot it for the process artifacts:

    aws elbv2 describe-target-health --target-group-arn ARN --region us-east-1

Then point the tool clients at the load balancer:

    DOSIMETER_TOOL_API_BASE_URL=https://dosimeter-alb-REPLACE.us-east-1.elb.amazonaws.com

## 6. Scale it to zero when you are not testing

Two idle Fargate tasks plus a load balancer bill all night:

    aws ecs update-service --cluster dosimeter --service dosimeter-api --desired-count 0 --region us-east-1

Bring it back with `--desired-count 2`. The daily routine is in
[aws/daily-shutdown.md](aws/daily-shutdown.md).

## Rolling back

Deployments reference a digest, so a rollback is a task definition revision
pointing at the previous digest, then updating the service to that revision.
Keep the previous digest in the pull request that deployed it.
