from test.integration.base import DBTIntegrationTest, use_profile
import hashlib
import os

from unittest.mock import call, ANY, patch

import dbt.exceptions
import dbt.version
import dbt.tracking
import dbt.utils


class TestEventTracking(DBTIntegrationTest):
    maxDiff = None

    @property
    def profile_config(self):
        return {
            'config': {
                'send_anonymous_usage_stats': True
            }
        }

    @property
    def schema(self):
        return "event_tracking_033"

    @staticmethod
    def dir(path):
        return path.lstrip("/")

    @property
    def models(self):
        return self.dir("models")

    # TODO : Handle the subject. Should be the same every time!
    # TODO : Regex match a uuid for user_id, invocation_id?

    @patch('dbt.tracking.tracker.track_struct_event')
    def run_event_test(
        self,
        cmd,
        expected_calls,
        expected_contexts,
        track_fn,
        expect_pass=True,
        expect_raise=False
    ):
        track_fn.reset_mock()

        project_id = hashlib.md5(
            self.config.project_name.encode('utf-8')).hexdigest()
        version = str(dbt.version.get_installed_version())

        if expect_raise:
            with self.assertRaises(BaseException):
                self.run_dbt(cmd, expect_pass=expect_pass)
        else:
            self.run_dbt(cmd, expect_pass=expect_pass)

        user_id = dbt.tracking.active_user.id
        invocation_id = dbt.tracking.active_user.invocation_id

        self.assertTrue(len(user_id) > 0)
        self.assertTrue(len(invocation_id) > 0)

        track_fn.assert_has_calls(expected_calls)

        ordered_contexts = []

        for (args, kwargs) in track_fn.call_args_list:
            ordered_contexts.append(
                [context.__dict__ for context in kwargs['context']]
            )

        populated_contexts = []

        for context in expected_contexts:
            if callable(context):
                populated_contexts.append(context(
                    project_id, user_id, invocation_id, version))
            else:
                populated_contexts.append(context)

        self.assertEqual(
            ordered_contexts,
            populated_contexts
        )

    def build_context(
        self,
        command,
        progress,
        result_type=None,
        adapter_type='postgres'
    ):

        def populate(
            project_id,
            user_id,
            invocation_id,
            version
        ):
            return [
                {
                    'schema': 'iglu:com.dbt/invocation/jsonschema/1-0-1',
                    'data': {
                        'project_id': project_id,
                        'user_id': user_id,
                        'invocation_id': invocation_id,
                        'version': version,

                        'command': command,
                        'progress': progress,
                        'run_type': 'regular',

                        'options': None,  # TODO : Add options to compile cmd!
                        'result_type': result_type,
                        'result': None,
                        'adapter_type': adapter_type
                    }
                },
                {
                    'schema': 'iglu:com.dbt/platform/jsonschema/1-0-0',
                    'data': ANY
                },
                {
                    'schema': 'iglu:com.dbt/invocation_env/jsonschema/1-0-0',
                    'data': ANY
                }
            ]

        return populate

    def run_context(
        self,
        materialization,
        hashed_contents,
        model_id,
        index,
        total,
        status,
        error=None
    ):
        timing = []

        if status != 'ERROR':
            timing = [ANY, ANY]

        def populate(project_id, user_id, invocation_id, version):
            return [{
                'schema': 'iglu:com.dbt/run_model/jsonschema/1-0-1',
                'data': {
                    'invocation_id': invocation_id,

                    'model_materialization': materialization,

                    'execution_time': ANY,
                    'hashed_contents': hashed_contents,
                    'model_id': model_id,

                    'index': index,
                    'total': total,

                    'run_status': status,
                    'run_error': error,
                    'run_skipped': False,

                    'timing': timing,
                },
            }]

        return populate


class TestEventTrackingSuccess(TestEventTracking):
    @property
    def packages_config(self):
        return {
            'packages': [
                {'git': 'https://github.com/fishtown-analytics/dbt-integration-project', 'warn-unpinned': False},
            ],
        }

    @property
    def project_config(self):
        return {
            'config-version': 2,
            "data-paths": [self.dir("data")],
            "test-paths": [self.dir("test")],
            'seeds': {
                'quote_columns': False,
            }
        }

    @use_profile("postgres")
    def test__postgres_event_tracking_compile(self):
        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('compile', 'start'),
            self.build_context('compile', 'end', result_type='ok')
        ]

        self.run_event_test(
            ["compile", "--vars", "sensitive_thing: abc"],
            expected_calls,
            expected_contexts
        )

    @use_profile("postgres")
    def test__postgres_event_tracking_deps(self):
        package_context = [
            {
                'schema': 'iglu:com.dbt/package_install/jsonschema/1-0-0',
                'data': {
                    'name': 'c5552991412d1cd86e5c20a87f3518d5',
                    'source': 'git',
                    'version': 'eb0a191797624dd3a48fa681d3061212'
                }
            }
        ]

        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='package',
                label=ANY,
                property_='install',
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('deps', 'start'),
            package_context,
            self.build_context('deps', 'end', result_type='ok')
        ]

        self.run_event_test(["deps"], expected_calls, expected_contexts)

    @use_profile("postgres")
    def test__postgres_event_tracking_seed(self):
        def seed_context(project_id, user_id, invocation_id, version):
            return [{
                'schema': 'iglu:com.dbt/run_model/jsonschema/1-0-1',
                'data': {
                    'invocation_id': invocation_id,

                    'model_materialization': 'seed',

                    'execution_time': ANY,
                    'hashed_contents': 'd41d8cd98f00b204e9800998ecf8427e',
                    'model_id': '39bc2cd707d99bd3e600d2faaafad7ae',

                    'index': 1,
                    'total': 1,

                    'run_status': 'INSERT 1',
                    'run_error': None,
                    'run_skipped': False,

                    'timing': [ANY, ANY],
                },
            }]

        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='run_model',
                label=ANY,
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('seed', 'start'),
            seed_context,
            self.build_context('seed', 'end', result_type='ok')
        ]

        self.run_event_test(["seed"], expected_calls, expected_contexts)

    @use_profile("postgres")
    def test__postgres_event_tracking_models(self):
        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='run_model',
                label=ANY,
                context=ANY
            ),
            call(
                category='dbt',
                action='run_model',
                label=ANY,
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        hashed = '20ff78afb16c8b3b8f83861b1d3b99bd'
        # this hashed contents field changes on azure postgres tests, I believe
        # due to newlines again
        if os.name == 'nt':
            hashed = '52cf9d1db8f0a18ca64ef64681399746'

        expected_contexts = [
            self.build_context('run', 'start'),
            self.run_context(
                hashed_contents='1e5789d34cddfbd5da47d7713aa9191c',
                model_id='4fbacae0e1b69924b22964b457148fb8',
                index=1,
                total=2,
                status='CREATE VIEW',
                materialization='view'
            ),
            self.run_context(
                hashed_contents=hashed,
                model_id='57994a805249953b31b738b1af7a1eeb',
                index=2,
                total=2,
                status='CREATE VIEW',
                materialization='view'
            ),
            self.build_context('run', 'end', result_type='ok')
        ]

        self.run_event_test(
            ["run", "--model", "example", "example_2"],
            expected_calls,
            expected_contexts
        )

    @use_profile("postgres")
    def test__postgres_event_tracking_model_error(self):
        # cmd = ["run", "--model", "model_error"]
        # self.run_event_test(cmd, event_run_model_error, expect_pass=False)

        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='run_model',
                label=ANY,
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('run', 'start'),
            self.run_context(
                hashed_contents='4419e809ce0995d99026299e54266037',
                model_id='576c3d4489593f00fad42b97c278641e',
                index=1,
                total=1,
                status='ERROR',
                materialization='view'
            ),
            self.build_context('run', 'end', result_type='ok')
        ]

        self.run_event_test(
            ["run", "--model", "model_error"],
            expected_calls,
            expected_contexts,
            expect_pass=False
        )

    @use_profile("postgres")
    def test__postgres_event_tracking_tests(self):
        # TODO: dbt does not track events for tests, but it should!
        self.run_dbt(["run", "--model", "example", "example_2"])

        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('test', 'start'),
            self.build_context('test', 'end', result_type='ok')
        ]

        self.run_event_test(
            ["test"],
            expected_calls,
            expected_contexts,
            expect_pass=False
        )


class TestEventTrackingCompilationError(TestEventTracking):
    @property
    def project_config(self):
        return {
            'config-version': 2,
            "source-paths": [self.dir("model-compilation-error")],
        }

    @use_profile("postgres")
    def test__postgres_event_tracking_with_compilation_error(self):
        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('compile', 'start'),
            self.build_context('compile', 'end', result_type='error')
        ]

        self.run_event_test(
            ["compile"],
            expected_calls,
            expected_contexts,
            expect_pass=False,
            expect_raise=True
        )


class TestEventTrackingUnableToConnect(TestEventTracking):

    @property
    def profile_config(self):
        return {
            'config': {
                'send_anonymous_usage_stats': True
            },
            'test': {
                'outputs': {
                    'default2': {
                        'type': 'postgres',
                        'threads': 4,
                        'host': self.database_host,
                        'port': 5432,
                        'user': 'root',
                        'pass': 'password',
                        'dbname': 'dbt',
                        'schema': self.unique_schema()
                    },
                    'noaccess': {
                        'type': 'postgres',
                        'threads': 4,
                        'host': self.database_host,
                        'port': 5432,
                        'user': 'BAD',
                        'pass': 'bad_password',
                        'dbname': 'dbt',
                        'schema': self.unique_schema()
                    }
                },
                'target': 'default2'
            }
        }

    @use_profile("postgres")
    def test__postgres_event_tracking_unable_to_connect(self):
        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('run', 'start'),
            self.build_context('run', 'end', result_type='error')
        ]

        self.run_event_test(
            ["run", "--target", "noaccess", "--models", "example"],
            expected_calls,
            expected_contexts,
            expect_pass=False
        )


class TestEventTrackingSnapshot(TestEventTracking):
    @property
    def project_config(self):
        return {
            'config-version': 2,
            "snapshot-paths": ['snapshots']
        }

    @use_profile("postgres")
    def test__postgres_event_tracking_snapshot(self):
        self.run_dbt(["run", "--models", "snapshottable"])

        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='run_model',
                label=ANY,
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        # the model here has a raw_sql that contains the schema, which changes
        expected_contexts = [
            self.build_context('snapshot', 'start'),
            self.run_context(
                hashed_contents=ANY,
                model_id='820793a4def8d8a38d109a9709374849',
                index=1,
                total=1,
                status='SELECT 1',
                materialization='snapshot'
            ),
            self.build_context('snapshot', 'end', result_type='ok')
        ]

        self.run_event_test(
            ["snapshot"],
            expected_calls,
            expected_contexts
        )


class TestEventTrackingCatalogGenerate(TestEventTracking):
    @use_profile("postgres")
    def test__postgres_event_tracking_catalog_generate(self):
        # create a model for the catalog
        self.run_dbt(["run", "--models", "example"])

        expected_calls = [
            call(
                category='dbt',
                action='invocation',
                label='start',
                context=ANY
            ),
            call(
                category='dbt',
                action='invocation',
                label='end',
                context=ANY
            ),
        ]

        expected_contexts = [
            self.build_context('generate', 'start'),
            self.build_context('generate', 'end', result_type='ok')
        ]

        self.run_event_test(
            ["docs", "generate"],
            expected_calls,
            expected_contexts
        )
