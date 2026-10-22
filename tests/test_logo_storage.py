import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routes.company_logos import router
from app.services import logo_storage


class LogoStorageTests(unittest.TestCase):
    def test_local_upload_is_served_from_backend_upload_root(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"K_SERVICE": "", "COMPANY_LOGO_BUCKET": ""}), patch.object(logo_storage, "UPLOAD_ROOT", Path(folder)):
            url = logo_storage.save_logo(b"png contents", "image/png")
            app = FastAPI()
            app.include_router(router)
            with TestClient(app) as client:
                response = client.get(url)
            self.assertEqual(response.content, b"png contents")
            self.assertEqual(response.headers["content-type"], "image/png")

    def test_bucket_upload_and_read_use_same_key_without_local_files(self):
        bucket = Mock()
        bucket.blob.return_value.download_as_bytes.return_value = b"webp contents"
        with patch.object(logo_storage, "_bucket", return_value=bucket):
            url = logo_storage.save_logo(b"webp contents", "image/webp")
            # Mock the SDK exception import without needing credentials or network.
            import sys
            from types import ModuleType
            exceptions = ModuleType("google.api_core.exceptions")
            exceptions.NotFound = type("NotFound", (Exception,), {})
            with patch.dict(sys.modules, {"google.api_core.exceptions": exceptions}):
                self.assertEqual(logo_storage.read_logo(url.rsplit("/", 1)[1]), b"webp contents")
        key = url.removeprefix("/uploads/")
        self.assertEqual(bucket.blob.call_args_list[0].args, (key,))
        self.assertEqual(bucket.blob.call_args_list[1].args, (key,))
        bucket.blob.return_value.upload_from_string.assert_called_once_with(
            b"webp contents", content_type="image/webp", if_generation_match=0, timeout=30,
        )

    def test_cloud_run_without_bucket_rejects_ephemeral_upload(self):
        with patch.dict(os.environ, {"K_SERVICE": "api", "COMPANY_LOGO_BUCKET": ""}):
            with self.assertRaises(HTTPException) as error:
                logo_storage.save_logo(b"contents", "image/png")
        self.assertEqual(error.exception.status_code, 503)

    def test_invalid_filename_is_rejected_before_storage_access(self):
        with patch.object(logo_storage, "_bucket") as bucket:
            with self.assertRaises(HTTPException) as error:
                logo_storage.read_logo("../secret.png")
            bucket.assert_not_called()
        self.assertEqual(error.exception.status_code, 404)
