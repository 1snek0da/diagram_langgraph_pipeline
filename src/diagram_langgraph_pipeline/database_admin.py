"""PostgreSQL diagnostics and checksum-protected schema migrations."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import socket
from urllib.parse import urlparse

from .runtime_config import PROJECT_ROOT, mask_dsn


class DatabaseSetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseDiagnostic:
    ok: bool
    configured_dsn: str
    message: str
    suggested_port: int | None = None


def diagnose_database(dsn: str) -> DatabaseDiagnostic:
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), inet_server_port()")
                database, port = cursor.fetchone()
        return DatabaseDiagnostic(
            True,
            mask_dsn(dsn),
            f"已连接数据库 {database}（端口 {port}）",
        )
    except Exception as exc:
        parsed = urlparse(dsn)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        suggested = None
        if host in {"localhost", "127.0.0.1", "::1"} and port != 5432:
            try:
                with socket.create_connection(("127.0.0.1", 5432), timeout=0.5):
                    suggested = 5432
            except OSError:
                pass
        suffix = (
            f"；检测到本机 PostgreSQL 可能监听 {suggested}，而配置为 {port}"
            if suggested
            else ""
        )
        return DatabaseDiagnostic(
            False,
            mask_dsn(dsn),
            f"数据库连接失败（{type(exc).__name__}）{suffix}",
            suggested,
        )


def apply_migrations(dsn: str, root: Path = PROJECT_ROOT) -> list[str]:
    """Apply the base schema when empty, then all ordered migrations.

    Every migration is checksum protected. Existing databases without a ledger
    are safely adopted because migrations are written to be idempotent.
    """

    try:
        import psycopg
    except ImportError as exc:
        raise DatabaseSetupError('请安装 PostgreSQL 支持：pip install -e ".[postgres]"') from exc

    schema = root / "database" / "schema.sql"
    migrations = sorted((root / "database" / "migrations").glob("*.sql"))
    applied: list[str] = []
    try:
        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.analysis_runs')")
                if cursor.fetchone()[0] is None:
                    cursor.execute(schema.read_text(encoding="utf-8-sig"))
                    applied.append(schema.name)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(64) PRIMARY KEY,
                        filename TEXT NOT NULL,
                        checksum CHAR(64) NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                for path in migrations:
                    version = path.name.split("_", 1)[0]
                    sql = path.read_text(encoding="utf-8-sig")
                    checksum = sha256(sql.encode("utf-8")).hexdigest()
                    cursor.execute(
                        "SELECT checksum FROM schema_migrations WHERE version=%s",
                        (version,),
                    )
                    row = cursor.fetchone()
                    if row:
                        if row[0] != checksum:
                            raise DatabaseSetupError(
                                f"迁移 {version} 的校验和已变化，已阻止升级"
                            )
                        continue
                    # Migration files contain their own BEGIN/COMMIT in older
                    # releases. Remove only those boundary lines so the whole
                    # upgrade remains in this connection transaction.
                    body = "\n".join(
                        line for line in sql.splitlines()
                        if line.strip().upper() not in {"BEGIN;", "COMMIT;"}
                    )
                    cursor.execute(body)
                    cursor.execute(
                        "INSERT INTO schema_migrations(version,filename,checksum) VALUES (%s,%s,%s)",
                        (version, path.name, checksum),
                    )
                    applied.append(path.name)
    except DatabaseSetupError:
        raise
    except Exception as exc:
        raise DatabaseSetupError(f"数据库初始化失败：{type(exc).__name__}: {exc}") from exc
    return applied
