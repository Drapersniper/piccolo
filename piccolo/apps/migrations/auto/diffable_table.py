from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from piccolo.apps.migrations.auto.operations import (
    AddColumn,
    AlterColumn,
    DropColumn,
)
from piccolo.apps.migrations.auto.serialisation import (
    deserialise_params,
    serialise_params,
)
from piccolo.columns.base import Column
from piccolo.table import Table, create_table_class


def compare_dicts(
    dict_1: dict[str, Any], dict_2: dict[str, Any]
) -> dict[str, Any]:
    """
    Returns a new dictionary which only contains key, value pairs which are in
    the first dictionary and not the second.

    For example::

        >>> dict_1 = {'a': 1, 'b': 2}
        >>> dict_2 = {'a': 1}
        >>> compare_dicts(dict_1, dict_2)
        {'b': 2}

        >>> dict_1 = {'a': 2, 'b': 2}
        >>> dict_2 = {'a': 1}
        >>> compare_dicts(dict_1, dict_2)
        {'a': 2, 'b': 2}

    """
    output = {}

    for key, value in dict_1.items():
        dict_2_value = dict_2.get(key, ...)

        if (
            # If the value is `...` then it means no value was found.
            (dict_2_value is ...)
            # We have to compare the types, because if we just use equality
            # then 1.0 == 1 is True.
            # See this issue:
            # https://github.com/piccolo-orm/piccolo/issues/1071
            or (type(value) is not type(dict_2_value))
            # Finally compare the actual values.
            or (dict_2_value != value)
        ):
            output[key] = value

    return output


@dataclass
class TableDelta:
    add_columns: list[AddColumn] = field(default_factory=list)
    drop_columns: list[DropColumn] = field(default_factory=list)
    alter_columns: list[AlterColumn] = field(default_factory=list)

    def __eq__(self, value: TableDelta) -> bool:  # type: ignore
        """
        This is mostly for testing purposes.
        """
        return True


@dataclass
class ColumnComparison:
    """
    As Column overrides it's `__eq__` method, to allow it to be used in the
    `where` clause of a query, we need to wrap `Column` if we want to compare
    them.
    """

    column: Column

    def __hash__(self) -> int:
        return self.column.__hash__()

    def __eq__(self, value) -> bool:
        if isinstance(value, ColumnComparison):
            return (
                self.column._meta.db_column_name
                == value.column._meta.db_column_name
            )
        return False


@dataclass
class DiffableTable:
    """
    Represents a Table. When we substract two instances, it returns the
    changes.
    """

    class_name: str
    tablename: str
    schema: Optional[str] = None
    columns: list[Column] = field(default_factory=list)
    previous_class_name: Optional[str] = None

    def __post_init__(self) -> None:
        self.columns_map: dict[str, Column] = {
            i._meta.name: i for i in self.columns
        }

    def __sub__(self, value: DiffableTable) -> TableDelta:
        if not isinstance(value, DiffableTable):
            raise ValueError(
                "Can only diff with other DiffableTable instances"
            )

        if value.class_name != self.class_name:
            raise ValueError(
                "The two tables don't appear to have the same name."
            )

        #######################################################################

        # Because we're using sets here, the order is indeterminate. We sort
        # them, otherwise it's difficult to write good unit tests if the order
        # constantly changes.

        add_columns = [
            AddColumn(
                table_class_name=self.class_name,
                column_name=i.column._meta.name,
                db_column_name=i.column._meta.db_column_name,
                column_class_name=i.column.__class__.__name__,
                column_class=i.column.__class__,
                params=i.column._meta.params,
                schema=self.schema,
            )
            for i in sorted(
                {ColumnComparison(column=column) for column in self.columns}
                - {
                    ColumnComparison(column=column) for column in value.columns
                },
                key=lambda x: x.column._meta.name,
            )
        ]

        drop_columns = [
            DropColumn(
                table_class_name=self.class_name,
                column_name=i.column._meta.name,
                db_column_name=i.column._meta.db_column_name,
                tablename=value.tablename,
                schema=self.schema,
            )
            for i in sorted(
                {ColumnComparison(column=column) for column in value.columns}
                - {ColumnComparison(column=column) for column in self.columns},
                key=lambda x: x.column._meta.name,
            )
        ]

        #######################################################################

        alter_columns: list[AlterColumn] = []

        for existing_column in value.columns:
            column = self.columns_map.get(existing_column._meta.name)
            if not column:
                # This is a new column - already captured above.
                continue

            delta = compare_dicts(
                serialise_params(column._meta.params).params,
                serialise_params(existing_column._meta.params).params,
            )

            old_params = {
                key: existing_column._meta.params.get(key)
                for key, _ in delta.items()
            }

            if delta or (column.__class__ != existing_column.__class__):
                alter_columns.append(
                    AlterColumn(
                        table_class_name=self.class_name,
                        tablename=self.tablename,
                        column_name=column._meta.name,
                        db_column_name=column._meta.db_column_name,
                        params=deserialise_params(delta),
                        old_params=old_params,
                        column_class=column.__class__,
                        old_column_class=existing_column.__class__,
                        schema=self.schema,
                    )
                )

        return TableDelta(
            add_columns=add_columns,
            drop_columns=drop_columns,
            alter_columns=alter_columns,
        )

    def __hash__(self) -> int:
        """
        We have to return an integer, which is why convert the string this way.
        """
        return hash(self.class_name + self.tablename)

    def __eq__(self, value) -> bool:
        """
        This is used by sets for uniqueness checks.
        """
        if not isinstance(value, DiffableTable):
            return False
        return (self.class_name == value.class_name) and (
            self.tablename == value.tablename
        )

    def __str__(self):
        return f"{self.class_name} - {self.tablename}"

    def to_table_class(self) -> type[Table]:
        """
        Converts the DiffableTable into a Table subclass.
        """
        return create_table_class(
            class_name=self.class_name,
            class_kwargs={"tablename": self.tablename, "schema": self.schema},
            class_members={
                column._meta.name: column for column in self.columns
            },
        )
