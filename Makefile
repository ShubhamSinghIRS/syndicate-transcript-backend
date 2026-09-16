# --- docker-compose (one file, docker-compose.yml, split into "dev" and "prod" profiles) ---
#
# ENV picks the profile (dev|prod, defaults to dev). SERVICE optionally scopes
# a command to one container (postgres, backend, postgres-dev, backend-dev) -
# leave it unset to act on the whole stack for that profile.
#
# Examples:
#   make up                              start the dev stack
#   make up ENV=prod                     start the prod stack
#   make up ENV=dev SERVICE=backend-dev  rebuild + (re)start just that container
#   make rm ENV=dev SERVICE=postgres-dev delete just that container
#   make down ENV=prod                   stop + remove the whole prod stack
#   make logs ENV=prod SERVICE=backend   tail logs for one container (all, if omitted)

.PHONY: up down rm logs ps check-compose-env

ENV ?= dev
SERVICE ?=
COMPOSE_ENV_FILE := $(if $(filter prod,$(ENV)),.env.production,.env.dev)

check-compose-env:
	@test -f "$(COMPOSE_ENV_FILE)" || { echo "ERROR: env file not found: $(COMPOSE_ENV_FILE)"; exit 1; }

up: check-compose-env
	docker compose --profile $(ENV) up -d --build $(SERVICE)

down:
	docker compose --profile $(ENV) down

rm:
	docker compose --profile $(ENV) rm -sf $(SERVICE)

logs:
	docker compose --profile $(ENV) logs -f $(SERVICE)

ps:
	docker compose --profile $(ENV) ps
