"""Regression: uploading and editing a profile must preserve branding at login."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_company_users as fixtures
from app.routes.company_profile import router
from app.routes.company_logos import router as logo_router
from app.services import logo_storage


class CompanyLogoLoginTests(unittest.TestCase):
    def test_upload_profile_edit_and_fresh_login_preserve_logo(self):
        fixture = fixtures.CompanyUsersTests()
        fixture.setUp()
        try:
            fixture.client.app.include_router(router)
            fixture.client.app.include_router(logo_router)
            with tempfile.TemporaryDirectory() as directory, patch.object(logo_storage, "UPLOAD_ROOT", Path(directory)), patch.object(logo_storage, "_bucket", return_value=None):
                response = fixture.client.put(
                    "/company/profile", headers=fixture.admin_headers,
                    data={"company_name": "ABC"},
                    files={"logo": ("logo.png", b"logo bytes", "image/png")},
                )
                self.assertEqual(response.status_code, 200, response.text)
                url = response.json()["data"]["logo_url"]
                response = fixture.client.put(
                    "/company/profile", headers=fixture.admin_headers,
                    data={"company_name": "ABC updated"},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["data"]["logo_url"], url)
                fixture.db.expire_all()
                response = fixture.client.post("/auth/company/login", json={
                    "login_id": "adminabc", "password": "Admin1234",
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["company"]["logo_url"], url)
                self.assertEqual(fixture.client.get(url).content, b"logo bytes")
        finally:
            fixture.tearDown()
