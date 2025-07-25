from __future__ import annotations

import os
import sys

from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.apps.migrations.commands.base import (
    BaseMigrationManager,
    MigrationResult,
)
from piccolo.apps.migrations.tables import Migration
from piccolo.conf.apps import AppConfig, MigrationModule
from piccolo.utils.printing import print_heading


class BackwardsMigrationManager(BaseMigrationManager):
    def __init__(
        self,
        app_name: str,
        migration_id: str,
        auto_agree: bool = False,
        clean: bool = False,
        preview: bool = False,
    ):
        self.migration_id = migration_id
        self.app_name = app_name
        self.auto_agree = auto_agree
        self.clean = clean
        self.preview = preview
        super().__init__()

    async def run_migrations_backwards(self, app_config: AppConfig):
        migration_modules: dict[str, MigrationModule] = (
            self.get_migration_modules(
                app_config.resolved_migrations_folder_path
            )
        )

        ran_migration_ids = await Migration.get_migrations_which_ran(
            app_name=self.app_name
        )
        if len(ran_migration_ids) == 0:
            # Make sure a success is returned, as we don't want this
            # to appear as an error in automated scripts.
            message = "🏁 No migrations to reverse!"
            print(message)
            return MigrationResult(success=True, message=message)

        #######################################################################

        if self.migration_id == "all":
            earliest_migration_id = ran_migration_ids[0]
        elif self.migration_id == "1":
            earliest_migration_id = ran_migration_ids[-1]
        else:
            earliest_migration_id = self.migration_id

        if earliest_migration_id not in ran_migration_ids:
            message = (
                "Unrecognized migration name - must be one of "
                f"{ran_migration_ids}"
            )
            print(message, file=sys.stderr)
            return MigrationResult(success=False, message=message)

        #######################################################################

        latest_migration_id = ran_migration_ids[-1]

        start_index = ran_migration_ids.index(earliest_migration_id)
        end_index = ran_migration_ids.index(latest_migration_id) + 1

        subset = ran_migration_ids[start_index:end_index]
        reversed_migration_ids = list(reversed(subset))

        #######################################################################

        n = len(reversed_migration_ids)
        _continue = (
            "y"
            if self.auto_agree
            else input(
                f"Reverse {n} migration{'s' if n != 1 else ''}? [y/N] "
            ).lower()
        )
        if _continue == "y":
            for migration_id in reversed_migration_ids:
                migration_module = migration_modules[migration_id]
                response = await migration_module.forwards()

                if isinstance(response, MigrationManager):
                    if self.preview:
                        response.preview = True
                    await response.run(backwards=True)
                if not self.preview:
                    await Migration.delete().where(
                        Migration.name == migration_id
                    ).run()

                    if self.clean and migration_module.__file__:
                        os.unlink(migration_module.__file__)

                print("ok! ✔️")
            return MigrationResult(success=True)

        else:  # pragma: no cover
            message = "Not proceeding."
            print(message, file=sys.stderr)
            return MigrationResult(success=False, message=message)

    async def run(self) -> MigrationResult:
        await self.create_migration_table()
        app_config = self.get_app_config(self.app_name)
        return await self.run_migrations_backwards(app_config=app_config)


async def run_backwards(
    app_name: str,
    migration_id: str = "1",
    auto_agree: bool = False,
    clean: bool = False,
    preview: bool = False,
) -> MigrationResult:
    if app_name == "all":
        sorted_app_names = BaseMigrationManager().get_sorted_app_names()
        sorted_app_names.reverse()

        names = [f"'{name}'" for name in sorted_app_names]
        _continue = (
            "y"
            if auto_agree
            else input(
                "You are about to undo the migrations for the following "
                "apps:\n"
                f"{', '.join(names)}\n"
                "Are you sure you want to continue? [y/N] "
            ).lower()
        )

        if _continue != "y":
            return MigrationResult(success=False, message="user cancelled")
        for _app_name in sorted_app_names:
            print_heading(_app_name)
            manager = BackwardsMigrationManager(
                app_name=_app_name,
                migration_id="all",
                auto_agree=auto_agree,
                preview=preview,
            )
            await manager.run()
        return MigrationResult(success=True)
    else:
        manager = BackwardsMigrationManager(
            app_name=app_name,
            migration_id=migration_id,
            auto_agree=auto_agree,
            clean=clean,
            preview=preview,
        )
        return await manager.run()


async def backwards(
    app_name: str,
    migration_id: str = "1",
    auto_agree: bool = False,
    clean: bool = False,
    preview: bool = False,
):
    """
    Undo migrations up to a specific migration.

    :param app_name:
        The app to reverse migrations for. Specify a value of 'all' to reverse
        migrations for all apps.
    :param migration_id:
        Migrations will be reversed up to and including this migration_id.
        Specify a value of 'all' to undo all of the migrations. Specify a
        value of '1' to undo the most recent migration.
    :param auto_agree:
        If true, automatically agree to any input prompts.
    :param clean:
        If true, the migration files which have been run backwards are deleted
        from the disk after completing.
    :param preview:
        If true, don't actually run the migration, just print the SQL queries.

    """
    response = await run_backwards(
        app_name=app_name,
        migration_id=migration_id,
        auto_agree=auto_agree,
        clean=clean,
        preview=preview,
    )

    if not response.success:
        sys.exit(1)
