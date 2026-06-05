dev:
	docker compose up --build

up:
	docker compose up -d

reload:
	docker compose restart thor-vision

logs:
	docker compose logs -f thor-vision

build:
	docker compose build

down:
	docker compose down

status:
	docker compose ps
	@echo ""
	@curl -s http://localhost:8080/api/health | python3 -m json.tool 2>/dev/null || echo "Service not responding"

cameras:
	@curl -s http://localhost:8080/api/cameras | python3 -m json.tool

clean:
	docker compose down --rmi local -v
