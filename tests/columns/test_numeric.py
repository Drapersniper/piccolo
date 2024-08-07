from decimal import Decimal

from piccolo.columns.column_types import Numeric
from piccolo.table import Table
from piccolo.testing.test_case import TableTest


class MyTable(Table):
    column_a = Numeric()
    column_b = Numeric(digits=(3, 2))


class TestNumeric(TableTest):
    tables = [MyTable]

    def test_creation(self):
        row = MyTable(column_a=Decimal(1.23), column_b=Decimal(1.23))
        row.save().run_sync()

        _row = MyTable.objects().first().run_sync()
        assert _row is not None

        self.assertEqual(type(_row.column_a), Decimal)
        self.assertEqual(type(_row.column_b), Decimal)

        self.assertAlmostEqual(_row.column_a, Decimal(1.23))
        self.assertAlmostEqual(_row.column_b, Decimal("1.23"))
