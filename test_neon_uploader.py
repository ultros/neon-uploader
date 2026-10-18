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

class SharedFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.share = self.home / "share"
        self.share.mkdir()
        (self.share / "projects" / "alpha").mkdir(parents=True)
        (self.share / "projects" / "alpha" / "report.txt").write_text("ok")
        (self.share / ".hidden").write_text("hidden")
        (self.home / "private.txt").write_text("private")
        self.app = uploader.create_app(self.share, access_token="test-secret", create_root=False)
        self.client = self.app.test_client()
        self.auth = {"Authorization": "Basic bmVvbjp0ZXN0LXNlY3JldA=="}

    def test_nested_and_hidden_files_visible_under_share(self):
        data = self.client.get("/api/files", headers=self.auth).json
        self.assertEqual(data["root_name"], "Share")
        self.assertEqual({x["name"] for x in data["items"]}, {"projects", ".hidden"})
        child = self.client.get("/api/files?path=projects/alpha", headers=self.auth).json
        self.assertEqual([i["name"] for i in child["items"]], ["report.txt"])
        download = self.client.get("/api/download?path=projects/alpha/report.txt", headers=self.auth)
        self.assertEqual(download.data, b"ok")

    def test_above_share_is_blocked(self):
        for path in ("../private.txt", "/tmp", "projects/../../private.txt"):
            resp = self.client.get("/api/download", query_string={"path": path}, headers=self.auth)
            self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.client.get("/api/files?path=projects", headers=self.auth).status_code, 200)

    def test_explicit_root_must_exist(self):
        absent = self.home / "typo-missing-share"
        with self.assertRaisesRegex(RuntimeError, "Share root missing"):
            uploader.create_app(absent, access_token="x", create_root=False)
        self.assertFalse(absent.exists())

    def test_share_root_choice_saved_and_env_override(self):
        from unittest import mock
        config = self.home / "config" / "share-root"
        with mock.patch.object(uploader, "SHARE_ROOT_PATH", config):
            with mock.patch.dict(os.environ, {"NEON_SHARE_ROOT": str(self.share)}):
                self.assertEqual(uploader.choose_share_root(), self.share)
                self.assertFalse(config.exists())
            with mock.patch.dict(os.environ, {"NEON_SHARE_ROOT": ""}):
                with mock.patch("builtins.input", return_value=str(self.share)):
                    self.assertEqual(uploader.choose_share_root(), self.share)
                self.assertEqual(config.read_text().strip(), str(self.share))
                with mock.patch("builtins.input", return_value=""):
                    self.assertEqual(uploader.choose_share_root(), self.share)

    def test_unconfigured_directory_refuses_creation(self):
        from unittest import mock
        missing = self.home / "missing-share"
        with mock.patch.object(uploader, "SHARE_ROOT_PATH", self.home / "config" / "share-root"):
            with mock.patch.dict(os.environ, {"NEON_SHARE_ROOT": str(missing)}):
                with self.assertRaisesRegex(RuntimeError, "does not exist"):
                    uploader.choose_share_root()
        self.assertFalse(missing.exists())


class RootSelectionTests(unittest.TestCase):
    """The server must open a persistent real share, never make an empty replacement."""

    def setUp(self):
        from unittest import mock
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.home = Path(self.work.name)
        self.share = self.home / "existing-share"
        self.share.mkdir()
        (self.share / "keep-me.txt").write_text("persistent")
        self.config = self.home / "config" / "share-root"
        patcher = mock.patch.object(uploader, "SHARE_ROOT_PATH", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_explicit_share_root_remains_persistent(self):
        from unittest import mock
        with mock.patch.object(uploader, "discover_samba_shares", return_value=[]), \
             mock.patch.dict(os.environ, {"NEON_SHARE_ROOT": ""}):
            result = uploader.choose_share_root(explicit=str(self.share))
            self.assertEqual(result, self.share)
            self.assertEqual(self.config.read_text().strip(), str(self.share))
            with mock.patch('sys.stdin.isatty', return_value=False):
                result2 = uploader.choose_share_root()
            self.assertEqual(result2, self.share)
            self.assertEqual((self.share / "keep-me.txt").read_text(), "persistent")

    def test_missing_share_fails_and_does_not_create_folder(self):
        from unittest import mock
        nonexistent = self.home / "missing-drive"
        with mock.patch.object(uploader, "discover_samba_shares", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "missing or unavailable"):
                uploader.choose_share_root(explicit=str(nonexistent))
        self.assertFalse(nonexistent.exists())
        self.assertFalse(self.config.exists())

    def test_no_known_share_does_not_fall_back_to_empty_uploads(self):
        from unittest import mock
        with mock.patch.object(uploader, "discover_samba_shares", return_value=[]), \
             mock.patch.dict(os.environ, {"NEON_SHARE_ROOT": ""}), \
             mock.patch('sys.stdin.isatty', return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Share root is not configured"):
                uploader.choose_share_root()
        self.assertFalse(self.config.exists())

    def test_mount_guard_refuses_unmounted_path(self):
        from unittest import mock
        with mock.patch.object(uploader, "discover_samba_shares", return_value=[]), \
             mock.patch.dict(os.environ, {"NEON_REQUIRE_MOUNT": "1"}), \
             mock.patch.object(uploader.os.path, "ismount", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "mount is not active"):
                uploader.choose_share_root(explicit=str(self.share))

    def test_discover_samba_ignores_pseudo_shares(self):
        from unittest import mock
        conf = self.home / 'smb.conf'
        conf.write_text(f"[global]\npath = /\n[backup]\npath = {self.share}\n"
                        "[homes]\npath = /home/%U\n[remote]\npath = /missing/path\n")
        with mock.patch.object(uploader.shutil, 'which', return_value=None):
            self.assertEqual(uploader.discover_samba_shares(conf), [self.share])


class WindowsClientLoginTests(unittest.TestCase):
    """End-to-end browser ticket and cookie exchange (run when Flask is available)."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = uploader.create_app(self.directory.name, access_token="a-long-test-password").test_client()
        import base64
        cred = base64.b64encode(b"neon:a-long-test-password").decode("ascii")
        self.auth = {"Authorization": "Basic " + cred}

    def test_windows_browser_auto_login(self):
        base = "http://pi.lan:8080"
        self.assertEqual(self.client.get("/api/files", base_url=base).status_code, 401)
        response = self.client.post("/api/auth/ticket", base_url=base, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        ticket = response.json["ticket"]
        self.assertNotEqual(ticket, "a-long-test-password")
        landing = self.client.get("/__neon_login", base_url=base)
        self.assertEqual(landing.status_code, 200)
        self.assertIn("no-referrer", landing.headers["Referrer-Policy"])
        result = self.client.post("/__neon_login", json={"ticket": ticket}, base_url=base)
        self.assertEqual(result.status_code, 200)
        self.assertIn("HttpOnly", result.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", result.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/api/files", base_url=base).status_code, 200)
        self.assertEqual(self.client.post("/__neon_login", json={"ticket": ticket}, base_url=base).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/ticket", base_url=base).status_code, 403)

    def test_ticket_bound_to_issuer_ip(self):
        base = "http://pi.lan:8080"
        t = self.client.post("/api/auth/ticket", base_url=base, headers=self.auth).json["ticket"]
        remote = {"REMOTE_ADDR": "192.0.2.19"}
        failed = self.client.post("/__neon_login", json={"ticket": t}, base_url=base,
                                  environ_overrides=remote)
        self.assertEqual(failed.status_code, 403)
        self.assertEqual(self.client.post("/__neon_login", json={"ticket": t}, base_url=base).status_code, 200)
        self.assertEqual(self.client.get("/api/files", base_url=base, environ_overrides=remote).status_code, 401)


if __name__ == "__main__":
    unittest.main()
