"""Run with: python -m unittest discover -p 'test_*.py'"""
import importlib.util
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("neon-uploader.py")
spec = importlib.util.spec_from_file_location("neon_uploader", SCRIPT)
uploader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploader)


class FileManagerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = uploader.create_app(self.directory.name, access_token="test-secret").test_client()
        self.auth = {"Authorization": "Basic bmVvbjp0ZXN0LXNlY3JldA=="}

    def get(self, url):
        return self.client.get(url, headers=self.auth)

    def post(self, url, json):
        return self.client.post(url, json=json, headers=self.auth)

    def test_auth_and_listing(self):
        self.assertEqual(self.client.get("/api/files").status_code, 401)
        self.assertEqual(self.get("/api/files").json["items"], [])
        self.post("/api/folders", {"path": "", "name": "photos"})
        response = self.get("/api/files")
        self.assertEqual(response.json["items"][0]["type"], "directory")

    def test_upload_unique_names_download_and_zip(self):
        headers = dict(self.auth)
        for _ in range(2):
            response = self.client.post("/upload", data={"files": (io.BytesIO(b"hello"), "example.txt")}, headers=headers)
            self.assertEqual(response.status_code, 200)
        names = [i["name"] for i in self.get("/api/files").json["items"]]
        self.assertEqual(names, ["example.txt", "example_001.txt"])
        downloaded = self.get("/api/download?path=example.txt")
        self.assertEqual(downloaded.data, b"hello")
        archive_response = self.post("/api/download-zip", {"paths": names})
        self.assertEqual(archive_response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(archive_response.data)) as zipped:
            self.assertEqual(sorted(zipped.namelist()), names)

    def test_rename_and_delete(self):
        self.post("/api/folders", {"path": "", "name": "folder"})
        response = self.post("/api/rename", {"path": "folder", "name": "new folder"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post("/api/delete", {"paths": ["new folder"]}).status_code, 400)
        self.assertEqual(self.post("/api/delete", {"paths": ["new folder"], "confirm": True}).json["deleted"], 1)
        self.assertFalse((Path(self.directory.name) / "new folder").exists())

    def test_reject_traversal_and_symlinks(self):
        (Path(self.directory.name) / "safe.txt").write_text("safe")
        for path in ("../", "/etc/passwd", "x/../safe.txt", "x\\safe.txt"):
            self.assertEqual(self.get("/api/download?path=" + path).status_code, 400)
        outside = Path(self.directory.name).parent / "outside-neon-file.txt"
        link = Path(self.directory.name) / "bad-link.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            return
        self.assertEqual(self.get("/api/download?path=bad-link.txt").status_code, 403)
        self.assertNotIn("bad-link.txt", [i["name"] for i in self.get("/api/files").json["items"]])

    def test_reject_origin_and_duplicate_name(self):
        headers = dict(self.auth, Origin="https://example.com")
        response = self.client.post("/api/folders", json={"path": "", "name": "x"}, headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.post("/api/folders", {"path": "", "name": "x"}).status_code, 201)
        self.assertEqual(self.post("/api/folders", {"path": "", "name": "x"}).status_code, 409)
        self.assertEqual(self.post("/api/rename", {"path": "x", "name": "../escape"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
