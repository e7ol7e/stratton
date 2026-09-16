# Docker Compose and VPS deployment

## Run locally

Install Docker with the Compose plugin (Docker Desktop with Linux containers on Windows). Start Docker before running these commands from the project directory.

Use your existing `.env` with `BOT_TOKEN`, or copy `.env.example` to `.env` and fill it in. Stop the locally running `uv run ...` bot before starting the container: Telegram allows only one polling instance per token.

```sh
docker compose up -d --build
docker compose logs -f --tail=100 bot
docker compose ps
```

The image installs dependencies using `uv sync --locked`; Python runs directly from that environment at runtime. The container runs as UID/GID `10001:10001`. On Linux, prepare the writable directories before starting:

```sh
mkdir -p data logs
sudo chown -R 10001:10001 data logs
```

`./data` and `./logs` are bind-mounted, so existing words and results in `data/vocabulary.sqlite3` are used immediately and survive container replacement. Compose fixes the database path to `/app/data/vocabulary.sqlite3`; a custom local `DATABASE_PATH` must be migrated to `data/vocabulary.sqlite3` before switching. `.env`, databases, logs and local virtual environments are excluded from the image.

The service restarts after failures and host reboots while Docker is running, unless explicitly stopped. No inbound ports or domain are needed: the bot uses outbound HTTPS long polling. FSM sessions still reset on restart. Logs rotate both in Docker and in `logs/bot.log`.

## Move to a Linux VPS

1. Install [Docker Engine and the Compose plugin](https://docs.docker.com/engine/install/) on the VPS and enable Docker at boot (`sudo systemctl enable --now docker` on systemd hosts).
2. Clone the public GitHub repository into a directory owned by your SSH user (no GitHub credentials required):

   ```sh
   git clone https://github.com/e7ol7e/stratton.git
   cd stratton
   ```
3. Stop the old bot before copying its database. For Compose, use `docker compose down`; for a terminal process, press Ctrl+C and wait for it to exit. This prevents overlapping polling and writes during the transfer.
4. Transfer `.env` privately over SSH/SCP and the entire `data/` directory, including any SQLite `-wal` or `-shm` files. If local `DATABASE_PATH` was customized, copy that database and its sidecar files into `data/` using the `vocabulary.sqlite3` filename prefix. Keep the old copy as a backup.
5. On the VPS, from the deployment directory:

   ```sh
   chmod 600 .env
   mkdir -p data logs
   sudo chown -R 10001:10001 data logs
   docker compose config --quiet
   docker compose up -d --build
   docker compose logs --tail=100 bot
   ```

6. Send `/start`, `/words` and `/stats` in Telegram to confirm the bot responds and your saved data arrived. Keep the old instance stopped.

## Operations

```sh
# Rebuild after source or lockfile updates
git pull --ff-only
docker compose up -d --build

# Stop and remove the container (host data and logs remain)
docker compose down

# Validate Compose without printing the interpolated token
docker compose config --quiet
```

For a simple consistent backup, run `docker compose stop bot`, archive the entire `data/` directory, then `docker compose start bot`. Restore with the bot stopped and reapply ownership to UID/GID 10001. Unfinished FSM sessions are not backed up.

References: [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/), [Compose service configuration](https://docs.docker.com/reference/compose-file/services/).
