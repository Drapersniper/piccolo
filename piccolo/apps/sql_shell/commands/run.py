import os
import signal
import subprocess
import sys
from typing import cast

from piccolo.engine.finder import engine_finder
from piccolo.engine.postgres import PostgresEngine
from piccolo.engine.sqlite import SQLiteEngine


def run() -> None:
    """
    Launch the SQL shell for the configured engine. For Postgres
    this will be psql, and for SQLite it will be sqlite3.
    """
    engine = engine_finder()

    if engine is None:
        raise ValueError(
            "Unable to find the engine - make sure piccolo_conf is on the "
            "path."
        )

    # Heavily inspired by Django's dbshell command
    if isinstance(engine, PostgresEngine):
        engine = cast(PostgresEngine, engine)

        args = ["psql"]

        config = engine.config

        if dsn := config.get("dsn"):
            args += [dsn]
        else:
            if user := config.get("user"):
                args += ["-U", user]
            if host := config.get("host"):
                args += ["-h", host]
            if port := config.get("port"):
                args += ["-p", str(port)]
            if database := config.get("database"):
                args += [database]

        sigint_handler = signal.getsignal(signal.SIGINT)
        subprocess_env = os.environ.copy()
        if password := config.get("password"):
            subprocess_env["PGPASSWORD"] = str(password)
        try:
            # Allow SIGINT to pass to psql to abort queries.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            print("Enter \\q to exit")
            subprocess.run(args, check=True, env=subprocess_env)
        finally:
            # Restore the original SIGINT handler.
            signal.signal(signal.SIGINT, sigint_handler)

    elif isinstance(engine, SQLiteEngine):
        engine = cast(SQLiteEngine, engine)

        database = cast(str, engine.connection_kwargs.get("database"))
        if not database:
            sys.exit("Unable to determine which database to connect to.")

        print("Enter .quit to exit")
        subprocess.run(["sqlite3", database], check=True)
