SHELL         := /bin/bash
.DEFAULT_GOAL := help
AWS_REGION    ?= eu-west-1
TF_DIR        := terraform

.PHONY: help demo-up demo-down demo-verify ssm-populate

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# demo-up — provision AWS infrastructure and deploy the gateway image
# Requires: AWS credentials, Terraform, Docker, and secrets already in SSM.
# Time: ~8 minutes on first apply; ~2 minutes for updates.
# Cost: ~€0 while paused; ~€1 for a demo day.
# ---------------------------------------------------------------------------
demo-up: ## Provision AWS infra + deploy gateway (~8 min)
	@echo "==> Initialising Terraform"
	cd $(TF_DIR) && terraform init -input=false
	@echo "==> Applying ECR repository (image must exist before App Runner is created)"
	cd $(TF_DIR) && terraform apply -auto-approve -input=false \
		-target=aws_ecr_repository.gateway
	@echo "==> Building and pushing gateway image"
	$(MAKE) _build-and-push
	@echo "==> Applying remaining Terraform resources (App Runner, IAM, SSM, CloudWatch)"
	cd $(TF_DIR) && terraform apply -auto-approve -input=false
	@echo ""
	@echo "Gateway URL: $$(cd $(TF_DIR) && terraform output -raw app_runner_service_url)"
	@echo "Health:      $$(cd $(TF_DIR) && terraform output -raw app_runner_service_url)/health"

demo-down: ## Destroy all AWS resources (cost goes to ~€0)
	@echo "==> Running terraform destroy"
	cd $(TF_DIR) && terraform destroy -auto-approve -input=false
	@echo "==> Verifying teardown"
	$(MAKE) demo-verify

demo-verify: ## Verify no billable resources remain after teardown
	@echo "--- App Runner services ---"
	aws apprunner list-services --region $(AWS_REGION) \
		--query 'ServiceSummaryList[?contains(ServiceName, `mcp-agent-factory`)]' \
		--output table
	@echo "--- App Runner CloudWatch log group ---"
	aws logs describe-log-groups --region $(AWS_REGION) \
		--log-group-name-prefix /aws/apprunner/mcp-agent-factory \
		--query 'logGroups[*].logGroupName' \
		--output table
	@echo "==> Teardown verification complete."
	@echo "    Check Cost Explorer tomorrow (billing lag ~24h) with filter project=mcp-agent-factory"

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

_build-and-push:
	$(eval ECR_URL := $(shell cd $(TF_DIR) && terraform output -raw ecr_repository_url))
	$(eval AWS_ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(ECR_URL)
	docker build --platform linux/amd64 -t $(ECR_URL):latest .
	docker push $(ECR_URL):latest

_apprunner-deploy:
	$(eval SERVICE_ARN := $(shell cd $(TF_DIR) && terraform output -raw app_runner_service_arn))
	aws apprunner start-deployment \
		--service-arn $(SERVICE_ARN) \
		--region $(AWS_REGION)
	@echo "Deployment triggered. App Runner will pull the new image and route traffic after /health passes."
