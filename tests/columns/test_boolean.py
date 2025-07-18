from typing import Any

from piccolo.columns.column_types import Boolean
from piccolo.table import Table
from piccolo.testing.test_case import TableTest


class MyTable(Table):
    boolean = Boolean(default=False, null=True)


class TestBoolean(TableTest):
    tables = [MyTable]

    def test_return_type(self) -> None:
        for value in (True, False, None, ...):
            kwargs: dict[str, Any] = {} if value is ... else {"boolean": value}
            expected = MyTable.boolean.default if value is ... else value

            row = MyTable(**kwargs)
            row.save().run_sync()
            self.assertEqual(row.boolean, expected)

            row_from_db = (
                MyTable.select(MyTable.boolean)
                .where(
                    MyTable._meta.primary_key
                    == getattr(row, MyTable._meta.primary_key._meta.name)
                )
                .first()
                .run_sync()
            )
            assert row_from_db is not None

            self.assertEqual(
                row_from_db["boolean"],
                expected,
            )

    def test_eq_and_ne(self):
        """
        Make sure the `eq` and `ne` methods works correctly.
        """
        MyTable.insert(
            MyTable(boolean=True),
            MyTable(boolean=False),
            MyTable(boolean=True),
        ).run_sync()

        self.assertEqual(
            MyTable.count().where(MyTable.boolean.eq(True)).run_sync(), 2
        )

        self.assertEqual(
            MyTable.count().where(MyTable.boolean.ne(True)).run_sync(), 1
        )
