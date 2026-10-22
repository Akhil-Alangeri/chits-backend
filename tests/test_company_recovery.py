"""Isolated recovery API tests; SMTP is always mocked."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
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
from app.models import Company, User
from app.models.admin.company_recovery import CompanyRecovery, RecoveryRate
from app.routes.company_recovery import router
from app.routes.auth import router as login_router

@compiles(BigInteger, 'sqlite')
def sqlite_int(element, compiler, **kw): return 'INTEGER'

class CompanyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        company = Company(id=1, company_name='One', email='admin@example.com', status='active')
        other = Company(id=2, company_name='Two', email='admin@example.com', status='active')
        self.db.add_all([company, other]); self.db.flush()
        for id, role, tenant in [(1,'company_admin',1),(2,'super_admin',None),(3,'customer',1),(4,'company_user',1),(5,'company_admin',2)]:
            self.db.add(User(id=id, login_id=f'user{id}', company_id=tenant, role=role, status='active', password_hash=hash_password('OldPassword1')))
        self.db.commit()
        app = FastAPI(); app.include_router(router); app.include_router(login_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.smtp = patch('app.routes.company_recovery.send_recovery_email'); self.mail = self.smtp.start()
        self.identity = {'login_id':'user1', 'email':'admin@example.com'}
    def tearDown(self):
        self.smtp.stop(); self.db.close(); self.engine.dispose()
    def send(self, identity=None):
        return self.client.post('/auth/company/forgot-password', json=identity or self.identity)
    def otp(self):
        self.assertEqual(self.send().status_code,200)
        return self.mail.call_args.args[2]
    def verify(self, otp):
        return self.client.post('/auth/company/verify-reset-otp',json={**self.identity,'otp':otp})
    def reset(self, token, password='NewPassword2'):
        return self.client.post('/auth/company/reset-password',json={'reset_token':token,'new_password':password})
    def state(self): return self.db.get(CompanyRecovery,1)
    def test_full_flow_login_and_reuse(self):
        otp=self.otp(); self.assertNotEqual(self.state().otp_hash,otp)
        token=self.verify(otp).json()['reset_token']
        self.assertEqual(self.verify(otp).status_code,400)
        self.assertEqual(self.reset(token).status_code,200)
        self.assertEqual(self.reset(token).status_code,400)
        for password, code in [('OldPassword1',401),('NewPassword2',200)]:
            self.assertEqual(self.client.post('/auth/company/login',json={'login_id':'user1','password':password}).status_code,code)
        self.assertTrue(verify_password('OldPassword1',self.db.get(User,5).password_hash))
    def test_unknown_and_ineligible_generic(self):
        generic=self.send({'login_id':'missing','email':'unknown@example.com'}).json()
        for id in [2,3,4]:
            self.assertEqual(self.send({'login_id':f'user{id}','email':'admin@example.com'}).json(),generic)
        self.db.get(User,1).status='inactive'; self.db.commit()
        self.assertEqual(self.send().json(),generic); self.mail.assert_not_called()
    def test_inactive_company(self):
        self.db.get(Company,1).status='inactive'; self.db.commit()
        self.send(); self.mail.assert_not_called()
    def test_wrong_email_tenant(self):
        self.send({'login_id':'user1','email':'other@example.com'}); self.mail.assert_not_called()
    def test_duplicate_email_selects_exact_login(self):
        self.send({'login_id':'user5','email':'admin@example.com'})
        self.assertIsNotNone(self.db.get(CompanyRecovery,5)); self.assertIsNone(self.state())
    def test_attempts(self):
        otp=self.otp(); wrong='000000' if otp!='000000' else '111111'
        for _ in range(5): self.assertEqual(self.verify(wrong).status_code,400)
        self.assertEqual(self.verify(otp).status_code,400)
    def test_expired_otp(self):
        otp=self.otp(); self.state().otp_expires=datetime.utcnow()-timedelta(seconds=1); self.db.commit()
        self.assertEqual(self.verify(otp).status_code,400)
    def test_cooldown_resend(self):
        otp=self.otp(); self.send(); self.assertEqual(self.mail.call_count,1)
        self.state().sent_at=datetime.utcnow()-timedelta(seconds=61); self.db.commit()
        with patch('app.routes.company_recovery.secrets.randbelow',return_value=(int(otp)+1)%1000000): self.send()
        self.assertEqual(self.mail.call_count,2); self.assertEqual(self.verify(otp).status_code,400)
    def test_token_expiry(self):
        token=self.verify(self.otp()).json()['reset_token']
        self.state().token_expires=datetime.utcnow()-timedelta(seconds=1); self.db.commit()
        self.assertEqual(self.reset(token).status_code,400)
    def test_provider_failure(self):
        self.mail.side_effect=RuntimeError('private provider data')
        with self.assertLogs('app.routes.company_recovery',level='ERROR') as logs: response=self.send()
        self.assertEqual(response.status_code,200); self.assertIsNone(self.state().otp_hash)
        self.assertNotIn('private provider data',' '.join(logs.output))
    def test_account_rate_limit(self):
        for _ in range(8): self.send()
        self.assertEqual(self.mail.call_count,1)
        self.state().sent_at=datetime.utcnow()-timedelta(seconds=61); self.db.commit(); self.send()
        self.assertEqual(self.mail.call_count,1)
    def test_source_rate_limit_all_endpoints(self):
        for _ in range(60): self.send({'login_id':'missing','email':'unknown@example.com'})
        self.assertEqual(self.send().status_code,429)
    def test_password_policy(self):
        token=self.verify(self.otp()).json()['reset_token']
        for password in ['short','x'*73]: self.assertEqual(self.reset(token,password).status_code,422)
        self.assertEqual(self.reset(token).status_code,200)
    def test_account_changed_after_verification(self):
        token=self.verify(self.otp()).json()['reset_token']
        self.db.get(User,1).password_hash=hash_password('ChangedPassword'); self.db.commit()
        self.assertEqual(self.reset(token).status_code,400)
    def test_deactivated_after_verification(self):
        token=self.verify(self.otp()).json()['reset_token']
        self.db.get(User,1).status='inactive'; self.db.commit()
        self.assertEqual(self.reset(token).status_code,400)

    def test_concurrent_verify_and_reset_single_winner(self):
        # Independent connections against a file DB; conditional updates also fence stale reads.
        import tempfile
        import sqlite3
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        otp=self.otp()
        with tempfile.TemporaryDirectory() as directory:
            filename=str(Path(directory)/'recovery.db')
            with sqlite3.connect(filename) as destination:
                source=self.engine.raw_connection()
                source.driver_connection.backup(destination)
                source.close()
            destination.close()
            engine=create_engine('sqlite:///'+filename,connect_args={'check_same_thread':False,'timeout':30})
            factory=sessionmaker(bind=engine)
            def database():
                with factory() as db: yield db
            app=FastAPI(); app.include_router(router); app.dependency_overrides[get_db]=database
            client=TestClient(app)
            def race(path, body):
                barrier=Barrier(2)
                def call():
                    barrier.wait()
                    return client.post(path,json=body)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(call) for _ in range(2)]
                    return [future.result() for future in futures]
            # Rate limiting has separate sequential durability tests; isolate token races here.
            with patch('app.routes.company_recovery.source_limit'):
                verified=race('/auth/company/verify-reset-otp',{**self.identity,'otp':otp})
                self.assertEqual(sorted(r.status_code for r in verified),[200,400])
                token=next(r.json()['reset_token'] for r in verified if r.status_code==200)
                results=race('/auth/company/reset-password',{'reset_token':token,'new_password':'NewPassword2'})
                self.assertEqual(sorted(r.status_code for r in results),[200,400])
            engine.dispose()
