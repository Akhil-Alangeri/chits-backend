"""Recovery tests use an isolated SQLite DB and mock SMS transport."""
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models
from app.core.database import Base, get_db
from app.core.security import hash_password, verify_password
from app.models import User
from app.routes.super_admin_auth import router

@compiles(BigInteger, 'sqlite')
def sqlite_int(element, compiler, **kw):
    return 'INTEGER'

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SUPER_ADMIN_RESET_USERNAME': 'admin', 'MOBILE_NUMBER': '9000000000', 'MSG91_AUTH_KEY': 'test', 'MSG91_TEMPLATE_ID': 'test'})
        self.env.start()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(id=1, login_id='admin', role='super_admin', status='active', password_hash=hash_password('OldPassword1'))
        self.db.add(self.user); self.db.commit()
        app = FastAPI(); app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.sms = patch('app.routes.super_admin_auth.httpx.AsyncClient.post', new_callable=AsyncMock)
        self.mock = self.sms.start()
        self.mock.return_value = Mock(status_code=200)
        self.mock.return_value.json.return_value = {'type': 'success'}

    def tearDown(self):
        self.sms.stop(); self.env.stop(); self.db.close(); self.engine.dispose()

    def send(self):
        response = self.client.post('/super-admin/auth/forgot-password', json={'username': 'admin'})
        self.assertEqual(response.status_code, 200, response.text)
        return self.mock.call_args.kwargs['params']['otp']

    def reset(self, otp):
        return self.client.post('/super-admin/auth/reset-password', json={'username': 'admin', 'otp': otp, 'new_password': 'NewPassword2'})

    def test_reset_consumes_otp_and_revokes_session(self):
        login = self.client.post('/super-admin/auth/login', json={'username': 'admin', 'password': 'OldPassword1'})
        token = login.json()['access_token']
        otp = self.send()
        self.assertNotEqual(self.user.reset_hash, otp)
        self.assertEqual(self.reset(otp).status_code, 200)
        self.assertTrue(verify_password('NewPassword2', self.user.password_hash))
        self.assertEqual(self.reset(otp).status_code, 400)
        self.assertEqual(self.client.get('/super-admin/auth/me', headers={'Authorization': 'Bearer '+token}).status_code, 401)

    def test_cooldown_and_attempt_limit(self):
        otp = self.send()
        self.assertEqual(self.client.post('/super-admin/auth/forgot-password', json={'username': 'admin'}).status_code, 429)
        wrong = '000000' if otp != '000000' else '111111'
        for _ in range(5): self.assertEqual(self.reset(wrong).status_code, 400)
        self.assertEqual(self.reset(otp).status_code, 400)
        self.user.reset_sent_at = datetime.utcnow() - timedelta(minutes=2); self.db.commit()
        self.assertEqual(self.client.post('/super-admin/auth/forgot-password', json={'username': 'admin'}).status_code, 429)

    def test_expired_otp(self):
        otp = self.send()
        self.user.reset_expires = datetime.utcnow() - timedelta(seconds=1); self.db.commit()
        self.assertEqual(self.reset(otp).status_code, 400)

    def test_unknown_account_never_sends_sms(self):
        self.assertEqual(self.client.post('/super-admin/auth/forgot-password', json={'username': 'other'}).status_code, 400)
        self.mock.assert_not_called()

    def test_provider_failure(self):
        self.mock.return_value.status_code = 500
        self.assertEqual(self.client.post('/super-admin/auth/forgot-password', json={'username': 'admin'}).status_code, 503)

if __name__ == '__main__': unittest.main()
