# Backend subscription foundation — Phase B

This phase changes the backend only. No production database migration, billing,
cloud configuration, frontend change, commit, push or deployment was performed.

## Commercial catalog

| Plan | Annual INR | Active/upcoming/paused groups | Admin | Active staff | Months |
|---|---:|---:|---:|---:|---:|
| Starter | 9,999 | 3 | 1 | 0 | 12 |
| Growth | 14,999 | 7 | 1 | 3 | 12 |
| Business | 19,999 | 12 | 1 | 5 | 12 |

Core customer/chit/payment/collection/auction/customer-portal access and audit
history remain enabled. Starter excludes loans, expenses, reports, staff
management and support writes. Growth enables those modules. Audit export is a
Business entitlement; an export implementation/UI is a later phase. WhatsApp
requires a separate active, dated add-on with an approval actor and nonblank paid
reference, regardless of plan/enable override. An explicit false override can
disable the add-on. No WhatsApp purchase/provisioning API was introduced. MSG91
OTP, email reminders and welcome emails are unchanged.

## Schema and migration

New revision `g1d52b701107`, parent `f0c42b701106`:

- Nullable plan fields: `active_group_limit`, `admin_account_limit`,
  `staff_account_limit`, `duration_months`.
- Nullable company fields: `subscription_started_at`, `subscription_ends_at`,
  `subscription_status`, `pending_subscription_plan_id`,
  `pending_subscription_effective_at`.
- `company_subscription_events`: append-only through the application API;
  company transitions have a company ID, and platform catalog events have NULL.
  Stores actor, reason/reference and before/after snapshots. No edit/delete API.
- `company_addons`: separate paid approvals, validity and status. It does not
  replace the existing plan/feature/override system.

The migration inserts missing catalog rows only. It does not assign companies,
invent dates or overwrite existing plans, mappings or overrides. Conflicting
reserved commercial codes fail preflight before DDL. Existing feature labels are
preserved. The new migration can resume/repeat compatible additions; older
migrations were not changed or rerun.

Offline SQL is deliberately unsupported because insert-only conflict detection
requires inspecting actual catalog rows. Downgrade refuses to remove event or
add-on history and retains seeded catalog rows. MySQL DDL implicitly commits;
backup and staging verification remain necessary before an authorized rollout.

## Capacity and locking

Verified routes: POST `/chits` creates drafts; PUT `/chits/{id}` is the existing
status-change/activation/reopening entry point. No separate duplication, import,
invitation or staff-role-change endpoint was found.

- Count `active`, `upcoming`, `paused`, scoped to company. Draft/completed/cancelled
  do not consume capacity. Update input accepts only the six existing statuses.
- Drafts remain creatable at capacity and after expiry.
- Enforce when moving from a non-consuming status into a consuming status.
  Moving within consuming statuses, existing edits and capacity reductions remain
  available, including for companies already above their limit.
- Staff seats count active `company_user` rows. Creation and reactivation check
  seats. Staff management retains the company-admin role requirement as a
  separate authorization layer. Admin-readable lists/details and staff
  deactivation/deletion remain available for remediation. No existing user is
  automatically deactivated; company admins remain protected.
- Approval locks the company and checks admin capacity. Initial legitimate admin
  creation can proceed without a commercial term; it never assigns a paid plan.

Capacity changes and subscription assignment lock the company row first. Mutable
target rows and capacity usage use locking current reads, with refreshed ORM
state, so prior MySQL REPEATABLE READ snapshots cannot hide a predecessor's
committed increase. Locks remain through the business/audit commit. Existing
capacity writers retry an entire rolled-back transaction up to three attempts
for MySQL deadlocks/lock timeouts. Exhaustion returns structured
`SUBSCRIPTION_BUSY` (503); unrelated database errors are not retried. A real
cross-company first-override race verifies recovery without duplicate events.
Existing
automatic completion only releases capacity and is not called inside the locked
capacity-increase transaction. Any future import/invitation/role-change writer
must reuse these helpers and lock order.

See MySQL's [consistent-read documentation](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)
for the distinction between snapshot reads and locking current reads.

## Lifecycle and administrative API

Dates are UTC. Capacity increases are allowed during the term and the 15 days
immediately following expiry; at exactly `ends_at + 15 days` they are blocked.
Feature access is not removed merely because a term expires, preserving existing
collections, auctions, repayments and historical access. A bounded plan without
a reviewed valid term blocks increases. Existing unbounded/custom/unassigned
accounts retain legacy capacity and existing module access until explicit review.
No legacy company is automatically moved to Starter.

The existing `/company/entitlements` response retains `plan`, `plan_features`,
`overrides`, `features`, and adds `limits`, `usage`, `subscription`. Usage key
`active_groups` includes upcoming and paused groups. Ordinary optional feature
overrides retain explicit override → plan → false precedence. Legacy reports,
staff management and support access are preserved. Core access/audit history and
the paid WhatsApp requirement cannot be bypassed by an ordinary feature override.

Existing Super Admin subscription PUT accepts optional actions:
`assign`, `upgrade`, `renew`, `schedule_downgrade`, `apply_downgrade`,
`cancel_downgrade`. Commercial transitions require authenticated Super Admin,
`workflow: "administrative"` and a reason. `approved_reference` is an informational
administrative reference; this API does not verify payments, charge, refund or
activate from a claimed payment reference alone. Old custom unbounded plan
assignments and override-only edits keep their existing request shape.

- Initial reviewed assignment establishes a 12-calendar-month term. `starts_at`
  is optional and accepted only for initial assignment. Explicit assignment can
  repair a termless bounded assignment, but cannot reset a valid/partial term.
- Upgrades preserve original term start and renewal date. GET
  `/super-admin/companies/{id}/subscription/upgrade-quote?plan_id=...` is read-only:
  annual price difference × remaining fraction of the annual term, rounded to
  INR paise. It is an administrative estimate, not a tax invoice/payment request.
- Downgrades schedule for renewal, checking capacity then and again on explicit
  application. No automatic downgrade worker applies them. If capacity is too
  high at renewal, retain current servicing/access until review.
- Renewal cannot bypass a pending downgrade. Renewal during grace retains the
  anniversary; after grace it starts at the authorized renewal time. Early paid
  renewal scheduling is deferred.
- GET `/super-admin/companies/{id}/subscription/events` returns up to 100 recent
  company events. Company tokens cannot access platform history.
- Commercial price, capacity, duration and feature matrix cannot be edited via
  the generic plan editor. Plan status/description remain manageable. Omitted
  new capacity fields in old PUT bodies preserve stored values.

Changes, company audit logging and subscription events commit together. Backend
financial audit logging remains unconditional. Audit history no longer hides
past loan/expense events after a plan change. Starter support GETs remain
available while create/reply/update/delete operations are restricted after
existing tenant/ownership checks. Report routes/exports require `reports` and,
where applicable, their loan/expense entitlement.

Errors remain FastAPI responses with a structured `detail` object containing
`code` and `message`. Codes include `PLAN_LIMIT_REACHED` (resource, used, limit,
plan_code), `SUBSCRIPTION_EXPIRED`, `SUBSCRIPTION_REVIEW_REQUIRED`,
`FEATURE_NOT_AVAILABLE`, and `SUBSCRIPTION_APPROVAL_REQUIRED`.

## Validation and rollout checks

Actual results on 25 October 2026:

- Full backend discovery: **142 passed, 0 failed, 0 skipped** (69.939 seconds).
- After the final resolver/catalog refinements: **71 focused tests passed**
  (27.418 seconds), including entitlement/dashboard regressions.
- Real MySQL 8.0.46: **8 migration tests + 4 concurrency tests passed** inside
  those runs. Used a separate temporary server on localhost port 13317, never the
  existing MySQL service or configured application database. Disposable schemas
  were cleaned after tests.
- `alembic heads`: one head, `g1d52b701107`; `git diff --check` passed.
- Angular builds, production migrations, cloud changes and real billing/provider
  integration were not run in this phase. Existing TestClient deprecation
  warnings remain; no dependency upgrades were made.

Local logs: `tmp/phase_b_backend_final_tests.log` and
`tmp/phase_b_backend_focused_tests.log` (ignored by Git).

Files changed (relative to `chits-backend/`):

- `app/models/__init__.py`, `app/models/admin/company.py`,
  `app/models/admin/subscription.py`.
- `app/schemas/chit_group.py`, `app/schemas/subscription.py`.
- `app/routes/subscription.py`, `app/routes/company_users.py`.
- `app/routes/collection_report.py`, `app/routes/due_reports.py`,
  `app/routes/chit_reports.py`, `app/routes/ledger_reports.py`,
  `app/routes/loan_reports.py`, `app/routes/expenses_reports_router.py`.
- `app/services/entitlement_service.py`, `app/services/chit_group_service.py`,
  `app/services/company_user_service.py`, `app/services/company_service.py`,
  `app/services/audit_log_service.py`, `app/services/support/ticket_service.py`.
- `tests/test_entitlements.py` (additive response and retained audit-history
  expectations; existing authorization assertions retained).

New files:

- `alembic/versions/g1d52b701107_subscription_foundation.py`.
- `app/services/subscription_lifecycle.py`,
  `app/services/subscription_transactions.py`.
- `tests/test_subscription_foundation.py`, `tests/test_subscription_features.py`,
  `tests/test_subscription_lifecycle.py`, `tests/test_subscription_migration.py`,
  `tests/test_subscription_mysql.py`.
- `SUBSCRIPTION_FOUNDATION.md`.

Pre-existing support pagination edits were preserved. This phase did not edit
`app/routes/admin_ticket_router.py`; its existing working-tree diff predates this
work. Existing `previews/` and uploaded-logo artifacts were also preserved.

Use the populated `venv`, not the incomplete `.venv`:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m alembic heads
```

Real MySQL tests require explicit `NEXNIDHI_TEST_MYSQL_URL` pointing to localhost
and a `nexnidhi_test_*` database placeholder, plus
`NEXNIDHI_TEST_MYSQL_ALLOW_CREATE=1`. They create unique disposable schemas and
remove only schemas they created; they never use the configured application DB.
Tests exercise the actual new migration against a prior-schema fixture and
actual concurrent API requests using distinct connections and warmed snapshots.

Before a separately approved staging/production migration:

1. Verify current Alembic revision and actual schema; take a backup.
2. Review conflicts for reserved starter/growth/business codes and nonstandard
   status values. Resolve conflicting commercial catalog rows explicitly.
3. Verify nullable limits/dates on legacy rows remain unchanged and existing
   company assignments/overrides and financial row counts are preserved.
4. Verify InnoDB tables and transactional locking on the deployment database.
5. Review staging upgrade/retry and event-history rollback safeguards.
6. Arrange deliberate company assignments; seeding does not activate customers.

Next phase: connect Super Admin lifecycle/history and reviewed add-on provisioning,
then Company Admin usage/locked states/error messages. Audit export implementation
and any billing integration need separately approved work. Existing Angular code
was not edited or built in this backend-only phase.
