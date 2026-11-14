# AWS Services Health Check

Operational reference for manually verifying all infrastructure components after deployment.

**Account:** `195613527809` · **Region:** `eu-west-1`

---

## Prerequisites

Confirm the AWS CLI is authenticated to the right account:

```bash
aws sts get-caller-identity --query '[Account,Arn]'
```

---

## ElastiCache Redis

```bash
aws elasticache describe-cache-clusters \
  --cache-cluster-id mcp-agent-factory \
  --region eu-west-1 \
  --show-cache-node-info \
  --query 'CacheClusters[0].[CacheClusterStatus,Engine,EngineVersion,CacheNodes[0].Endpoint]'
```

Healthy state: `available`, engine `redis 7.x`, endpoint DNS populated.

To retrieve just the endpoint:

```bash
aws elasticache describe-cache-clusters \
  --cache-cluster-id mcp-agent-factory \
  --region eu-west-1 \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint'
```

---

## ECS Gateway Service

Check the task definition:

```bash
aws ecs describe-task-definition \
  --task-definition mcp-agent-factory-gateway \
  --region eu-west-1 \
  --query 'taskDefinition.[family,revision,status]'
```

Check running tasks:

```bash
aws ecs list-tasks \
  --cluster mcp-agent-factory \
  --service-name mcp-agent-factory-gateway \
  --region eu-west-1 \
  --desired-status RUNNING
```

At least one task ARN should appear. Tasks that cycle repeatedly (short uptime) indicate a crash loop — read the logs below to diagnose.

---

## Application Load Balancer

Check ALB state:

```bash
aws elbv2 describe-load-balancers \
  --names mcp-agent-factory \
  --region eu-west-1 \
  --query 'LoadBalancers[0].[DNSName,State.Code]'
```

Healthy state: `active`. Use the `DNSName` to probe the service:

```bash
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names mcp-agent-factory \
  --region eu-west-1 \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

curl -I http://$ALB_DNS/health
curl -I http://$ALB_DNS/openapi.json
```

Both should return `200 OK`.

---

## Lambda Worker

```bash
aws lambda get-function \
  --function-name mcp-agent-factory-pipeline-worker \
  --region eu-west-1 \
  --query 'Configuration.[State,Runtime,Handler,LastModified]'
```

Healthy state: `Active`, runtime `python3.11`, handler `sfn_worker.handler`.

---

## Step Functions State Machine

```bash
aws stepfunctions describe-state-machine \
  --state-machine-arn arn:aws:states:eu-west-1:195613527809:stateMachine:mcp-agent-factory-fleet \
  --region eu-west-1 \
  --query '[Name,Status,Type]'
```

Healthy state: `ACTIVE`, type `STANDARD`.

Recent execution summary:

```bash
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:eu-west-1:195613527809:stateMachine:mcp-agent-factory-fleet \
  --region eu-west-1 \
  --max-items 5 \
  --query 'executions[*].[status,startDate,name]'
```

---

## ECR Repository

```bash
aws ecr describe-repositories \
  --repository-names mcp-agent-factory/gateway \
  --region eu-west-1 \
  --query 'repositories[0].[repositoryUri,createdAt]'
```

Recent images:

```bash
aws ecr list-images \
  --repository-name mcp-agent-factory/gateway \
  --region eu-west-1 \
  --query 'imageIds[*].imageTag' \
  --max-items 5
```

---

## IAM

GitHub OIDC provider (required for CI):

```bash
aws iam list-open-id-connect-providers \
  --query 'OpenIDConnectProviderList[*].Arn' | grep github
```

CI role:

```bash
aws iam get-role \
  --role-name mcp-agent-factory-ci \
  --query 'Role.[RoleName,Arn]'
```

Lambda execution role:

```bash
aws iam get-role \
  --role-name mcp-agent-factory-lambda-worker \
  --query 'Role.Arn'
```

---

## SSM Parameters

```bash
aws ssm get-parameters-by-path \
  --path /mcp-agent-factory \
  --region eu-west-1 \
  --query 'Parameters[*].[Name,Type]'
```

All parameters under `/mcp-agent-factory/` should be present. Use `--with-decryption` only if you need to read `SecureString` values for debugging.

---

## Security Groups

Gateway security group (ingress on 8000 from ALB):

```bash
aws ec2 describe-security-groups \
  --filters Name=group-name,Values=mcp-agent-factory-gateway \
  --region eu-west-1 \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,ToPort]'
```

Redis security group (ingress on 6379 from gateway SG):

```bash
aws ec2 describe-security-groups \
  --filters Name=group-name,Values=mcp-agent-factory-redis \
  --region eu-west-1 \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,UserIdGroupPairs[0].GroupId]'
```

---

## CloudWatch Logs

Lambda logs:

```bash
aws logs tail /aws/lambda/mcp-agent-factory-pipeline-worker \
  --follow \
  --region eu-west-1
```

ECS gateway logs:

```bash
aws logs tail /ecs/mcp-agent-factory-gateway \
  --follow \
  --region eu-west-1
```

---

## End-to-End Smoke Test

After confirming the services above are healthy, submit a test job through the gateway:

```bash
JOB=$(curl -s -X POST http://$ALB_DNS/mcp/jobs \
  -H "Content-Type: application/json" \
  -d '{"tools": ["web_search"], "query": "ping"}' \
  | jq -r '.job_id')

echo "Job ID: $JOB"

for i in {1..30}; do
  STATUS=$(curl -s http://$ALB_DNS/mcp/jobs/$JOB | jq -r '.status')
  echo "[$i] $STATUS"
  [ "$STATUS" = "done" ] || [ "$STATUS" = "failed" ] && break
  sleep 2
done

curl -s http://$ALB_DNS/mcp/jobs/$JOB | jq .
```

The job should reach `done` or `failed` within 30–60 seconds.

---

**See also:** [`STEP-FUNCTIONS-VERIFICATION.md`](STEP-FUNCTIONS-VERIFICATION.md) · [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
