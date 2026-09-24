# AWS resources

| Resource | Document | Needed for |
| --- | --- | --- |
| S3 packet bucket | [packet-storage.md](packet-storage.md) | submit, today |
| Textract | [textract.md](textract.md) | submit, today |
| Bedrock model access | [bedrock-models.md](bedrock-models.md) | every model call |
| Bedrock Guardrails | [bedrock-guardrails.md](bedrock-guardrails.md) | every model call |
| Bedrock Knowledge Base | [bedrock-knowledge-base.md](bedrock-knowledge-base.md) | ask and citations |
| OpenSearch Serverless | [opensearch-serverless.md](opensearch-serverless.md) | backs the Knowledge Base |
| RDS PostgreSQL | [rds-postgres.md](rds-postgres.md) | the deployed database |
| Secrets Manager | [secrets-manager.md](secrets-manager.md) | the RDS master password |
| VPC networking | [vpc-networking.md](vpc-networking.md) | RDS and ECS live in it |
| IAM roles | [iam-roles.md](iam-roles.md) | every piece of compute |
| GitHub OIDC provider | [github-oidc.md](github-oidc.md) | CI without stored keys |
| CloudWatch Logs | [cloudwatch-logs.md](cloudwatch-logs.md) | logs from deployed compute |
| ECR | [ecr.md](ecr.md) | later, when images exist |
| ECS on Fargate | [ecs-fargate.md](ecs-fargate.md) | later, hosts the tool API |
| Application Load Balancer | [application-load-balancer.md](application-load-balancer.md) | later, fronts ECS |
| AgentCore Runtime | [agentcore-runtime.md](agentcore-runtime.md) | later, hosts the workflow |
| AgentCore Gateway | [agentcore-gateway.md](agentcore-gateway.md) | later, the MCP server |
| AgentCore Identity | [agentcore-identity.md](agentcore-identity.md) | later, verifies the caller |

The diagram of how they fit together is in
[architecture-diagram.md](architecture-diagram.md). The daily stop routine is in
[daily-shutdown.md](daily-shutdown.md).
