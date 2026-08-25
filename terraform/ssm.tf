# ---------------------------------------------------------------------------
# SSM Parameter Store — parameters are created and managed by `make ssm-sync`,
# NOT by Terraform. Terraform only needs the IAM role (in iam.tf) to grant
# App Runner read access. Values are never committed to the repo.
#
# To manually set or update a parameter:
#   make ssm-sync           # reads all values from .env
# Or individually:
#   aws ssm put-parameter --name /mcp-agent-factory/redis-url \
#     --value "rediss://..." --type SecureString --overwrite
# ---------------------------------------------------------------------------
