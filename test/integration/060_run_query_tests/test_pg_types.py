
from test.integration.base import DBTIntegrationTest, use_profile
import json

class TestPostgresTypes(DBTIntegrationTest):

    @property
    def schema(self):
        return "pg_query_types_060"

    @property
    def models(self):
        return "models"

    @property
    def project_config(self):
        return {
            'config-version': 2,
            'macro-paths': ['macros'],
        }

    @use_profile('bigquery')
    def test__postgres_nested_types(self):
        result = self.run_dbt(['run-operation', 'test_array_results'])
        self.assertTrue(result.success)
