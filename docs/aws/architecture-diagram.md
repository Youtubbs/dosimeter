# How the AWS resources fit together

```mermaid
flowchart TB
    officer["Radiation safety officer"]
    cli["dosimeter CLI<br/>(the application)"]

    subgraph ingest["Ingestion, at submit"]
        s3["S3 packet bucket<br/>content-addressed artifacts"]
        textract["Textract<br/>async FORMS and TABLES"]
    end

    subgraph models["Bedrock"]
        bedrock["Model access<br/>reasoning, fast, embedding,<br/>multimodal, judge"]
        guardrails["Guardrails<br/>content filters and prompt attacks"]
        kb["Knowledge Base<br/>doc_type, section_path, status"]
    end

    subgraph store["Persistence"]
        rds["RDS PostgreSQL + pgvector<br/>records, queue, run records,<br/>graph checkpoints"]
    end

    subgraph deploy["Deployment, later"]
        ecr["ECR<br/>two images, deploy by digest"]
        runtime["AgentCore Runtime<br/>hosts the LangGraph workflow"]
        gateway["AgentCore Gateway<br/>read tools, passthrough"]
        kbgateway["AgentCore Gateway<br/>KB connector"]
        identity["AgentCore Identity<br/>Cognito verifies the caller"]
        tools["AgentCore Runtime<br/>MCP read tools,<br/>entitlement check per call"]
        ecs["ECS Fargate<br/>Flask tool API, optional"]
    end

    subgraph ops["Account guardrails"]
        iam["IAM roles<br/>no long-lived keys"]
        oidc["GitHub OIDC provider<br/>CI assumes a role"]
        logs["CloudWatch Logs"]
    end

    officer --> cli
    cli --> s3
    s3 --> textract
    textract --> cli
    cli --> guardrails
    cli --> bedrock
    cli --> kb
    cli --> rds
    cli --> api["Flask tool API<br/>entitlement check per call"]
    api --> rds

    cli -.->|"later"| gateway
    gateway -.-> identity
    gateway -.-> tools
    tools -.-> rds
    kbgateway -.-> kb
    ecr -.-> ecs
    ecr -.-> runtime
    ecr -.-> tools
    runtime -.-> gateway
    runtime -.-> kbgateway
    oidc -.-> ecr

    iam -.- cli
    iam -.- ecs
    iam -.- runtime
    iam -.- tools
    logs -.- runtime
    logs -.- tools
```
