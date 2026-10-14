"""Isolated API tests: no connection to the configured MySQL database."""
import json
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base, get_db
from app.core.security import hash_password, decode_access_token, create_access_token
from app.models.admin.company import Company
from app.models.admin.user import User
from app.models.admin.audit_log import AuditLog
from app.models.admin.chit_group import ChitGroup
from app.routes.auth import router as auth_router
from app.routes.company_users import router as users_router
from app.routes.chit_group import router as chits_router
from app.routes.audit_log_router import router as audit_router
from app.services.audit_log_service import create_audit_log


@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kw):
    return "INTEGER"


class CompanyUsersTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.db.add_all([Company(id=12, company_name="ABC", email="abc@example.com", status="active"),
                         Company(id=13, company_name="Other", email="other@example.com", status="active")])
        self.db.flush()
        self.db.add_all([User(id=1, company_id=12, login_id="adminabc", password_hash=hash_password("Admin1234"), role="company_admin", status="active"),
                         User(id=2, company_id=13, login_id="otheradmin", password_hash=hash_password("Admin1234"), role="company_admin", status="active"),
                         User(id=3, company_id=13, login_id="otherstaff", password_hash=hash_password("Staff1234"), role="company_user", status="active")])
        self.db.commit()
        self.db.add_all([ChitGroup(id=1, company_id=12, name="ABC chit", code="ABC001", chit_value=10000, monthly_emi=1000, duration_months=10, max_members=10),
                         ChitGroup(id=2, company_id=13, name="Other chit", code="OTH001", chit_value=10000, monthly_emi=1000, duration_months=10, max_members=10)])
        self.db.commit()
        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(users_router)
        app.include_router(chits_router)
        app.include_router(audit_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.admin_headers = self.login("adminabc", "Admin1234")

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def login(self, login_id, password):
        result = self.client.post("/auth/company/login", json={"login_id": login_id, "password": password})
        self.assertEqual(result.status_code, 200, result.text)
        return {"Authorization": "Bearer " + result.json()["access_token"]}

    def create(self):
        response = self.client.post("/company/users", headers=self.admin_headers,
                                    json={"full_name": "Ramesh", "login_id": "ramesh01", "password": "Staff1234"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn("password_hash", response.json())
        return response.json()["id"]

    def test_audit_actor_name_id_and_tenant_safe_fallbacks(self):
        self.db.get(User,1).full_name='Company Administrator'
        self.db.commit()
        staff_id=self.create()
        response=self.client.put(f'/company/users/{staff_id}',headers=self.admin_headers,
            json={'full_name':'Updated Staff','login_id':'ramesh01'})
        self.assertEqual(response.status_code,200,response.text)
        for actor, action in [(staff_id,'CREATE'),(staff_id,'UPDATE'),(None,'STATUS_CHANGE'),(2,'UPDATE')]:
            create_audit_log(self.db,company_id=12,user_id=actor,action=action,module='Customers',description='Test audit action')
        self.db.get(User,staff_id).status='deleted'
        self.db.commit()
        result=self.client.get('/admin/audit-history',headers=self.admin_headers)
        self.assertEqual(result.status_code,200,result.text)
        entries=result.json()['items']
        for entry in entries:
            if entry['user_id']==1:
                self.assertEqual(entry['user_name'],'Company Administrator')
                self.assertEqual(entry['user_login_id'],'adminabc')
            elif entry['user_id']==staff_id:
                self.assertEqual(entry['user_name'],'Updated Staff')
                self.assertEqual(entry['user_login_id'],'ramesh01')
            else:
                self.assertIsNone(entry['user_name'])
                self.assertIsNone(entry['user_login_id'])
            self.assertNotIn('password_hash',entry)
        self.db.get(User,1).full_name=None;self.db.commit()
        result=self.client.get('/admin/audit-history?user_id=1',headers=self.admin_headers)
        self.assertTrue(result.json()['items'])
        self.assertTrue(all(e['user_id']==1 and e['user_name']=='adminabc' for e in result.json()['items']))

    def test_lifecycle_and_operational_login(self):
        user_id = self.create()
        staff_headers = self.login("ramesh01", "Staff1234")
        claims = decode_access_token(staff_headers["Authorization"].split()[1])
        self.assertEqual((claims["user_id"], claims["company_id"], claims["role"]), (user_id, 12, "company_user"))
        for headers in (self.admin_headers, staff_headers):
            result = self.client.get("/chits", headers=headers)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual([chit["id"] for chit in result.json()], [1])
        result = self.client.put(f"/company/users/{user_id}", headers=self.admin_headers,
                                 json={"full_name": "Ramesh Kumar", "login_id": "ramesh02"})
        self.assertEqual(result.status_code, 200, result.text)
        result = self.client.patch(f"/company/users/{user_id}/password", headers=self.admin_headers, json={"password": "Newpass123"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.post("/auth/company/login", json={"login_id": "ramesh02", "password": "Staff1234"}).status_code, 401)
        self.login("ramesh02", "Newpass123")
        self.assertEqual(self.client.patch(f"/company/users/{user_id}/status", headers=self.admin_headers, json={"status": "inactive"}).status_code, 200)
        self.assertEqual(self.client.post("/auth/company/login", json={"login_id": "ramesh02", "password": "Newpass123"}).status_code, 403)
        self.assertEqual(self.client.get("/chits", headers=staff_headers).status_code, 403)
        self.assertEqual(self.client.patch(f"/company/users/{user_id}/status", headers=self.admin_headers, json={"status": "active"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/company/users/{user_id}", headers=self.admin_headers).status_code, 204)
        self.assertEqual(self.db.get(User, user_id).status, "deleted")
        self.assertEqual(self.client.get(f"/company/users/{user_id}", headers=self.admin_headers).status_code, 404)
        self.assertEqual(self.client.post("/auth/company/login", json={"login_id": "ramesh02", "password": "Newpass123"}).status_code, 403)
        self.assertEqual(self.db.query(AuditLog).count(), 6)
        self.assertNotIn("password_hash", json.dumps([audit.new_values for audit in self.db.query(AuditLog)]))

    def test_tenant_isolation_for_every_action(self):
        self.create()
        result = self.client.get("/company/users", headers=self.admin_headers)
        self.assertEqual({u["id"] for u in result.json()}, {1, 4})
        for method, suffix, body in [("get", "", None), ("put", "", {"full_name": "Hacked", "login_id": "hacked"}),
                                     ("patch", "/status", {"status": "inactive"}), ("patch", "/password", {"password": "Hacked123"}),
                                     ("delete", "", None)]:
            with self.subTest(method=method, suffix=suffix):
                args = {"headers": self.admin_headers}
                if body is not None: args["json"] = body
                self.assertEqual(self.client.request(method, f"/company/users/3{suffix}", **args).status_code, 404)
        self.assertEqual(self.db.get(User, 3).status, "active")

    def test_staff_denied_every_management_api(self):
        user_id = self.create()
        headers = self.login("ramesh01", "Staff1234")
        for method, suffix, body in [("get", "", None), ("post", "", {"full_name": "Bad", "login_id": "bad", "password": "Password1"}),
                                     ("get", f"/{user_id}", None), ("put", f"/{user_id}", {"full_name": "Bad", "login_id": "bad"}),
                                     ("patch", f"/{user_id}/status", {"status": "inactive"}),
                                     ("patch", f"/{user_id}/password", {"password": "Password1"}), ("delete", f"/{user_id}", None)]:
            args = {"headers": headers}
            if body is not None: args["json"] = body
            with self.subTest(method=method, suffix=suffix):
                self.assertEqual(self.client.request(method, "/company/users" + suffix, **args).status_code, 403)

    def test_validation_duplicate_and_protected_admin(self):
        user_id = self.create()
        data = {"full_name": "Ramesh", "login_id": "ramesh01", "password": "Staff1234"}
        self.assertEqual(self.client.post("/company/users", headers=self.admin_headers, json=data).status_code, 409)
        for override in [{"company_id": 13}, {"role": "company_admin"}, {"full_name": "  "}, {"login_id": " "},
                         {"password": "short"}, {"password": "a" * 73}, {"password": "\u00e9" * 37}]:
            self.assertEqual(self.client.post("/company/users", headers=self.admin_headers, json={**data, **override}).status_code, 422)
        self.assertEqual(self.client.put(f"/company/users/{user_id}", headers=self.admin_headers, json={"full_name": "Name", "login_id": "otherstaff"}).status_code, 409)
        for method, suffix, body in [("delete", "", None), ("patch", "/status", {"status": "inactive"}),
                                     ("patch", "/password", {"password": "Newpass123"}), ("put", "", {"full_name": "Bad", "login_id": "bad"})]:
            args = {"headers": self.admin_headers}
            if body is not None: args["json"] = body
            self.assertEqual(self.client.request(method, "/company/users/1" + suffix, **args).status_code, 403)
        self.login("adminabc", "Admin1234")

    def test_invalid_customer_and_missing_tokens(self):
        self.assertIn(self.client.get("/company/users").status_code, (401, 403))
        for claims in [{"sub": "bad"}, {"sub": "1", "token_type": "customer"}]:
            headers = {"Authorization": "Bearer " + create_access_token(claims)}
            self.assertEqual(self.client.get("/company/users", headers=headers).status_code, 401)


if __name__ == "__main__":
    unittest.main()
