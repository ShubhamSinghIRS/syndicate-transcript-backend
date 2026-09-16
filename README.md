# Syndicate Transcript Backend

FastAPI backend, running on Postgres via SQLAlchemy/Alembic.

## Environment files

None of these are committed - each is gitignored, and you create your own copy locally / on the server. [env.example](env.example) documents every variable.

| File | Used by |
|---|---|
| `.env` | Running the app directly (no Docker), e.g. `uvicorn main:app` from a venv - auto-loaded by `python-dotenv`. |
| `.env.dev` | The `dev` Docker Compose profile. |
| `.env.production` | The `prod` Docker Compose profile. |

To set one up: copy `env.example` to the target filename and fill in real values. For a Compose profile, also set `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`, and point `DATABASE_URL` at the `postgres` service host, e.g.:
```
DATABASE_URL=postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@postgres:5432/<POSTGRES_DB>
```

## Running with Docker Compose

[docker-compose.yml](docker-compose.yml) defines one stack per environment - `dev` (its own Postgres container, port 5432 open on the host for local DB clients) and `prod` (hardened Postgres container, backend bound to `127.0.0.1:8000` only, meant to sit behind a reverse proxy). Pick which one runs with `ENV`; `SERVICE` optionally scopes a command to a single container (`postgres`, `backend`, `postgres-dev`, `backend-dev`).

```
make up                              # start the dev stack (default)
make up ENV=prod                     # start the prod stack
make up ENV=dev SERVICE=backend-dev  # rebuild + (re)start just one container
make down ENV=prod                   # stop and remove the whole prod stack
make rm ENV=dev SERVICE=postgres-dev # delete just one container
make logs ENV=dev SERVICE=backend-dev
make ps ENV=prod
```

Every container start runs `alembic upgrade head` automatically before the server starts (see [entrypoint.sh](entrypoint.sh)).

## Deploying to a fresh server (e.g. Linode)

1. Install Docker: `curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER` (log back in afterwards).
2. `git clone <repo-url> && cd syndicate-transcript-backend`
3. Create `.env.production` on the server (see the table above - it never comes from git) with real production values.
4. `make up ENV=prod`
5. `make logs ENV=prod` - confirm every migration ran and you see `Uvicorn running on http://0.0.0.0:8000`.

The backend only listens on `127.0.0.1:8000` in the `prod` profile - put a reverse proxy (Nginx/Caddy) with a TLS certificate in front of it as the public listener; nothing binds it to the internet directly.

## Storage

Postgres data:
- `dev` - a Docker-managed volume (`pgdata_dev`).
- `prod` - bind-mounted to `/mnt/postgres-data` on the host. Create that path (and put it on its own sized volume if you want disk usage capped) before the first `make up ENV=prod`. Check actual usage with `docker exec syndicate-postgres du -sh /var/lib/postgresql/data`.
