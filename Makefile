# Ontos dev convenience targets.
#   make dev       — run the full local stack (backend :8000 + frontend :3000); Ctrl+C stops both
#   make backend   — backend only (FastAPI/uvicorn, --reload)
#   make frontend  — frontend only (Vite)
# Logs are tee'd to /tmp/backend.log and /tmp/frontend.log while also printing to the terminal.

.PHONY: dev backend frontend

dev:
	@echo "Starting Ontos dev stack — backend :8000, frontend :3000  (Ctrl+C stops both)"
	@trap 'kill 0' EXIT INT TERM; \
	( cd src && hatch -e dev run dev-backend 2>&1 | tee /tmp/backend.log ) & \
	( cd src/frontend && yarn dev:frontend 2>&1 | tee /tmp/frontend.log ) & \
	wait

backend:
	cd src && hatch -e dev run dev-backend

frontend:
	cd src/frontend && yarn dev:frontend
