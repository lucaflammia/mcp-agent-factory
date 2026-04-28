---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T02: Create Prometheus scrape config and Grafana provisioning

Create observability/prometheus.yml with a scrape job for gateway:8000/metrics. Create observability/grafana/datasources/prometheus.yml pointing at prometheus:9090. Create observability/grafana/dashboards/dashboard.yml provisioning config. Create a minimal starter dashboard JSON.

## Inputs

- None specified.

## Expected Output

- `observability/ directory with prometheus.yml and grafana/ subtree`

## Verification

All files exist and are valid YAML/JSON
