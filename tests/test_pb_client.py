import unittest
from unittest.mock import Mock

from pb_client import PBClient


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class PBClientTests(unittest.TestCase):
    def test_list_queued_jobs_uses_compatible_sort(self):
        client = PBClient('http://localhost:8090', 'admin@admin.com', 'secret')
        called = {}

        def fake_request(method, path, **kwargs):
            called['method'] = method
            called['path'] = path
            called['params'] = kwargs.get('params', {})
            return FakeResponse({'items': []})

        client._request = fake_request  # type: ignore[assignment]

        client.list_queued_jobs(limit=3)

        self.assertEqual(called['method'], 'GET')
        self.assertEqual(called['path'], '/api/collections/video_jobs/records')
        self.assertEqual(called['params']['filter'], "status='queued'")
        self.assertEqual(called['params']['sort'], '-priority,-id')
        self.assertEqual(called['params']['perPage'], 3)

    def test_update_progress_heartbeat_does_not_override_progress(self):
        client = PBClient('http://localhost:8090', 'admin@admin.com', 'secret')
        called = {}

        def fake_request(method, path, **kwargs):
            called['method'] = method
            called['path'] = path
            called['json'] = kwargs.get('json', {})
            return FakeResponse({})

        client._request = fake_request  # type: ignore[assignment]

        client.update_progress('job1', -1, '', status='rendering', lease_seconds=10)

        self.assertEqual(called['method'], 'PATCH')
        self.assertEqual(called['path'], '/api/collections/video_jobs/records/job1')
        self.assertEqual(called['json']['status'], 'rendering')
        self.assertIn('lease_until', called['json'])
        self.assertNotIn('progress', called['json'])
        self.assertNotIn('progress_stage', called['json'])

    def test_authenticate_uses_superusers_endpoint(self):
        client = PBClient('http://localhost:8090', 'admin@admin.com', 'secret')
        mocked_post = Mock(return_value=Mock(raise_for_status=Mock(), json=Mock(return_value={'token': 'abc'})))
        client._client.post = mocked_post

        client._authenticate()

        args, kwargs = mocked_post.call_args
        self.assertEqual(
            args[0],
            'http://localhost:8090/api/collections/_superusers/auth-with-password',
        )
        self.assertEqual(kwargs['json']['identity'], 'admin@admin.com')
        self.assertEqual(kwargs['json']['password'], 'secret')
        self.assertEqual(client._token, 'abc')


if __name__ == '__main__':
    unittest.main()
