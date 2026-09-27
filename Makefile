.PHONY: help build up down restart logs test test-local clean

help:
	@echo "Comandos disponíveis no MVP de Trading de Grãos:"
	@echo "  make build      - Constrói as imagens Docker"
	@echo "  make up         - Sobe os serviços (Dashboard Streamlit :8501 e API FastAPI :8000)"
	@echo "  make down       - Encerra os containers"
	@echo "  make restart    - Reinicia os containers"
	@echo "  make logs       - Visualiza os logs dos containers"
	@echo "  make test       - Executa a suite de testes no container"
	@echo "  make clean      - Limpa volumes e containers não utilizados"

build:
	docker compose build

up:
	docker compose up -d
	@echo "Dashboard disponível em: http://localhost:8501"
	@echo "API e Swagger Docs em:   http://localhost:8000/docs"

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest -v

clean:
	docker compose down -v --remove-orphans
