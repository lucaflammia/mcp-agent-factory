SHELL         := /bin/bash
.DEFAULT_GOAL := help
AWS_REGION    ?= eu-west-1
TF_DIR        := terraform

.PHONY: help demo-up demo-down demo-verify ssm-populate ssm-sync

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# demo-up — provision AWS infrastructure and deploy the gateway image
# Requires: AWS credentials, Terraform, Docker, and secrets already in SSM.
# Time: ~5 minutes on first apply; ~2 minutes for updates.
# Cost: ~€25/month (ALB + Fargate always-on). Run demo-down after each session.
# ---------------------------------------------------------------------------
demo-up: ## Provision AWS infra + deploy gateway (~5 min)
	@echo "==> Building Lambda deployment package"
	$(MAKE) _build-lambda-package
	@echo "==> Initialising Terraform"
	cd $(TF_DIR) && terraform init -input=false
	@echo "==> Applying ECR repository (image must exist before ECS task definition is created)"
	cd $(TF_DIR) && terraform apply -auto-approve -input=false \
		-target=aws_ecr_repository.gateway
	@echo "==> Building and pushing gateway image"
	$(MAKE) _build-and-push
	@echo "==> Syncing secrets from .env into SSM"
	$(MAKE) ssm-sync
	@echo "==> Applying remaining Terraform resources (ECS, ALB, IAM, CloudWatch)"
	cd $(TF_DIR) && terraform apply -auto-approve -input=false
	@echo ""
	@echo "Gateway URL: $$(cd $(TF_DIR) && terraform output -raw gateway_url)"
	@echo "Health:      $$(cd $(TF_DIR) && terraform output -raw gateway_url)/health"

demo-down: ## Destroy all AWS resources (stops ALB + Fargate charges)
	@echo "==> Running terraform destroy"
	cd $(TF_DIR) && terraform destroy -auto-approve -input=false
	@echo "==> Verifying teardown"
	$(MAKE) demo-verify

demo-verify: ## Verify no billable resources remain after teardown
	@echo "--- ECS services ---"
	aws ecs list-services --region $(AWS_REGION) --cluster mcp-agent-factory \
		--query 'serviceArns' --output table 2>/dev/null || echo "  (cluster not found)"
	@echo "--- ALBs ---"
	aws elbv2 describe-load-balancers --region $(AWS_REGION) \
		--query 'LoadBalancers[?contains(LoadBalancerName, `mcp-agent-factory`)].LoadBalancerName' \
		--output table
	@echo "--- CloudWatch log group ---"
	aws logs describe-log-groups --region $(AWS_REGION) \
		--log-group-name-prefix /ecs/mcp-agent-factory \
		--query 'logGroups[*].logGroupName' \
		--output table
	@echo "--- ElastiCache clusters ---"
	aws elasticache describe-cache-clusters --region $(AWS_REGION) \
		--query 'CacheClusters[?contains(CacheClusterId, `mcp-agent-factory`)].{Id:CacheClusterId,Status:CacheClusterStatus}' \
		--output table
	@echo "--- Step Functions state machines ---"
	aws stepfunctions list-state-machines --region $(AWS_REGION) \
		--query 'stateMachines[?contains(name, `mcp-agent-factory`)].{Name:name,Status:status}' \
		--output table
	@echo "--- Lambda functions ---"
	aws lambda list-functions --region $(AWS_REGION) \
		--query 'Functions[?contains(FunctionName, `mcp-agent-factory`)].FunctionName' \
		--output table
	@echo "--- SSM parameters ---"
	aws ssm describe-parameters --region $(AWS_REGION) \
		--parameter-filters "Key=Name,Option=BeginsWith,Values=/mcp-agent-factory/" \
		--query 'Parameters[*].Name' \
		--output table 2>/dev/null || echo "  (none found)"
	@echo "==> Teardown verification complete."
	@echo "    Check Cost Explorer tomorrow (billing lag ~24h) with filter project=mcp-agent-factory"

ssm-sync: ## Sync secrets from .env into SSM (runs automatically in demo-up)
	@if [ ! -f .env ]; then echo "ERROR: .env not found — copy .env.example and fill in values"; exit 1; fi
	@set -a && source .env && set +a && \
	_ssm_put() { \
		aws ssm put-parameter --region $(AWS_REGION) \
			--name "/mcp-agent-factory/$$1" --value "$$2" \
			--type SecureString --overwrite --query Version --output text > /dev/null && \
		echo "  /mcp-agent-factory/$$1 updated"; \
	}; \
	_ssm_put gemini-api-key   "$$GEMINI_API_KEY"; \
	_ssm_put database-url     "$${NEON_CONNECTION_STRING:-$$DATABASE_URL}"; \
	_ssm_put redis-url        "$${UPSTASH_REDIS_URL:-$$REDIS_URL}"; \
	_ssm_put jwt-secret       "$$JWT_SECRET"; \
	_ssm_put otel-endpoint    "$$OTEL_EXPORTER_OTLP_ENDPOINT"; \
	_ssm_put otel-headers     "$$OTEL_EXPORTER_OTLP_HEADERS"
	@echo "  SSM sync complete."

ssm-populate: ## Interactively populate SSM SecureString parameters (run once after demo-up)
	@echo "Setting SSM parameters for mcp-agent-factory..."
	@read -s -p "GEMINI_API_KEY: " v && aws ssm put-parameter \
		--name /mcp-agent-factory/gemini-api-key --value "$$v" \
		--type SecureString --overwrite --region $(AWS_REGION) && echo " OK"
	@read -s -p "DATABASE_URL (Neon): " v && aws ssm put-parameter \
		--name /mcp-agent-factory/database-url --value "$$v" \
		--type SecureString --overwrite --region $(AWS_REGION) && echo " OK"
	@read -s -p "REDIS_URL (Upstash): " v && aws ssm put-parameter \
		--name /mcp-agent-factory/redis-url --value "$$v" \
		--type SecureString --overwrite --region $(AWS_REGION) && echo " OK"
	@read -s -p "JWT_SECRET (run: openssl rand -hex 32): " v && aws ssm put-parameter \
		--name /mcp-agent-factory/jwt-secret --value "$$v" \
		--type SecureString --overwrite --region $(AWS_REGION) && echo " OK"
	@read -s -p "OTEL_EXPORTER_OTLP_ENDPOINT (Grafana Cloud): " v && aws ssm put-parameter \
		--name /mcp-agent-factory/otel-endpoint --value "$$v" \
		--type SecureString --overwrite --region $(AWS_REGION) && echo " OK"
	@read -s -p "OTEL_EXPORTER_OTLP_HEADERS (Authorization=Basic ...): " v && aws ssm put-parameter \
		--name /mcp-agent-factory/otel-headers --value "$$v" \
		--type SecureString --overwrite --region $(AWS_REGION) && echo " OK"
	@echo "All secrets stored."

# ---------------------------------------------------------------------------
# Internal helpers (not part of the public interface)
# ---------------------------------------------------------------------------

_build-lambda-package:
	bash $(TF_DIR)/build_lambda_package.sh

_build-and-push:
	$(eval ECR_URL := $(shell cd $(TF_DIR) && terraform output -raw ecr_repository_url))
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(ECR_URL)
	docker build --platform linux/amd64 --build-arg EXTRAS=infra,otel -t $(ECR_URL):latest .
	docker push $(ECR_URL):latest
