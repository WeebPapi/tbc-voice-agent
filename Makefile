.PHONY: install dev test demo-reset

install:
	python -m pip install -e ".[dev]"
	cd apps/web && npm install

dev:
	powershell -ExecutionPolicy Bypass -File scripts/dev.ps1

test:
	powershell -ExecutionPolicy Bypass -File scripts/test.ps1

demo-reset:
	powershell -ExecutionPolicy Bypass -File scripts/demo-reset.ps1
