"""Offline, credential-free tests for the public Kero smoke contract."""
import contextlib
import io
import json
import unittest
from unittest import mock
from urllib.error import HTTPError

import runner_bridge


class Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class SmokeContractTests(unittest.TestCase):
    def simulate(self, protected_status):
        calls = []

        def open_url(request, timeout):
            url = request.full_url
            calls.append(url)
            if url.endswith("/rotas/") or url.endswith("/calculadora/"):
                if protected_status >= 400:
                    raise HTTPError(url, protected_status, "HTTP error", {}, None)
                return Response(protected_status)
            return Response(200)

        output = io.StringIO()
        with mock.patch.object(runner_bridge.urllib.request, "urlopen", open_url), mock.patch.object(runner_bridge.time, "sleep"):
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as status:
                runner_bridge.site_smoke()
        return status.exception.code, [json.loads(s) for s in output.getvalue().splitlines()], calls

    def test_401_means_expected_auth_gate(self):
        code, rows, calls = self.simulate(401)
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(x["ok"] for x in rows))
        self.assertEqual([x["status"] for x in rows], [200, 401, 401])
        self.assertTrue(all(x["authenticated_functionality_tested"] is False for x in rows))

    def test_403_does_not_pass_or_retry(self):
        code, rows, calls = self.simulate(403)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 3)
        self.assertFalse(rows[1]["ok"])
        self.assertEqual(rows[1]["status"], 403)

    def test_public_200_does_not_pass_protected_gate(self):
        code, rows, calls = self.simulate(200)
        self.assertEqual(code, 2)
        self.assertFalse(rows[1]["ok"])
        self.assertFalse(rows[2]["ok"])


if __name__ == "__main__":
    unittest.main()
