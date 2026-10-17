"""Yükleme, gerçek katalog ve korumalı Range medya uçlarının HTTP testleri."""
import base64
from contextlib import closing
import http.cookiejar
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

VIDEO = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + bytes(range(128))
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fatihflix-media-test-")
        self.original_data_dir = server.DATA_DIR
        server.DATA_DIR = Path(self.temp.name)
        server.init_db()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        self.admin = self.client()
        self.member = self.client()
        self.anonymous = self.client()
        for client, email in ((self.admin, "admin@example.com"), (self.member, "member@example.com")):
            status, _, _ = self.json_request("/api/register", {
                "name": "Test Üye", "email": email, "password": "test-parola-123",
            }, client=client)
            self.assertEqual(status, 200)
        with closing(server.connect()) as db:
            db.execute("UPDATE users SET role='admin' WHERE email=?", ("admin@example.com",))
            db.commit()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(timeout=5)
        server.DATA_DIR = self.original_data_dir
        with server.LOCK:
            server.SESSIONS.clear()
            server.ATTEMPTS.clear()
        self.temp.cleanup()

    @staticmethod
    def client():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, data=None, client=None, method=None, headers=None):
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            response = (client or self.admin).open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    def json_request(self, path, data=None, client=None, headers=None):
        status, raw, response_headers = self.request(path, json.dumps(data).encode() if data is not None else None,
            client=client, headers={"Content-Type": "application/json", **(headers or {})})
        return status, json.loads(raw), response_headers

    def upload(self, kind="video", data=VIDEO, content_type="video/mp4", client=None):
        status, raw, headers = self.request(f"/api/admin/uploads?kind={kind}", data,
            client=client, headers={"Content-Type": content_type})
        return status, json.loads(raw), headers

    def create_movie(self, **changes):
        status, payload, _ = self.upload()
        self.assertEqual(status, 201, payload)
        fields = {"title": "Test Filmi", "description": "Gerçek yüklenen test içeriğinin açıklaması.",
            "genre": "Dram", "type": "Film", "year": 2026, "videoId": payload["asset"]["id"]}
        fields.update(changes)
        status, payload, _ = self.json_request("/api/admin/content", fields)
        self.assertEqual(status, 201, payload)
        return payload["movie"]

    def test_fresh_catalog_has_only_demo_seed_entries(self):
        status, payload, _ = self.json_request("/api/catalog", client=self.anonymous)
        self.assertEqual(status, 200)
        self.assertTrue(payload["movies"])
        self.assertTrue(all(movie["demo"] for movie in payload["movies"]))

    def test_admin_authorization_for_upload_and_content(self):
        for client, expected in ((self.anonymous, 401), (self.member, 403)):
            with self.subTest(expected=expected):
                self.assertEqual(self.upload(client=client)[0], expected)
                self.assertEqual(self.json_request("/api/admin/content", {}, client=client)[0], expected)

    def test_upload_signatures_and_types(self):
        invalid = [("video", b"not an mp4", "video/mp4"),
            ("cover", b"not an image", "image/png"),
            ("cover", b"<svg></svg>", "image/svg+xml"), ("unknown", VIDEO, "video/mp4")]
        for kind, data, content_type in invalid:
            with self.subTest(kind=kind, content_type=content_type):
                self.assertIn(self.upload(kind, data, content_type)[0], (400, 415))
        status, payload, _ = self.upload()
        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["asset"]["kind"], "video")
        self.assertEqual(payload["asset"]["url"], "/media/" + payload["asset"]["id"])

    def test_catalog_public_cover_and_member_video(self):
        status, payload, _ = self.upload("cover", PNG, "image/png")
        self.assertEqual(status, 201, payload)
        cover = payload["asset"]
        movie = self.create_movie(coverId=cover["id"])
        catalog = self.json_request("/api/catalog", client=self.anonymous)[1]["movies"]
        published = [m for m in catalog if not m["demo"]]
        self.assertEqual([m["id"] for m in published], [movie["id"]])
        self.assertEqual(published[0]["title"], "Test Filmi")
        status, body, headers = self.request(cover["url"], client=self.anonymous)
        self.assertEqual(status, 200)
        self.assertEqual(body, PNG)
        self.assertTrue(headers["Content-Type"].startswith("image/png"))
        self.assertEqual(self.request(movie["video"], client=self.anonymous)[0], 401)
        status, body, headers = self.request(movie["video"], client=self.member)
        self.assertEqual(status, 200)
        self.assertEqual(body, VIDEO)
        self.assertEqual(headers["Content-Length"], str(len(VIDEO)))

    def test_upload_rejects_oversized_declared_body_before_reading(self):
        for kind, size, mime in (("video", 2*1024**3 + 1, "video/mp4"),
                ("cover", 10*1024**2 + 1, "image/png")):
            with self.subTest(kind=kind):
                status, _, _ = self.request(f"/api/admin/uploads?kind={kind}", b"small",
                    headers={"Content-Type": mime, "Content-Length": str(size)})
                self.assertEqual(status, 413)

    def test_range_normal_open_suffix_and_head(self):
        movie = self.create_movie()
        for value, start, end in (("bytes=2-8", 2, 8), ("bytes=10-", 10, len(VIDEO)-1),
                ("bytes=-8", len(VIDEO)-8, len(VIDEO)-1), ("bytes=0-9999", 0, len(VIDEO)-1)):
            with self.subTest(range=value):
                status, body, headers = self.request(movie["video"], client=self.member, headers={"Range": value})
                self.assertEqual(status, 206)
                self.assertEqual(body, VIDEO[start:end+1])
                self.assertEqual(headers["Content-Range"], f"bytes {start}-{end}/{len(VIDEO)}")
                self.assertEqual(headers["Content-Length"], str(end-start+1))
                self.assertEqual(headers["Accept-Ranges"], "bytes")
        status, body, headers = self.request(movie["video"], client=self.member, method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Content-Length"], str(len(VIDEO)))
        status, body, headers = self.request(movie["video"], client=self.member, method="HEAD", headers={"Range": "bytes=3-7"})
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Content-Length"], str(len(VIDEO)))

    def test_invalid_ranges(self):
        movie = self.create_movie()
        for value in ("bytes=9999-", "bytes=8-2", "bytes=-0", "bytes=", "bytes=a-b", "bytes=0-1,3-4", "items=0-1",
                "bytes=" + "9"*5000 + "-", "bytes=-" + "9"*5000):
            with self.subTest(range=value):
                status, _, headers = self.request(movie["video"], client=self.member, headers={"Range": value})
                self.assertEqual(status, 416)
                self.assertEqual(headers["Content-Range"], f"bytes */{len(VIDEO)}")

    def test_media_filename_cannot_escape_storage(self):
        asset = self.upload()[1]["asset"]
        with closing(server.connect()) as db:
            db.execute("UPDATE assets SET filename='../fatihflix.db' WHERE id=?", (asset["id"],))
            db.commit()
        self.assertEqual(self.request(asset["url"])[0], 403)

    def test_content_metadata_validation(self):
        status, payload, _ = self.upload()
        self.assertEqual(status, 201, payload)
        valid = {"title": "Film", "description": "Test açıklaması.", "genre": "Dram",
            "type": "Film", "year": 2026, "videoId": payload["asset"]["id"]}
        for change in ({"title": ""}, {"description": ""}, {"genre": "Bilinmeyen"},
                {"title": None}, {"description": None}, {"genre": ["Dram"]},
                {"type": "Oyun"}, {"year": "2026"}, {"year": True}, {"year": 1887}, {"year": 2101},
                {"videoId": "does-not-exist"}, {"coverId": "does-not-exist"},
                {"coverId": valid["videoId"]}, {"videoId": None}):
            with self.subTest(change=change):
                self.assertIn(self.json_request("/api/admin/content", {**valid, **change})[0], (400, 404))
        self.assertTrue(all(movie["demo"] for movie in self.json_request("/api/catalog")[1]["movies"]))

    def test_uploaded_content_works_with_favorites_progress_and_recommendations(self):
        movie = self.create_movie()
        status, payload, _ = self.json_request("/api/favorites", {"id": movie["id"]}, client=self.member)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["user"]["favorites"], [movie["id"]])
        self.assertIn(movie["id"], payload["recommendations"])
        catalog = self.json_request("/api/catalog")[1]["movies"]
        genres = {item["id"]: item["genre"] for item in catalog}
        self.assertEqual(genres[payload["recommendations"][0]], "Dram")
        status, payload, _ = self.json_request("/api/progress", {
            "id": movie["id"], "position": 24, "duration": 120}, client=self.member)
        self.assertEqual(status, 200, payload)
        user = self.json_request("/api/me", client=self.member)[1]["user"]
        self.assertEqual(user["history"][movie["id"]]["position"], 24)
        server.init_db()
        persisted = self.json_request("/api/catalog")[1]["movies"]
        self.assertIn(movie["id"], [item["id"] for item in persisted])

    def test_quality_variants_replace_label_preserve_original_and_support_range(self):
        movie = self.create_movie()
        self.assertEqual(movie["qualities"], [])
        alternate = VIDEO + b"quality-720"
        status, payload, _ = self.upload(data=alternate)
        self.assertEqual(status, 201)
        asset = payload["asset"]
        status, payload, _ = self.json_request("/api/admin/qualities", {
            "id": movie["id"], "assetId": asset["id"], "quality": "720p"})
        self.assertEqual(status, 200, payload)
        updated = payload["movie"]
        self.assertEqual(updated["video"], movie["video"])
        self.assertEqual(updated["qualities"], [{"label": "720p", "src": asset["url"]}])
        self.assertEqual(self.request(asset["url"], client=self.anonymous)[0], 401)
        status, body, headers = self.request(asset["url"], client=self.member, headers={"Range": "bytes=5-14"})
        self.assertEqual(status, 206)
        self.assertEqual(body, alternate[5:15])
        self.assertEqual(headers["Content-Range"], f"bytes 5-14/{len(alternate)}")
        replacement = self.upload(data=VIDEO + b"replacement")[1]["asset"]
        for quality in ("720p", "360p", "1080p"):
            status, payload, _ = self.json_request("/api/admin/qualities", {
                "id": movie["id"], "assetId": replacement["id"], "quality": quality})
            self.assertEqual(status, 200)
        variants = payload["movie"]["qualities"]
        self.assertEqual([entry["label"] for entry in variants], ["360p", "720p", "1080p"])
        self.assertTrue(all(entry["src"] == replacement["url"] for entry in variants))
        server.init_db()
        persisted = next(item for item in self.json_request("/api/catalog")[1]["movies"] if item["id"] == movie["id"])
        self.assertEqual(persisted["qualities"], variants)
        self.assertEqual(persisted["video"], movie["video"])

    def test_quality_variant_permissions_and_validation(self):
        movie = self.create_movie()
        asset = self.upload()[1]["asset"]
        valid = {"id": movie["id"], "assetId": asset["id"], "quality": "1080p"}
        for client, expected in ((self.anonymous, 401), (self.member, 403)):
            self.assertEqual(self.json_request("/api/admin/qualities", valid, client=client)[0], expected)
        for change in ({"quality": "4K"}, {"quality": None}, {"quality": ["720p"]}, {"id": []}, {"assetId": None},
                {"assetId": "missing"}, {"id": "aurora"}):
            with self.subTest(change=change):
                self.assertEqual(self.json_request("/api/admin/qualities", {**valid, **change})[0], 400)
        self.assertEqual(self.json_request("/api/admin/qualities", {**valid, "id": "missing"})[0], 404)
        cover = self.upload("cover", PNG, "image/png")[1]["asset"]
        self.assertEqual(self.json_request("/api/admin/qualities", {**valid, "assetId": cover["id"]})[0], 400)
        with closing(server.connect()) as db:
            db.execute("UPDATE users SET role='admin' WHERE email='member@example.com'")
            db.commit()
        foreign = self.upload(client=self.member)[1]["asset"]
        self.assertEqual(self.json_request("/api/admin/qualities", {**valid, "assetId": foreign["id"]})[0], 400)
        self.assertTrue(all("qualities" in item for item in self.json_request("/api/catalog")[1]["movies"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
