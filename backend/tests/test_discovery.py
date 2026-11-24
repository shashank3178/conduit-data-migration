import unittest
from snowbridge.contracts import Capability,CapabilityStatus,Column,Key,TableSchema,MappingSafety
from snowbridge.discovery import discover_inventory,estimate_migration
from snowbridge.type_mapping import map_type,normalize_engine

class FakeAdapter:
    def inspect_capabilities(self):
        return (Capability("snapshot",CapabilityStatus.AVAILABLE,"available"),)
    def discover_schema(self,schemas=None):
        return [TableSchema("app","orders",(
            Column("id",1,"integer",False),Column("amount",2,"numeric",True,precision=12,scale=2)),
            (Key("pk_orders",("id",),True,True),),estimated_rows=100,estimated_bytes=8192,
            storage_engine="postgresql")]

class DiscoveryTests(unittest.TestCase):
    def test_unified_inventory_and_estimate(self):
        report=discover_inventory(FakeAdapter(),"postgresql","mysql")
        self.assertEqual(report.estimate.table_count,1)
        self.assertEqual(report.estimate.estimated_rows,100)
        self.assertEqual(report.estimate.estimated_bytes,8192)
        self.assertEqual(len(report.mappings),2)
        self.assertEqual(report.unsupported_mappings,())
        self.assertTrue(any("Inventory scope" in warning for warning in report.warnings))

    def test_unknown_estimates_are_reported(self):
        estimate=estimate_migration([TableSchema("s","t",(Column("id",1,"int",False),))])
        self.assertEqual(estimate.confidence,"low")
        self.assertEqual(estimate.unknown_row_tables,("s.t",))
        self.assertEqual(estimate.unknown_size_tables,("s.t",))

    def test_unsigned_mysql_integer_requires_wider_target(self):
        mapping=map_type("mysql","postgresql","int unsigned")
        self.assertEqual(mapping.target_type,"bigint")
        self.assertEqual(mapping.safety,MappingSafety.WARNING)

    def test_mysql_unsigned_bigint_does_not_overflow_postgresql_bigint(self):
        mapping=map_type("mysql","postgresql","bigint unsigned")
        self.assertEqual(mapping.target_type,"numeric(20,0)")
        self.assertEqual(mapping.safety,MappingSafety.WARNING)

    def test_mysql_enum_is_preserved_as_text_with_warning(self):
        mapping=map_type("mysql","postgresql","enum('new','paid','cancelled')")
        self.assertEqual(mapping.target_type,"text")
        self.assertEqual(mapping.safety,MappingSafety.WARNING)

    def test_oracle_date_preserves_time_component(self):
        mapping=map_type("oracle","postgresql","DATE")
        self.assertEqual(mapping.target_type,"timestamp")
        self.assertEqual(mapping.safety,MappingSafety.WARNING)

    def test_spatial_requires_explicit_transform(self):
        mapping=map_type("oracle","postgresql","SDO_GEOMETRY")
        self.assertEqual(mapping.safety,MappingSafety.REQUIRES_TRANSFORM)

    def test_unknown_native_type_is_not_silently_mapped(self):
        mapping=map_type("mysql","postgresql","vendor_custom_type")
        self.assertEqual(mapping.safety,MappingSafety.UNSUPPORTED)

    def test_engine_aliases(self):
        self.assertEqual(normalize_engine("postgres"),"postgresql")
        with self.assertRaises(ValueError):normalize_engine("sqlite")

if __name__=="__main__":unittest.main()
