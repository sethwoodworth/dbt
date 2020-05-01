from test.integration.base import DBTIntegrationTest, use_profile
import os


class TestAnalyses(DBTIntegrationTest):

    @property
    def schema(self):
        return "test_analyses_019"

    @property
    def models(self):
        return "models"

    def analysis_path(self):
        return "analysis"

    @property
    def project_config(self):
        return {
            "config-version": 2,
            "analysis-paths": [self.analysis_path()]
        }

    def assert_contents_equal(self, path, expected):
        with open(path) as fp:
            self.assertEqual(fp.read().strip(), expected)

    @use_profile('postgres')
    def test_postgres_analyses(self):
        compiled_analysis_path = os.path.normpath('target/compiled/test/analysis')
        path_1 = os.path.join(compiled_analysis_path, 'analysis.sql')
        path_2 = os.path.join(compiled_analysis_path, 'raw_stuff.sql')

        self.run_dbt(['clean'])
        self.assertFalse(os.path.exists(compiled_analysis_path))
        results = self.run_dbt(["compile"])
        self.assertEqual(len(results), 3)

        self.assertTrue(os.path.exists(path_1))
        self.assertTrue(os.path.exists(path_2))

        expected_sql = 'select * from "{}"."{}"."my_model"'.format(
            self.default_database, self.unique_schema()
        )
        self.assert_contents_equal(path_1, expected_sql)
        self.assert_contents_equal(path_2, '{% invalid jinja stuff %}')

