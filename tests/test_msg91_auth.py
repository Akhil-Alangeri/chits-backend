"""No real SMS, secrets or production database calls."""
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import get_db
from app.core.security import decode_access_token
from app.routes.customer.msg91_auth_router import router
from app.services.customer.msg91_auth import msg91_auth_service as service
from app.services.customer.msg91_auth import msg91_otp_service as provider
from app.services.customer.msg91_auth.msg91_cooldown import Msg91LoginState


class Msg91AuthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Msg91LoginState.__table__.create(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.lookup = patch.object(service, "get_customer_by_mobile", return_value=SimpleNamespace(id=17, customer_code="C17"))
        self.lookup_mock = self.lookup.start()
        self.send = patch.object(provider, "send_otp", new_callable=AsyncMock)
        self.send_mock = self.send.start()
        self.send_mock.return_value = None
        self.verify = patch.object(provider, "verify_otp", new_callable=AsyncMock)
        self.verify_mock = self.verify.start()
        self.body = {"mobile_number": "9876543210"}

    def tearDown(self):
        self.lookup.stop(); self.send.stop(); self.verify.stop()
        self.db.close(); self.engine.dispose()

    def post(self, path, body=None):
        return self.client.post("/customer/msg91-auth/" + path, json=body or self.body)

    def test_normalization_cooldown_resend_and_no_otp_response(self):
        response = self.post("send-otp", {"mobile_number": "+919876543210"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"success", "message", "resend_after", "request_id"})
        self.send_mock.assert_awaited_once_with("9876543210")
        for endpoint in ("send-otp", "resend-otp"):
            blocked = self.post(endpoint)
            self.assertEqual(blocked.status_code, 429)
            self.assertTrue(1 <= blocked.json()["retry_after"] <= 60)
            self.assertEqual(blocked.headers["Retry-After"], str(blocked.json()["retry_after"]))
        state = self.db.get(Msg91LoginState, "9876543210")
        state.next_send_at = service.utcnow() - timedelta(seconds=1)
        self.db.commit()
        self.assertEqual(self.post("resend-otp").status_code, 200)
        self.assertEqual(self.send_mock.await_count, 2)

    def test_ineligible_and_invalid_requests_never_send(self):
        self.lookup_mock.return_value = None
        self.assertEqual(self.post("send-otp").status_code, 401)
        self.assertEqual(self.post("send-otp", {"mobile_number": "abc9876543210"}).status_code, 400)
        self.assertEqual(self.post("send-otp", {"mobile_number": "1234567890"}).status_code, 400)
        self.send_mock.assert_not_awaited()

    def test_verify_existing_jwt_and_replay_block(self):
        self.post("send-otp")
        body = dict(self.body, otp="123456")
        response = self.post("verify-otp", body)
        self.assertEqual(response.status_code, 200)
        payload = decode_access_token(response.json()["access_token"])
        self.assertEqual(payload["sub"], "customer:17")
        self.assertEqual(payload["customer_profile_id"], 17)
        self.assertEqual(payload["token_type"], "customer")
        self.assertEqual(payload["exp"] - payload["iat"], 86400)
        self.assertEqual(self.post("verify-otp", body).status_code, 401)
        self.assertEqual(self.verify_mock.await_count, 1)

    def test_invalid_expired_attempts_and_provider_outage(self):
        self.post("send-otp")
        self.verify_mock.side_effect = HTTPException(503, "OTP service is temporarily unavailable.")
        self.assertEqual(self.post("verify-otp", dict(self.body, otp="123456")).status_code, 503)
        self.assertEqual(self.db.get(Msg91LoginState, "9876543210").attempts, 0)
        self.verify_mock.side_effect = HTTPException(401, "Invalid or expired OTP.")
        for _ in range(5):
            self.assertEqual(self.post("verify-otp", dict(self.body, otp="123456")).status_code, 401)
        self.assertEqual(self.post("verify-otp", dict(self.body, otp="123456")).status_code, 429)
        self.assertEqual(self.post("verify-otp", dict(self.body, otp="abcdef")).status_code, 400)

    def test_eligibility_rechecked_after_verification(self):
        self.post("send-otp")
        self.lookup_mock.return_value = None
        self.assertEqual(self.post("verify-otp", dict(self.body, otp="123456")).status_code, 401)

    def test_provider_send_failure_retains_reservation(self):
        self.send_mock.side_effect = HTTPException(503, "OTP service is temporarily unavailable.")
        self.assertEqual(self.post("send-otp").status_code, 503)
        self.assertEqual(self.post("send-otp").status_code, 429)
        self.assertEqual(self.send_mock.await_count, 1)
        self.assertFalse(self.db.get(Msg91LoginState, "9876543210").active)

    def test_expired_or_unsent_session_never_reaches_provider(self):
        body = dict(self.body, otp="123456")
        self.assertEqual(self.post("verify-otp", body).status_code, 401)
        self.assertEqual(self.post("resend-otp").status_code, 400)
        self.post("send-otp")
        state = self.db.get(Msg91LoginState, "9876543210")
        state.sent_at = service.utcnow() - timedelta(minutes=11)
        self.db.commit()
        self.assertEqual(self.post("verify-otp", body).status_code, 401)
        self.verify_mock.assert_not_awaited()


class Msg91ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def check_response(self, data, status=200, expected=None):
        response = httpx.Response(status, json=data)
        with patch.dict("os.environ", {"MSG91_AUTH_KEY": "test-key", "MSG91_TEMPLATE_ID": "test-template"}), patch.object(httpx.AsyncClient, "request", new=AsyncMock(return_value=response)):
            if expected:
                with self.assertRaises(HTTPException) as raised:
                    await provider.verify_otp("9876543210", "123456")
                self.assertEqual(raised.exception.status_code, expected)
            else:
                await provider.verify_otp("9876543210", "123456")

    async def test_send_contract_and_safe_request_id(self):
        request_id = "3567736c53515771356c4878"
        with patch.dict("os.environ", {"MSG91_AUTH_KEY": "test-key", "MSG91_TEMPLATE_ID": "test-template"}), patch.object(httpx.AsyncClient, "request", new=AsyncMock(return_value=httpx.Response(200, json={"type": "success", "message": request_id}))) as request:
            result = await provider.send_otp("9876543210")
            self.assertEqual(result, request_id)
            args, kwargs = request.await_args
            self.assertEqual(args, ("POST", provider.BASE_URL))
            self.assertEqual(kwargs["params"], {"mobile": "919876543210", "template_id": "test-template", "otp_length": 6, "otp_expiry": 10, "invisible": 0, "realTimeResponse": 1})
            self.assertEqual(kwargs["headers"]["authkey"], "test-key")
        with patch.dict("os.environ", {"MSG91_AUTH_KEY": "test-key", "MSG91_TEMPLATE_ID": "test-template"}), patch.object(httpx.AsyncClient, "request", new=AsyncMock(return_value=httpx.Response(200, json={"type": "success", "message": "Unexpected provider text"}))):
            self.assertIsNone(await provider.send_otp("9876543210"))

    async def test_ip_whitelist_rejection_is_configuration_failure(self):
        with patch.dict("os.environ", {"MSG91_AUTH_KEY": "test-key", "MSG91_TEMPLATE_ID": "test-template"}), patch.object(httpx.AsyncClient, "request", new=AsyncMock(return_value=httpx.Response(200, json={"type": "error", "message": "IP is not whitelisted"}))):
            with self.assertRaises(HTTPException) as raised:
                await provider.send_otp("9876543210")
            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(raised.exception.headers["X-OTP-Error-Code"], "msg91_ip_not_whitelisted")

    async def test_wrong_otp_and_provider_errors_are_different(self):
        await self.check_response({"type": "error", "message": "OTP not match"}, expected=401)
        await self.check_response({"type": "error", "message": "OTP expired"}, expected=401)
        await self.check_response({"type": "error", "message": "Invalid authkey"}, expected=502)
        await self.check_response({"type": "success", "message": "OTP already verified"}, expected=401)
        await self.check_response({"type": "success", "message": "OTP verified success"})
        await self.check_response([], expected=502)
        await self.check_response({}, status=503, expected=503)


if __name__ == "__main__":
    unittest.main()
