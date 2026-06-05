.PHONY: up down logs migrate test test-unit test-integration security-scan build push k8s-deploy load-baselines create-admin simulate-drift

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

migrate:
	alembic upgrade head

test:
	pytest

test-unit:
	pytest -m "not integration"

test-integration:
	pytest tests/integration/

test-auto-baseline:
	pytest tests/integration/test_baseline_registrar.py -v

verify-grafana:
	@echo "Checking Grafana Health..."
	@curl -s -f http://localhost:3000/api/health || (echo "Grafana not ready" && exit 1)
	@echo "Checking Provisioned Dashboards..."
	@curl -s -f http://localhost:3000/api/search | grep "drift-ops-v1" > /dev/null || (echo "Dashboard not found" && exit 1)
	@echo "Grafana setup verified successfully."

security-scan:
	pip-audit
	bandit -r .
	safety check

build:
	docker-compose build

push:
	@echo "Pushing images..."

k8s-deploy:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/ -n drift-system

load-baselines:
	docker-compose exec drift-dashboard python scripts/load_baselines.py

create-admin:
	docker-compose exec -it drift-dashboard python scripts/create_admin_user.py

simulate-drift:
	python scripts/simulate_drift.py
