import unittest

from snowbridge.contracts import Column, Key, TableSchema
from snowbridge.schema_ddl import UnsupportedSchemaError, plan_postgresql_ddl


class PostgreSQLDDLTests(unittest.TestCase):
    def test_builds_schema_table_identity_and_primary_key(self):
        table = TableSchema(
            schema_name="target", table_name='order"items',
            columns=(
                Column("id", 1, "bigint", False, identity_kind="a"),
                Column("amount", 2, "numeric(12, 2)", False),
                Column("note", 3, "text", True),
            ),
            keys=(Key("order_items_pkey", ("id",), primary=True, unique=True),),
        )
        plan = plan_postgresql_ddl((table,))
        self.assertEqual(len(plan.statements), 2)
        self.assertEqual(
            plan.load_columns,
            (("target", 'order"items', ("id", "amount", "note")),),
        )
        self.assertEqual(plan.diagnostics, ())

    def test_excludes_generated_columns_from_load_projection(self):
        table = TableSchema(
            "public", "computed",
            (
                Column("id", 1, "integer", False),
                Column("total", 2, "numeric(10,2)", False, generated_kind="s"),
            ),
        )
        with self.assertRaisesRegex(UnsupportedSchemaError, "generated columns"):
            plan_postgresql_ddl((table,))

    def test_rejects_custom_types_and_partitioned_tables(self):
        custom = TableSchema(
            "public", "custom_type",
            (Column("payload", 1, "my_domain", True),),
        )
        with self.assertRaisesRegex(UnsupportedSchemaError, "my_domain"):
            plan_postgresql_ddl((custom,))
        partitioned = TableSchema(
            "public", "partitioned",
            (Column("id", 1, "bigint", False),), partitioned=True,
        )
        with self.assertRaisesRegex(UnsupportedSchemaError, "partitioned tables"):
            plan_postgresql_ddl((partitioned,))

    def test_untrusted_default_expression_is_reported_not_executed(self):
        table = TableSchema(
            "public", "defaults",
            (Column("payload", 1, "text", True,
                    default_expression="dangerous_function()"),),
        )
        plan = plan_postgresql_ddl((table,))
        self.assertEqual(len(plan.diagnostics), 1)
        self.assertIn("requires review", plan.diagnostics[0])


if __name__ == "__main__":
    unittest.main()
