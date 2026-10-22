# Membership welcome emails

Implementation and local verification: 21 October 2026. No production access, production migration, deployment, real mail or Git push was performed. During follow-up troubleshooting, the additive migration was applied to the verified localhost MySQL database from `c8e30f4a0103` to `e9a42b701105`; the new outbox was confirmed present and empty. Existing business records were not changed.

## Behavior and scope

The existing services enqueue a `membership_welcome` intent in the same transaction as membership creation, a membership status change, or a group transition to active. Only confirmed/active memberships in an active group qualify (case/whitespace normalized for comparisons; stored domain statuses unchanged). A pending membership or upcoming group waits for a later qualifying transition. There are no provider calls in API requests, SQLAlchemy global listeners, startup scans, or historical backfill jobs. Unrelated edits to historical memberships/groups do not enqueue email. A future explicit activation/status transition is a new qualifying event, including for an older membership.

Each distinct membership/slot can produce one welcome. The unique key is `(membership_id, notification_type)`. Multiple memberships belonging to the same customer intentionally produce separate emails. The existing create-membership API still creates a new slot on each valid create request; notification deduplication does not introduce API-level request idempotency or merge different slot IDs.

Content is loaded through the membership's exact chit group, company and company customer profile. Profile company ownership must match group company ownership, and the outbox company must match both. The registered address is `CustomerProfile.email`; greeting uses `CustomerProfile.display_name`, not an unrelated global account or slot alias. Delivery rechecks relationships and membership/group eligibility. Missing/deleted/invalid memberships are never sent. An inactive/cancelled membership's pending message is marked failed with `membership_ineligible`; a later qualifying transition can resume it. No financial records are changed.

## Login verification

`chits-public/src/app/components/public-header/public-header.ts` links “Login as Customer” to `https://customer.nexnidhi.in/login`. `customer-app/src/app/app.routes.ts` redirects both the root URL and unmatched paths (including `/login`) to `customer-login`, which loads the existing MSG91 page. The primary email CTA uses `https://customer.nexnidhi.in/`; the second link uses `https://nexnidhi.in/` and explains the existing “Login as Customer” action. This was verified in repository source, not against deployed hosting rules. Authentication, registration, OTP, JWT, guards and Angular files are unchanged.

## Configuration

The welcome adapter reuses the existing SMTP environment names and Python SMTP dependencies. Existing company-credential, password-reset and monthly email functions remain untouched. It adds multipart HTML/plaintext support in an isolated adapter.

| Variable | Required value |
| --- | --- |
| `SMTP_HOST` | Actual transactional SMTP hostname; no implicit provider fallback |
| `SMTP_PORT` | `587` by default, or provider's encrypted submission port |
| `SMTP_USERNAME` | Provider-issued username |
| `SMTP_PASSWORD` | Secret Manager reference in Cloud Run; password whitespace is preserved |
| `SMTP_FROM` | Authorized bare sender email address, e.g. `hello@nexnidhi.in` |
| `SMTP_USE_TLS` | `true` for STARTTLS (default) |
| `SMTP_USE_SSL` | `true` for implicit TLS, usually port 465 (default `false`) |
| `WELCOME_EMAIL_DELIVERY_ENABLED` | `false` by default; set `true` on the worker only after review |

Exactly one TLS mode must be enabled. TLS certificate verification is enabled. Authentication is required; no plaintext or anonymous fallback is used. Configure the sender/domain with the provider's SPF/DKIM/DMARC instructions and confirm its authorized From address. Do not put secrets in source, images, previews, command-line literals or committed environment files.

Missing/invalid configuration causes the worker to exit without claiming messages or spending retries. API requests continue to enqueue durable intents after the required migration. Delivery disabled means records accumulate; enabling later sends eligible queued events. Review queue volume before enabling.

## Migration and deployment checklist — manual approval required

1. Obtain approval for production changes; take the normal Cloud SQL backup. Use an authorized connection to inspect `SELECT version_num FROM alembic_version` and `python -m alembic current`. These read-only production checks have **not** been run here.
2. Compare with `python -m alembic heads` and `python -m alembic history --verbose`. The inspected repository head before this change was `c8e30f4a0103`; the new head is `e9a42b701105`. If production differs, review the entire pending chain and stop until reconciled. Never stamp to skip migrations.
3. Inspect the new migration SQL without a DB connection:
   ```sh
   python -m alembic upgrade c8e30f4a0103:e9a42b701105 --sql
   ```
   It creates only `membership_welcome_outbox` and its index/unique constraint, then advances Alembic metadata. It inserts no notifications and touches no customer/financial rows. No foreign keys are added, so existing membership/group deletes remain unblocked; IDs retained in the outbox preserve deduplication history. Downgrade intentionally refuses to delete this history.
4. In an isolated MySQL staging database at the verified base revision, apply `python -m alembic upgrade e9a42b701105`, run a two-worker race and failure/retry smoke test, and check query plans. Local validation used SQLite plus offline MySQL SQL generation; live MySQL concurrency and Linux image execution still require staging validation.
5. After production approval and revision verification, apply the reviewed migration **before releasing the API code**. New hooks require the outbox table. If production is exactly `c8e30f4a0103`, the reviewed command is `python -m alembic upgrade e9a42b701105`. Do not run this blindly against any other revision.
6. Build/review the image and deploy the API with existing settings preserved. Configure a separate Cloud Run Job from that same image with command `python` and arguments `-m,app.welcome_worker,--limit,100`. Attach the existing Cloud SQL instance, required DB/JWT environment as applicable, and the job's runtime service account with Cloud SQL Client and access only to its selected Secret Manager secrets. Map `SMTP_USERNAME`, `SMTP_PASSWORD`, and other sensitive values to Secret Manager using reviewed Cloud Run secret references. Never replace unrelated service environment variables.
7. Keep delivery disabled initially. Review the fictional HTML/text previews and confirm both login links using deployed hosting. Use only explicitly approved test recipients for a staging provider test. Gmail/Outlook/mobile inbox rendering has not been live-tested locally.
8. Enable `WELCOME_EMAIL_DELIVERY_ENABLED=true` on the worker and schedule its execution, e.g. every minute, using Cloud Scheduler's authenticated Cloud Run Jobs execution API and a dedicated Scheduler service account authorized to execute that job. Do not expose a public send endpoint. Start with one task and appropriate task timeout (a full batch can take many minutes during SMTP failures); overlapping executions are supported by DB claims. Match worker parallelism to the DB connection budget.
9. Monitor executions and the queue. Confirm creation in an active group, pending confirmation, group activation, absence of duplicates, and existing company/customer login. No production deployment or real-recipient test is authorized by this document itself.

Local worker invocation after configuring a **non-production** DB/provider:

```sh
python -m app.welcome_worker --limit 100
```

The API does not start an in-process delivery scheduler. On Cloud Run request-based CPU allocation, scheduling this independent job is required for automatic delivery.

### Repeatable Cloud Shell setup

`deploy/welcome-worker.sh` creates/updates only the dedicated delivery job and its authenticated one-minute Cloud Scheduler trigger. It does not depend on a local computer or terminal. Deploy the API containing the welcome hooks through the existing release workflow after the reviewed production migration; use the same immutable image for the job.

Before running the script, verify the actual production `alembic_version` and that `membership_welcome_outbox` exists using an authorized production connection. The script refuses to run unless you explicitly record that verification as `PRODUCTION_SCHEMA_VERIFIED=e9a42b701105`; it never runs a migration or stamps a database. Do not set this variable based on the local database revision.

In Google Cloud Shell, set `PROJECT_ID`, `REGION`, `IMAGE`, `CLOUD_SQL_INSTANCE`, `WORKER_SERVICE_ACCOUNT`, `SCHEDULER_SERVICE_ACCOUNT`, `ENV_VARS_FILE`, `SECRET_MAPPINGS`, and `PRODUCTION_SCHEMA_VERIFIED` to the reviewed actual deployment values. `SECRET_MAPPINGS` contains secret names/versions only, for example `DB_PASSWORD=existing-db-secret:1,SMTP_USERNAME=smtp-user-secret:1,SMTP_PASSWORD=smtp-password-secret:1`; these are placeholders, not existing project resources. Create the worker-only YAML from `deploy/welcome-worker.env.example.yaml` outside the source tree. Never upload/copy the local `.env` to production. Keep the worker and API database identity/socket consistent.

The worker runtime service account needs `roles/cloudsql.client` and Secret Manager access to the mapped secrets. The Scheduler service account must exist; the script grants it `roles/run.invoker` on this job only. The executing deployer needs permission to deploy jobs, configure Scheduler, manage the relevant job IAM policy, enable the listed services if necessary and act as both service accounts. If production requires a Serverless VPC connector, also supply `VPC_CONNECTOR` and the existing `VPC_EGRESS` configuration; review SMTP outbound connectivity for that network.

Run `bash deploy/welcome-worker.sh` only after reviewing the real values. It deploys a single-task job processing up to 20 due records per execution, with application retries retained in the outbox and no additional task-level retry loop. The one-minute schedule calls the authenticated Jobs API; overlapping executions are safe through database claims. Queue volume/oldest age should be monitored and the batch size/connection budget tuned for actual traffic. Existing schedule targets are checked before updates; unrelated backend environment variables are untouched.

Google's command references: [Cloud Run Jobs deployment](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/deploy), [scheduled job execution](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule).

For local development, enable `WELCOME_EMAIL_DELIVERY_ENABLED=true` in the local `.env` and keep a second terminal running alongside Uvicorn:

```powershell
.\venv\Scripts\python.exe -m app.welcome_worker --watch --interval 15
```

The watcher checks for committed notifications every 15 seconds, including due retries, and recovers from temporary database errors. It must be restarted if its process or the computer is stopped. Production continues to use scheduled batch jobs; no in-process scheduler or frontend changes are required.

## Delivery guarantees and operations

States are `pending`, `processing`, `sent`, `failed`. A unique database key prevents repeated intents; atomic conditional updates claim a row using a random ownership token. Concurrent claimers cannot claim a live lease twice. Claims expire after ten minutes so process crashes can recover. Attempts/timestamps and sanitized reason codes are retained; SMTP exceptions, addresses and credentials are not logged. Payload loading transactions close before network I/O; SMTP socket operations have a 30-second timeout. Success/failure updates require the current claim token, preventing stale workers from overwriting newer outcomes.

`sent` / `sent_at` mean SMTP server acceptance after `send_message` succeeds, **not confirmed inbox delivery**. Bounces, spam placement and inbox delivery require provider-side monitoring. SMTP does not support a durable idempotency key. A crash after SMTP acceptance but before the database update, an ambiguous network error after acceptance, or a process pause beyond the lease can cause a duplicate. Stable Message-ID helps correlation but does not guarantee recipient-side deduplication. Do not promise exactly-once delivery.

Failures retry after 60, 120, 240, 480, 960, 1920 and 3600 seconds, up to eight attempts. Failed rows with `available_at IS NULL` need operator review; `last_error` explains missing/invalid email, changed eligibility, provider/config errors, or attempt limit. Correcting an email permits subsequent scheduled retries using current customer data. After exhaustion, an authorized operator may requeue a **specific reviewed failed outbox ID** by setting status to pending, attempts to zero, available_at to current UTC and clearing claim_token/claimed_at/last_error. Do not reset sent rows, delete history or bulk-requeue historical memberships. Assess ambiguous acceptance before manually retrying provider errors.

Read-only queue health query:

```sql
SELECT status, last_error, COUNT(*) AS total, MIN(created_at) AS oldest
FROM membership_welcome_outbox
GROUP BY status, last_error;
```

Alert on oldest due records, terminal failures and failed job executions. Pause sending by disabling the worker flag or schedule; API event capture can continue. To roll back code, stop the job and restore the prior API image while retaining the additive table. No destructive downgrade is necessary.

## Local verification and artifacts

```sh
python -m unittest discover -s tests -v
python -m compileall -q app tests alembic/versions/e9a42b701105_membership_welcome_outbox.py
python -m app.welcome_preview
```

Use the repository's `venv/Scripts/python.exe` on this Windows workspace (`.venv` lacks dependencies). Tests use isolated SQLite databases and mocked SMTP; the configured MySQL database is not contacted. Focused tests cover eligibility, actual service hooks, duplicates, multiple memberships/tenants, missing email, provider failure/retry, limits, leases/fencing, eight competing workers, no open transaction during SMTP, rollback, deletion/cancellation, escaping, MIME/TLS configuration and additive migration preservation. Existing auth, permissions, MSG91, recovery, company, dashboard and entitlement tests are also run.

`previews/membership-welcome.html` and `.txt` contain fictional sample data only. Regenerate with `python -m app.welcome_preview`. HTML uses table layout, inline colors, email-safe fonts, Outlook width fallback, optional-free text branding, and visible alternatives to the CTA. No network assets or embedded secrets are needed.

Verification results: 25 focused tests and all 33 pre-existing backend tests pass (58 total), including local watcher recovery after a database failure; Python compilation, whitespace checks and offline MySQL migration SQL generation pass. Existing FastAPI/httpx and UTC timestamp deprecation warnings remain. Headless Chrome and Edge exited unsuccessfully in this workspace, so no screenshot or visual email-client certification is claimed. Inspect the supplied HTML in a browser and test Gmail/Outlook/mobile inbox rendering in staging before release.

Changed files:

| Files | Purpose |
| --- | --- |
| `app/models/admin/welcome_outbox.py`, `app/models/__init__.py` | Persistent intent/deduplication model and registration |
| `alembic/versions/e9a42b701105_membership_welcome_outbox.py` | Safe additive migration |
| `app/services/chit_member_service.py`, `app/services/chit_group_service.py` | Three transaction-local event hooks |
| `app/services/welcome_notifications.py` | Eligibility, tenant validation, claims and retries |
| `app/services/welcome_email.py`, `app/services/welcome_template.py` | Configured encrypted SMTP and premium multipart template |
| `app/welcome_worker.py`, `app/welcome_preview.py` | Scheduled batch entrypoint and offline preview generator |
| `tests/test_welcome_notifications.py` | Focused mocked/isolation tests |
| `.env.example`, `WELCOME_EMAILS.md`, `previews/` | Configuration, operations and fictional sample artifacts |
