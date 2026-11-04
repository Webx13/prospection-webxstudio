SHELL := /bin/bash
.DEFAULT_GOAL := help

# Charge .env (s'il existe) et l'exporte vers les commandes lancées par make.
-include .env
export

COMPOSE := docker compose

.PHONY: help setup check-env db-up db-down db-reset migrate api web test test-api test-web lint up down

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

setup: ## Crée .env (mot de passe aléatoire) et installe les dépendances API + web
	@test -f .env || { pw=$$(openssl rand -hex 16) && sed "s/__GENERATE__/$$pw/g" .env.example > .env && echo ".env créé avec un mot de passe aléatoire"; }
	cd apps/api && uv sync
	cd apps/web && npm ci

check-env:
	@test -f .env || { echo "✗ .env manquant : lancez 'make setup'"; exit 1; }
	@if grep -q '__GENERATE__' .env; then echo "✗ .env contient encore __GENERATE__ : supprimez-le puis relancez 'make setup'"; exit 1; fi

db-up: check-env ## Démarre PostgreSQL (Docker) et crée la base de test
	$(COMPOSE) up -d --wait db
	@$(COMPOSE) exec -T db sh -c 'createdb -U "$$POSTGRES_USER" "$${POSTGRES_DB}_test" 2>&1 | grep -v "already exists" || true'

db-down: ## Arrête PostgreSQL (les données sont conservées)
	$(COMPOSE) stop db

db-reset: ## DESTRUCTIF : supprime le volume de données local (demande confirmation)
	@read -r -p "Supprimer définitivement les données PostgreSQL locales ? [y/N] " answer; \
	if [ "$$answer" = "y" ]; then $(COMPOSE) --profile full down -v; else echo "Annulé."; fi

migrate: check-env ## Applique les migrations Alembic sur la base de développement
	cd apps/api && uv run alembic upgrade head

api: check-env ## Lance l'API en natif avec rechargement (http://127.0.0.1:8000)
	cd apps/api && uv run uvicorn blackforge_api.main:create_app --factory --reload --no-server-header --host 127.0.0.1 --port 8000

web: ## Lance l'interface en natif (http://localhost:3000)
	cd apps/web && npm run dev

test: test-api test-web ## Lance tous les tests

test-api: db-up ## Tests de l'API (unitaires + intégration sur PostgreSQL réel)
	cd apps/api && uv run pytest

test-web: ## Tests de l'interface
	cd apps/web && npm test

lint: ## Lint + typage strict (API et web)
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd apps/web && npm run lint && npm run typecheck

up: check-env ## Lance toute la pile en conteneurs (db + migrations + api + web)
	$(COMPOSE) --profile full up --build

down: ## Arrête toute la pile
	$(COMPOSE) --profile full down
