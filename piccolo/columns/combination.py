from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union

from piccolo.columns.operators.comparison import (
    ComparisonOperator,
    Equal,
    IsNull,
)
from piccolo.custom_types import Combinable, CustomIterable
from piccolo.querystring import QueryString
from piccolo.utils.sql_values import convert_to_sql_value

if TYPE_CHECKING:
    from piccolo.columns.base import Column


class CombinableMixin(object):

    __slots__ = ()

    def __and__(self, value: Combinable) -> "And":
        return And(self, value)  # type: ignore

    def __or__(self, value: Combinable) -> "Or":
        return Or(self, value)  # type: ignore


class Combination(CombinableMixin):

    __slots__ = ("first", "second")

    operator = ""

    def __init__(self, first: Combinable, second: Combinable) -> None:
        self.first = first
        self.second = second

    @property
    def querystring(self) -> QueryString:
        return QueryString(
            "({} " + self.operator + " {})",
            self.first.querystring,
            self.second.querystring,
        )

    @property
    def querystring_for_update_and_delete(self) -> QueryString:
        return QueryString(
            "({} " + self.operator + " {})",
            self.first.querystring_for_update_and_delete,
            self.second.querystring_for_update_and_delete,
        )

    def __str__(self):
        return self.querystring.__str__()


class And(Combination):
    operator = "AND"

    def get_column_values(self) -> dict[Column, Any]:
        """
        This is used by `get_or_create` to know which values to assign if
        the row doesn't exist in the database.

        For example, if we have::

            (Band.name == 'Pythonistas') & (Band.popularity == 1000)

        We will return::

            {Band.name: 'Pythonistas', Band.popularity: 1000}.

        If the operator is anything besides equals, we don't return it, for
        example::

            (Band.name == 'Pythonistas') & (Band.popularity > 1000)

        Returns::

            {Band.name: 'Pythonistas'}

        """
        output = {}
        for combinable in (self.first, self.second):
            if isinstance(combinable, Where):
                if combinable.operator == Equal:
                    output[combinable.column] = combinable.value
                elif combinable.operator == IsNull:
                    output[combinable.column] = None
            elif isinstance(combinable, And):
                output.update(combinable.get_column_values())

        return output


class Or(Combination):
    operator = "OR"


class Undefined:
    pass


UNDEFINED = Undefined()


class WhereRaw(CombinableMixin):
    __slots__ = ("querystring",)

    def __init__(self, sql: str, *args: Any) -> None:
        """
        Execute raw SQL queries in your where clause. Use with caution!

        .. code-block:: python

            await Band.where(
                WhereRaw("name = 'Pythonistas'")
            )

        Or passing in parameters:

        .. code-block:: python

            await Band.where(
                WhereRaw("name = {}", 'Pythonistas')
            )

        """
        self.querystring = QueryString(sql, *args)

    @property
    def querystring_for_update_and_delete(self) -> QueryString:
        return self.querystring

    def __str__(self):
        return self.querystring.__str__()


class Where(CombinableMixin):

    __slots__ = ("column", "value", "values", "operator")

    def __init__(
        self,
        column: Column,
        value: Any = UNDEFINED,
        values: Union[CustomIterable, Undefined, QueryString] = UNDEFINED,
        operator: type[ComparisonOperator] = ComparisonOperator,
    ) -> None:
        """
        We use the UNDEFINED value to show the value was deliberately
        omitted, vs None, which is a valid value for a where clause.
        """
        self.column = column

        self.value = value if value == UNDEFINED else self.clean_value(value)
        if (values == UNDEFINED) or isinstance(values, QueryString):
            self.values = values
        else:
            self.values = [self.clean_value(i) for i in values]  # type: ignore

        self.operator = operator

    def clean_value(self, value: Any) -> Any:
        """
        If a where clause contains a ``Table`` instance, we should convert that
        to a column reference. For example:

        .. code-block:: python

            manager = await Manager.objects.where(
                Manager.name == 'Guido'
            ).first()

            # The where clause should be:
            await Band.select().where(Band.manager.id == guido.id)
            # Or
            await Band.select().where(Band.manager == guido.id)

            # If the object is passed in, i.e. `guido` instead of `guido.id`,
            # it should still work.
            await Band.select().where(Band.manager == guido)

        Also, convert Enums to their underlying values, and serialise any JSON.

        """
        return convert_to_sql_value(value=value, column=self.column)

    @property
    def values_querystring(self) -> QueryString:
        values = self.values

        if isinstance(values, QueryString):
            return values

        if isinstance(values, Undefined):
            raise ValueError("values is undefined")

        template = ", ".join("{}" for _ in values)
        return QueryString(template, *values)

    @property
    def querystring(self) -> QueryString:
        args: list[Any] = []
        if self.value != UNDEFINED:
            args.append(self.value)

        if self.values != UNDEFINED:
            args.append(self.values_querystring)

        template = self.operator.template.format(
            name=self.column.get_where_string(
                engine_type=self.column._meta.engine_type
            ),
            value="{}",
            values="{}",
        )

        return QueryString(template, *args)

    @property
    def querystring_for_update_and_delete(self) -> QueryString:
        args: list[Any] = []
        if self.value != UNDEFINED:
            args.append(self.value)

        if self.values != UNDEFINED:
            args.append(self.values_querystring)

        column = self.column

        if column._meta.call_chain:
            # Use a sub select to find the correct ID.
            root_column = column._meta.call_chain[0]
            sub_query = root_column._meta.table.select(root_column).where(self)

            column_name = column._meta.call_chain[0]._meta.name
            return QueryString(
                f"{column_name} IN ({{}})",
                sub_query.querystrings[0],
            )
        else:
            template = self.operator.template.format(
                name=self.column.get_where_string(
                    engine_type=self.column._meta.engine_type
                ),
                value="{}",
                values="{}",
            )

            return QueryString(template, *args)

    def __str__(self):
        return self.querystring.__str__()
