import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fbbot.cli import main
from fbbot.graph import GraphClient, GraphError, Page
from fbbot.queue import process_one


class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self._data


PAGE = Page("123", "Minha Página", "PAGE_TOKEN")


def make_session(status_seq=("ready",)):
    s = mock.MagicMock()
    statuses = iter(status_seq)

    def post(url, data=None, files=None, headers=None, timeout=None):
        if "rupload" in url:
            return FakeResp({"success": True})
        if data.get("upload_phase") == "start":
            return FakeResp({"video_id": "V1", "upload_url": "https://rupload.facebook.com/video-upload/v23.0/V1"})
        if data.get("upload_phase") == "finish":
            return FakeResp({"success": True})
        return FakeResp({"id": "POST1"})

    def get(url, params=None, timeout=None):
        if url.endswith("/V1"):
            return FakeResp({"status": {"video_status": next(statuses)}})
        if url.endswith("me/accounts"):
            return FakeResp({"data": [{"id": "123", "name": "Minha Página", "access_token": "PAGE_TOKEN"}]})
        return FakeResp({"data": []})

    s.post.side_effect = post
    s.get.side_effect = get
    return s


class ReelTests(unittest.TestCase):
    def test_publish_reel_local_file(self):
        sess = make_session(("processing", "ready"))
        client = GraphClient("USER", session=sess)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"x" * 10)
            f.flush()
            with mock.patch("fbbot.graph.time.sleep"):
                res = client.publish_reel(PAGE, f.name, description="Oi")
        self.assertEqual(res["video_id"], "V1")
        upload_call = sess.post.call_args_list[1]
        self.assertIn("rupload", upload_call.args[0])
        self.assertEqual(upload_call.kwargs["headers"]["file_size"], "10")
        self.assertEqual(upload_call.kwargs["headers"]["Authorization"], "OAuth PAGE_TOKEN")
        finish = sess.post.call_args_list[2].kwargs["data"]
        self.assertEqual(finish["video_state"], "PUBLISHED")
        self.assertEqual(finish["description"], "Oi")

    def test_publish_reel_url_scheduled(self):
        sess = make_session()
        client = GraphClient("USER", session=sess)
        client.publish_reel(PAGE, "https://exemplo.com/v.mp4", scheduled_time=2000000000)
        self.assertEqual(sess.post.call_args_list[1].kwargs["headers"]["file_url"], "https://exemplo.com/v.mp4")
        finish = sess.post.call_args_list[2].kwargs["data"]
        self.assertEqual(finish["video_state"], "SCHEDULED")
        self.assertEqual(finish["scheduled_publish_time"], 2000000000)

    def test_graph_error(self):
        sess = mock.MagicMock()
        sess.get.return_value = FakeResp({"error": {"message": "Invalid token"}}, 400)
        with self.assertRaises(GraphError):
            GraphClient("USER", session=sess).list_pages()


class QueueTests(unittest.TestCase):
    def test_queue_moves_published(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d)
            (q / "01.mp4").write_bytes(b"abc")
            (q / "01.txt").write_text("Legenda ❤️", encoding="utf-8")
            (q / "02.mp4").write_bytes(b"abc")
            client = GraphClient("USER", session=make_session())
            res = process_one(client, PAGE, q)
            self.assertEqual(res["video"], "01.mp4")
            self.assertTrue((q / "publicados" / "01.mp4").exists())
            self.assertTrue((q / "publicados" / "01.txt").exists())
            self.assertTrue((q / "02.mp4").exists())
            finish = client.session.post.call_args_list[2].kwargs["data"]
            self.assertEqual(finish["description"], "Legenda ❤️")

    def test_queue_error_goes_to_erros(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d)
            (q / "01.mp4").write_bytes(b"abc")
            sess = mock.MagicMock()
            sess.post.return_value = FakeResp({"error": {"message": "boom"}}, 400)
            res = process_one(GraphClient("USER", session=sess), PAGE, q)
            self.assertIn("boom", res["error"])
            self.assertTrue((q / "erros" / "01.mp4").exists())
            self.assertTrue((q / "erros" / "01.log").exists())

    def test_empty_queue(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(process_one(GraphClient("USER", session=make_session()), PAGE, Path(d)))


class CliTests(unittest.TestCase):
    def test_missing_token(self):
        with mock.patch.dict("os.environ", {"FB_USER_TOKEN": ""}):
            self.assertEqual(main(["--env", "/nao/existe", "pages"]), 1)


if __name__ == "__main__":
    unittest.main()
