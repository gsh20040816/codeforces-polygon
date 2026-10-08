import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from codeforces_polygon.client import Polygon, PolygonError, download, sign


def response(status=200, body=None, content=None, content_type="application/json"):
    resp = Mock()
    resp.status_code = status
    resp.headers = {"Content-Type": content_type}
    if body is not None:
        resp.json.return_value = body
        resp.text = json.dumps(body)
        resp.content = resp.text.encode()
    else:
        resp.json.side_effect = ValueError("not json")
        resp.content = content or b""
        resp.text = resp.content.decode("utf-8", "replace")
    resp.raise_for_status.return_value = None
    return resp


class SignTest(unittest.TestCase):
    def test_matches_polygon_algorithm(self):
        # From the Polygon API docs: rand/method?sorted_params#secret, sha512, prefixed by rand.
        fields = {"problemId": b"7", "apiKey": b"key", "time": b"100"}
        expected_base = b"abcdef/problem.info?apiKey=key&problemId=7&time=100#secret"
        expected = b"abcdef" + hashlib.sha512(expected_base).hexdigest().encode()
        self.assertEqual(sign("problem.info", fields, "secret", rand="abcdef"), expected)

    def test_sorts_by_key_then_value_and_signs_binary_values(self):
        fields = {"b": b"\xff\x00", "a": b"2"}
        base = b"zzzzzz/m?a=2&b=\xff\x00#s"
        self.assertEqual(sign("m", fields, "s", rand="zzzzzz"),
                         b"zzzzzz" + hashlib.sha512(base).hexdigest().encode())

    def test_random_prefix_is_six_chars(self):
        self.assertEqual(len(sign("m", {}, "s")), 6 + 128)


@patch("codeforces_polygon.client.time.time", return_value=1700000000)
@patch("codeforces_polygon.client.requests.post")
class CallTest(unittest.TestCase):
    def setUp(self):
        self.api = Polygon("key", "secret")

    def test_posts_signed_multipart_and_returns_result(self, post, _time):
        post.return_value = response(body={"status": "OK", "result": {"timeLimit": 1000}})

        result = self.api.call("problem.info", problemId=5, pin=None, enable=True)

        self.assertEqual(result, {"timeLimit": 1000})
        url = post.call_args.args[0]
        fields = post.call_args.kwargs["files"]
        self.assertEqual(url, "https://polygon.codeforces.com/api/problem.info")
        self.assertNotIn("pin", fields)  # None params are dropped
        self.assertEqual(fields["problemId"], b"5")
        self.assertEqual(fields["enable"], b"true")
        self.assertEqual(fields["apiKey"], b"key")
        self.assertEqual(fields["time"], b"1700000000")
        unsigned = {k: v for k, v in fields.items() if k != "apiSig"}
        rand = fields["apiSig"][:6].decode()
        self.assertEqual(fields["apiSig"], sign("problem.info", unsigned, "secret", rand=rand))

    def test_returns_none_when_ok_without_result(self, post, _time):
        post.return_value = response(body={"status": "OK"})
        self.assertIsNone(self.api.call("problem.commitChanges", problemId=1))

    def test_raw_returns_body_bytes(self, post, _time):
        post.return_value = response(content=b"1 2\n")
        self.assertEqual(self.api.call("problem.testInput", raw=True, problemId=1), b"1 2\n")

    def test_failed_status_raises_with_comment(self, post, _time):
        post.return_value = response(status=400, body={"status": "FAILED", "comment": "problemId: Access denied"})
        with self.assertRaisesRegex(PolygonError, "problem.info: problemId: Access denied"):
            self.api.call("problem.info", problemId=1)

    def test_failure_details_are_included(self, post, _time):
        body = {"status": "FAILED", "comment": "Some tests can not be deleted.",
                "result": {"failures": [{"testIndex": 2, "reason": "NOT_FOUND"}]}}
        post.return_value = response(status=400, body=body)
        with self.assertRaisesRegex(PolygonError, "can not be deleted.*NOT_FOUND"):
            self.api.call("problem.deleteTest", problemId=1, testset="tests", testIndices="2")

    def test_raw_failure_reports_polygon_comment(self, post, _time):
        # e.g. a generator or validator crash while producing a test input
        comment = "Validator 'val.cpp' returns exit code 3 [FAIL n out of range]\nInput:\n100000000\n"
        post.return_value = response(status=400, body={"status": "FAILED", "comment": comment})
        with self.assertRaises(PolygonError) as ctx:
            self.api.call("problem.testInput", raw=True, problemId=1, testset="tests", testIndex=3)
        self.assertIn("FAIL n out of range", str(ctx.exception))
        self.assertIn("100000000", str(ctx.exception))

    def test_non_json_error_raises_with_status(self, post, _time):
        post.return_value = response(status=502, content=b"Bad Gateway")
        with self.assertRaisesRegex(PolygonError, "HTTP 502: Bad Gateway"):
            self.api.call("problem.info", problemId=1)

    def test_file_body_without_raw_is_returned_as_bytes(self, post, _time):
        # `call problem.viewFile` without --raw; Polygon labels everything text/html
        post.return_value = response(content=b"#include <cstdio>\n", content_type="text/html;charset=UTF-8")
        self.assertEqual(self.api.call("problem.viewFile", problemId=1), b"#include <cstdio>\n")

    def test_scalar_json_body_is_a_file_not_a_crash(self, post, _time):
        post.return_value = response(body=5)
        self.assertEqual(self.api.call("problem.testInput", problemId=1), b"5")

    def test_http_status_is_kept_on_errors(self, post, _time):
        post.return_value = response(status=503, content=b"busy")
        with self.assertRaises(PolygonError) as ctx:
            self.api.call("problem.info", problemId=1)
        self.assertEqual(ctx.exception.status, 503)

    def test_bytes_params_are_sent_verbatim(self, post, _time):
        post.return_value = response(body={"status": "OK"})
        self.api.call("problem.saveStatementResource", problemId=1, name="a.png", file=b"\x89PNG\x00")
        self.assertEqual(post.call_args.kwargs["files"]["file"], b"\x89PNG\x00")


class FromEnvTest(unittest.TestCase):
    def test_requires_key_and_secret(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(PolygonError, "POLYGON_API_KEY"):
                Polygon.from_env()

    def test_reads_env(self):
        env = {"POLYGON_API_KEY": "k", "POLYGON_API_SECRET": "s", "POLYGON_URL": "https://example.test/"}
        with patch.dict("os.environ", env, clear=True):
            api = Polygon.from_env()
        self.assertEqual((api.key, api.secret, api.url), ("k", "s", "https://example.test"))


@patch("codeforces_polygon.client.requests.post")
class DownloadTest(unittest.TestCase):
    def test_posts_credentials_and_params(self, post):
        post.return_value = response(content=b"<problem/>", content_type="application/xml")
        content = download("https://polygon.codeforces.com/p85dIBF/u/a/problem.xml", "me", "pw",
                           revision=12, pin=None)
        self.assertEqual(content, b"<problem/>")
        post.assert_called_once_with(
            "https://polygon.codeforces.com/p85dIBF/u/a/problem.xml",
            data={"login": "me", "password": "pw", "revision": "12"},
            timeout=120,
        )

    def test_html_response_means_login_failed(self, post):
        post.return_value = response(content=b"<html>login</html>", content_type="text/html;charset=UTF-8")
        with self.assertRaisesRegex(PolygonError, "HTML page"):
            download("https://polygon.codeforces.com/c/50431a121273b7e31f4200e7/contest.xml", "me", "bad")


if __name__ == "__main__":
    unittest.main()
