#!/usr/bin/env python3
"""pg_dump → gzip → S3 backup script.

Usage (from the project root on the host):
    python scripts/backup_db.py

Two dump modes — controlled by BACKUP_MODE env var:

  docker  (default for this project)
    Runs pg_dump inside the db container via `docker compose exec`.
    Requires `docker` on the host. No pg_dump binary needed on the host.
    Set BACKUP_COMPOSE_PROJECT to the Compose project name if it differs
    from the directory name (default: ekorepetycje).

  direct
    Calls `pg_dump` directly. Use this when PostgreSQL is installed
    natively on the host (bare-metal) or when running inside the db
    container itself.

Configuration (env vars — sourced automatically from .env if present):

  S3 (required for upload):
    BACKUP_S3_BUCKET        e.g. my-ekorepetycje-backups
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION      e.g. eu-central-1

  Optional:
    BACKUP_MODE             docker | direct  (default: docker)
    BACKUP_COMPOSE_PROJECT  Compose project name  (default: ekorepetycje)
    BACKUP_S3_PREFIX        prefix inside the bucket  (default: ekorepetycje/db)
    BACKUP_RETAIN_DAYS      days of backups to keep in S3  (default: 30, 0=keep all)
    BACKUP_LOCAL_DIR        if set, also save a local copy here

  Postgres connection (used in 'direct' mode):
    POSTGRES_HOST           (default: localhost)
    POSTGRES_PORT           (default: 5432)
    POSTGRES_DB             (default: ekorepetycje)
    POSTGRES_USER           (default: postgres)
    POSTGRES_PASSWORD

Cron example (daily at 03:00, host user that can run docker):
    0 3 * * * cd /opt/ekorepetycje && /usr/bin/python3 scripts/backup_db.py >> /var/log/eko-backup.log 2>&1
"""

import gzip
import io
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"ERROR: {msg}")
    sys.exit(1)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# ── load .env early (before reading config) ───────────────────────────────────

def _load_dotenv() -> None:
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


# ── configuration ─────────────────────────────────────────────────────────────

BACKUP_MODE    = _env("BACKUP_MODE", "docker")          # "docker" | "direct"
COMPOSE_PROJECT = _env("BACKUP_COMPOSE_PROJECT", "ekorepetycje")

S3_BUCKET      = _env("BACKUP_S3_BUCKET")
S3_PREFIX      = _env("BACKUP_S3_PREFIX", "ekorepetycje/db").rstrip("/")
RETAIN_DAYS    = int(_env("BACKUP_RETAIN_DAYS", "30"))
LOCAL_DIR      = _env("BACKUP_LOCAL_DIR")

PG_HOST        = _env("POSTGRES_HOST", "localhost")
PG_PORT        = _env("POSTGRES_PORT", "5432")
PG_DB          = _env("POSTGRES_DB", "ekorepetycje")
PG_USER        = _env("POSTGRES_USER", "postgres")
PG_PASSWORD    = _env("POSTGRES_PASSWORD")

TIMESTAMP      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
FILENAME       = f"backup-{TIMESTAMP}.sql.gz"
S3_KEY         = f"{S3_PREFIX}/{FILENAME}"


# ── dump ──────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], env: dict | None = None) -> bytes:
    result = subprocess.run(cmd, env=env, capture_output=True)
    if result.returncode != 0:
        die(f"Command failed (exit {result.returncode}):\n{result.stderr.decode()}")
    return result.stdout


def run_pg_dump() -> bytes:
    if BACKUP_MODE == "docker":
        return _dump_via_docker()
    return _dump_direct()


def _dump_via_docker() -> bytes:
    """Run pg_dump inside the db container via docker compose exec."""
    log(f"Mode: docker — running pg_dump inside '{COMPOSE_PROJECT}-db-1' container …")

    # Build the pg_dump command that runs *inside* the container
    inner_cmd = [
        "pg_dump",
        "--username", PG_USER,
        "--no-password",
        "--format", "plain",
        PG_DB,
    ]
    # Pass the password via PGPASSWORD env inside the container
    env_flag = ["-e", f"PGPASSWORD={PG_PASSWORD}"] if PG_PASSWORD else []

    cmd = [
        "docker", "compose",
        "--project-name", COMPOSE_PROJECT,
        "exec", "-T",           # -T: no pseudo-TTY (required for piping)
        *env_flag,
        "db",
        *inner_cmd,
    ]

    data = _run(cmd)
    log(f"Dump complete — {len(data):,} bytes raw SQL")
    return data


def _dump_direct() -> bytes:
    """Call pg_dump directly (bare-metal or inside the db container)."""
    log(f"Mode: direct — running pg_dump on {PG_HOST}:{PG_PORT}/{PG_DB} …")

    env = os.environ.copy()
    if PG_PASSWORD:
        env["PGPASSWORD"] = PG_PASSWORD

    cmd = [
        "pg_dump",
        "--host", PG_HOST,
        "--port", PG_PORT,
        "--username", PG_USER,
        "--no-password",
        "--format", "plain",
        PG_DB,
    ]

    data = _run(cmd, env=env)
    log(f"Dump complete — {len(data):,} bytes raw SQL")
    return data


def compress(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
        gz.write(data)
    compressed = buf.getvalue()
    ratio = len(compressed) / len(data) * 100
    log(f"Compressed to {len(compressed):,} bytes ({ratio:.1f}% of original)")
    return compressed


# ── local save (optional) ─────────────────────────────────────────────────────

def save_local(data: bytes) -> None:
    dest = Path(LOCAL_DIR) / FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    log(f"Saved locally → {dest}")


# ── S3 upload + retention ─────────────────────────────────────────────────────

def upload_s3(data: bytes) -> None:
    try:
        import boto3
    except ImportError:
        die("boto3 not installed — run: pip install boto3")

    s3 = boto3.client("s3")
    log(f"Uploading to s3://{S3_BUCKET}/{S3_KEY} …")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=S3_KEY,
        Body=data,
        ContentType="application/gzip",
        Metadata={"db": PG_DB, "source-host": PG_HOST},
    )
    log(f"Upload complete → s3://{S3_BUCKET}/{S3_KEY}")


def prune_s3() -> None:
    if RETAIN_DAYS <= 0:
        return
    try:
        import boto3
    except ImportError:
        return

    s3 = boto3.client("s3")
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETAIN_DAYS)
    paginator = s3.get_paginator("list_objects_v2")
    to_delete = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff:
                to_delete.append({"Key": obj["Key"]})

    if not to_delete:
        log(f"Retention: no backups older than {RETAIN_DAYS} days to remove")
        return

    s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": to_delete, "Quiet": True})
    log(f"Retention: removed {len(to_delete)} backup(s) older than {RETAIN_DAYS} days")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log(f"=== Ekorepetycje DB backup — {TIMESTAMP} ===")

    if not S3_BUCKET and not LOCAL_DIR:
        die(
            "No destination configured.\n"
            "  Set BACKUP_S3_BUCKET for S3 upload,\n"
            "  and/or BACKUP_LOCAL_DIR for local save."
        )

    raw  = run_pg_dump()
    data = compress(raw)

    if LOCAL_DIR:
        save_local(data)

    if S3_BUCKET:
        upload_s3(data)
        prune_s3()

    log("=== Backup finished successfully ===")


if __name__ == "__main__":
    main()
