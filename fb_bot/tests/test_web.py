import io
import os
import unittest
from unittest import mock

from fbbot.config import Config
from fbbot.graph import GraphClient
from fbbot.web import create_app
from test_bot import make_session


class WebTests(unittest.TestCase):
    def setUp(self):
        self.sess = make_session()
        with mock.patch.dict(os.environ, {"PANEL_PASSWORD": "segredo"}):
            app = create_app(Config(user_token="U"), GraphClient("U", session=self.sess))
        app.config["TESTING"] = True
        self.c = app.test_client()

    def login(self):
        return self.c.post("/login", data={"senha": "segredo"})

    def test_requires_login(self):
        self.assertEqual(self.c.get("/").status_code, 302)
        self.assertIn("incorreta", self.c.post("/login", data={"senha": "x"}).get_data(as_text=True))

    def test_home_and_upload_reel(self):
        self.login()
        self.assertIn("Novo Reel", self.c.get("/").get_data(as_text=True))
        r = self.c.post("/reel", data={"page": "123", "descricao": "Oi ❤️",
                                       "video": (io.BytesIO(b"abc"), "v.mp4")},
                        content_type="multipart/form-data")
        self.assertIn("enviado", r.get_data(as_text=True))
        finish = self.sess.post.call_args_list[2].kwargs["data"]
        self.assertEqual(finish["description"], "Oi ❤️")

    def test_scheduled_reel(self):
        self.login()
        r = self.c.post("/reel", data={"page": "123", "agendar": "2030-01-01T10:00",
                                       "video": (io.BytesIO(b"abc"), "v.mov")},
                        content_type="multipart/form-data")
        self.assertIn("agendado", r.get_data(as_text=True))
        self.assertEqual(self.sess.post.call_args_list[2].kwargs["data"]["video_state"], "SCHEDULED")

    def test_text_post(self):
        self.login()
        r = self.c.post("/post", data={"page": "123", "mensagem": "Olá"})
        self.assertIn("Post publicado", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
