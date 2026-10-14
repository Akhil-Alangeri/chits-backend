"""Exercise actual routers against SQLite, without touching configured MySQL."""
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
from app.core.security import hash_password, create_access_token
from app.models import Company, User, Feature, Loan, Expense
from app.routes.subscription import router, company_router
from app.routes.auth import router as auth_router
from app.routes.company import router as companies_router
from app.routes.loan import router as loan_router
from app.routes.expenses import router as expenses_router
from app.routes.loan_reports import router as loan_reports_router
from app.routes.expenses_reports_router import router as expense_reports_router
from app.services.entitlement_service import get_company_effective_features
from app.services.ledger_report_service import _build_ledger_rows
from app.services.dashboard_service import get_loan_summary, get_expense_summary
from app.services.audit_log_service import get_audit_history

@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kw):
    return "INTEGER"

class EntitlementTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(conn, _): conn.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine,autoflush=False)()
        self.db.add_all([Company(id=12,company_name='A',email='a@example.com',status='active'),Company(id=13,company_name='B',email='b@example.com',status='active'),Feature(key='loans',name='Loans'),Feature(key='expenses',name='Expenses')])
        self.db.flush()
        password=hash_password('Password1234')
        self.db.add_all([User(id=2,company_id=12,login_id='admin',password_hash=password,role='company_admin',status='active'),
            User(id=3,company_id=12,login_id='staff',password_hash=password,role='company_user',status='active'),
            User(id=4,company_id=13,login_id='other',password_hash=password,role='company_user',status='active')])
        self.db.commit()
        self.app=FastAPI()
        self.module_routers=[loan_router,expenses_router,loan_reports_router,expense_reports_router]
        for r in [router,company_router,auth_router,companies_router,*self.module_routers]: self.app.include_router(r)
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(self.app)
        self.headers={i:{'Authorization':'Bearer '+create_access_token({'sub':str(i)})} for i in range(2,5)}
        self.headers[1]={}  # Platform management is intentionally login-free.
        self.normal=self.plan('normal',False,False)
        self.pro=self.plan('pro',True,True)
        self.assign(12,self.normal['id']);self.assign(13,self.pro['id'])

    def tearDown(self):
        self.client.close();self.db.close();self.engine.dispose()

    def plan(self,code,loans,expenses):
        data={'name':code.title(),'code':code,'price':'15000.00','billing_cycle':'yearly','features':{'loans':loans,'expenses':expenses}}
        r=self.client.post('/super-admin/plans',headers=self.headers[1],json=data)
        self.assertEqual(r.status_code,201,r.text);return r.json()

    def assign(self,company,plan,overrides=None):
        r=self.client.put(f'/super-admin/companies/{company}/subscription',headers=self.headers[1],json={'plan_id':plan,'overrides':overrides or {}})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def test_plan_edit_overrides_and_live_sessions(self):
        body={k:v for k,v in self.normal.items() if k not in ('id','created_at','updated_at')}
        body.update(price='25000.00',features={'loans':True,'expenses':False})
        r=self.client.put(f"/super-admin/plans/{self.normal['id']}",headers=self.headers[1],json=body)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(float(r.json()['price']),25000)
        for user in (2,3):
            self.assertEqual(self.client.get('/company/entitlements',headers=self.headers[user]).json()['features'],{'loans':True,'expenses':False})
        state=self.assign(12,self.normal['id'],{'loans':False,'expenses':True})
        self.assertEqual(state['features'],{'loans':False,'expenses':True})
        state=self.assign(12,self.normal['id'],{'loans':None,'expenses':None})
        self.assertEqual(state['overrides'],{});self.assertEqual(state['features'],{'loans':True,'expenses':False})
        self.assign(12,self.pro['id'],{'loans':False})
        self.assertEqual(self.client.get('/loans',headers=self.headers[3]).status_code,403)
        body['is_active']=False
        self.assertEqual(self.client.put(f"/super-admin/plans/{self.normal['id']}",headers=self.headers[1],json=body).status_code,200)
        self.assertEqual(self.client.put('/super-admin/companies/13/subscription',headers=self.headers[1],json={'plan_id':self.normal['id']}).status_code,422)

    def test_every_module_endpoint_denied(self):
        for r in self.module_routers:
            for route in r.routes:
                path=route.path.replace('{loan_id}','1').replace('{expense_id}','1')
                for method in route.methods:
                    for user in (2,3):
                        with self.subTest(path=path,method=method,user=user):
                            result=self.client.request(method,path,headers=self.headers[user],json={})
                            self.assertEqual(result.status_code,403,result.text)
        self.assertIn(self.client.get('/loans').status_code,(401,403))

    def test_login_free_platform_and_company_authentication(self):
        for path in ('/super-admin/features', '/super-admin/plans', '/super-admin/companies/12/subscription', '/companies', '/companies/requests', '/companies/12'):
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.assertEqual(self.client.post('/auth/super-admin/login',json={'login_id':'platform','password':'Password1234'}).status_code,404)
        self.assertEqual(self.client.post('/auth/company/login',json={'login_id':'admin','password':'Password1234'}).status_code,200)
        self.assertEqual(self.client.post('/auth/company/login',json={'login_id':'admin','password':'wrong'}).status_code,401)
        self.assertIn(self.client.get('/company/entitlements').status_code,(401,403))
        for extra in [{'company_id':13},{'role':'super_admin'},{'overrides':{'unknown':True}}]:
            r=self.client.put('/super-admin/companies/12/subscription',json={'plan_id':self.pro['id'],**extra})
            self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(self.client.get('/company/entitlements?company_id=13',headers=self.headers[2]).json()['features'],{'loans':False,'expenses':False})

    def test_operational_access_isolation_and_data_retention(self):
        loan=self.client.post('/loans',headers=self.headers[4],json={'person_name':'Borrower','direction':'given','principal_amount':1000,'start_date':'2026-10-06'})
        self.assertEqual(loan.status_code,201,loan.text)
        expense=self.client.post('/expenses',headers=self.headers[4],json={'category':'office','amount':500,'expense_date':'2026-10-06','payment_method':'cash'})
        self.assertEqual(expense.status_code,201,expense.text)
        for path in ('/loans','/expenses','/reports/loans','/reports/expenses'):
            self.assertEqual(self.client.get(path,headers=self.headers[4]).status_code,200,path)
        self.assign(12,self.pro['id'])
        self.assertEqual(self.client.get(f"/loans/{loan.json()['id']}",headers=self.headers[2]).status_code,404)
        self.assertEqual(self.client.get(f"/expenses/{expense.json()['id']}",headers=self.headers[3]).status_code,404)
        self.assign(13,self.normal['id'])
        self.assertEqual(self.db.query(Loan).count(),1);self.assertEqual(self.db.query(Expense).count(),1)
        self.assertEqual(_build_ledger_rows(self.db,13),[])
        self.assertEqual(get_loan_summary(self.db,13)['given_amount'],0)
        self.assertEqual(get_expense_summary(self.db,13)['total'],0)
        audits, count = get_audit_history(self.db, company_id=13)
        self.assertFalse(any(a.module in ('Loans', 'Loan Transactions', 'Expenses') for a in audits))
        self.assign(13,self.pro['id'])
        self.assertEqual(self.client.get(f"/loans/{loan.json()['id']}",headers=self.headers[4]).status_code,200)
        self.assertEqual(self.client.get(f"/expenses/{expense.json()['id']}",headers=self.headers[4]).status_code,200)
        state=self.assign(12,self.normal['id'],{'loans':True})
        self.assertTrue(state['features']['loans']);self.assertFalse(state['features']['expenses'])
        self.assertEqual(self.client.get('/loans',headers=self.headers[3]).status_code,200)
        self.assign(12,self.normal['id'],{'loans':None})
        self.assertEqual(self.client.get('/loans',headers=self.headers[3]).status_code,403)

    def test_plan_validation_and_unassigned_default(self):
        body={k:v for k,v in self.pro.items() if k not in ('id','created_at','updated_at')}
        self.assertEqual(self.client.post('/super-admin/plans',headers=self.headers[1],json=body).status_code,409)
        for change in ({'price':-1},{'features':{'unknown':True}},{'features':{'loans':'true'}},{'company_id':12},{'name':' '},{'billing_cycle':'invalid'}):
            r=self.client.put(f"/super-admin/plans/{self.pro['id']}",headers=self.headers[1],json={**body,**change})
            self.assertEqual(r.status_code,422,r.text)
        body['is_active']=False
        self.assertEqual(self.client.put(f"/super-admin/plans/{self.pro['id']}",headers=self.headers[1],json=body).status_code,200)
        self.assertEqual(self.client.get('/loans',headers=self.headers[4]).status_code,200)
        self.db.get(Company,12).subscription_plan_id=None;self.db.commit()
        self.assertEqual(get_company_effective_features(self.db,12),{'loans':False,'expenses':False})
        self.assertEqual(self.client.get('/loans',headers=self.headers[2]).status_code,403)

    def test_company_status_controls_login_and_existing_sessions(self):
        before_users = [(u.id, u.status, u.password_hash) for u in self.db.query(User).order_by(User.id)]
        before_plan = self.db.get(Company, 12).subscription_plan_id
        response = self.client.patch('/companies/12/status', json={'status':'inactive'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'inactive')
        for user, login in [(2, 'admin'), (3, 'staff')]:
            self.assertEqual(self.client.get('/company/entitlements', headers=self.headers[user]).status_code, 403)
            self.assertEqual(self.client.post('/auth/company/login', json={'login_id':login,'password':'Password1234'}).status_code, 403)
        self.assertEqual(self.client.get('/company/entitlements', headers=self.headers[4]).status_code, 200)
        response = self.client.patch('/companies/12/status', json={'status':'active'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/company/entitlements', headers=self.headers[3]).status_code, 200)
        self.assertEqual(self.client.post('/auth/company/login', json={'login_id':'admin','password':'Password1234'}).status_code, 200)
        self.assertEqual(self.db.get(Company,12).subscription_plan_id, before_plan)
        self.assertEqual([(u.id,u.status,u.password_hash) for u in self.db.query(User).order_by(User.id)], before_users)
        for body in [{'status':'pending'}, {'status':'active','company_id':13}]:
            self.assertEqual(self.client.patch('/companies/12/status',json=body).status_code,422)
        self.assertEqual(self.client.patch('/companies/999/status',json={'status':'active'}).status_code,404)
        self.db.get(Company,12).status='pending';self.db.commit()
        self.assertEqual(self.client.patch('/companies/12/status',json={'status':'active'}).status_code,409)
