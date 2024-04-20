from pathlib import Path

from psycopg import AsyncConnection

from m2rss.constants import LOGGER, PROJECT_DIR


def migration_order() -> list[Path]:
    migration_dir = PROJECT_DIR / "migrations"
    migrations: list[Path] = []
    for file in migration_dir.iterdir():
        if not file.is_file() and file.suffix != ".sql":
            continue
        migrations.append(file)
    return sorted(migrations, key=lambda x: x.stem)


async def check_done_migrations(conninfo: str) -> list[str]:
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'migrations')"
            )
            record = await cur.fetchone()
            if record is None or record[0] is False:
                return []

            await cur.execute("SELECT name FROM migrations")
            names: list[str] = []
            async for record in cur:
                names.append(record[0])
            return names


async def update_migration_table(conninfo: str, migration_name: str):
    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO migrations (name) VALUES (%s)", (migration_name,)
            )
            await conn.commit()


async def execute_migration(conninfo: str, migration: Path):
    if not migration.is_file() and migration.suffix != ".sql":
        return

    async with await AsyncConnection.connect(conninfo) as conn:
        async with conn.cursor() as cur:
            with open(migration, "rb") as f:
                await cur.execute(f.read())
            await conn.commit()


async def execute_migrations(conninfo: str):
    done_migrations = await check_done_migrations(conninfo)
    LOGGER.debug(f"Done migrations: {done_migrations}")
    for migration in migration_order():
        if migration.stem in done_migrations:
            continue

        LOGGER.info(f"Executing migration {migration.stem}")
        await execute_migration(conninfo, migration)
        await update_migration_table(conninfo, migration.stem)
