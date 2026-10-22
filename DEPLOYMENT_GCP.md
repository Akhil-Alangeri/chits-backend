# Cloud Run deployment

Build from this backend directory using Dockerfile (Python 3.14). First run:

```sh
docker build -t nexnidhi-backend .
```

Deploy the image to Cloud Run in `asia-south1`. Attach the existing Cloud SQL MySQL 8.0 instance and give the runtime service account `roles/cloudsql.client` (Cloud SQL Client). Enable the Cloud SQL Admin API. Supply the actual project and instance identifiers through deployment configuration, never source code.

Required Cloud Run environment configuration:

```dotenv
DB_USER=nexnidhi_app
DB_PASSWORD=<secret>
DB_NAME=chits
INSTANCE_UNIX_SOCKET=/cloudsql/<INSTANCE_CONNECTION_NAME>
SECRET_KEY=<secret>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=300
CORS_ORIGINS=https://nexnidhi.in,https://www.nexnidhi.in
```

Store DB_PASSWORD and SECRET_KEY securely using Cloud Run Secret Manager references; grant the runtime service account access to the selected secrets. Never commit their values. DB_HOST/DB_PORT are only needed for local TCP connections. Cloud Run supplies PORT, defaulting locally to 8080. Use SMTP settings from .env.example for email features; OTP provider configuration is deferred.

The engine allows at most 10 connections per process (pool_size=5, max_overflow=5). Set Cloud Run maximum instances within the database connection budget, reserving capacity for migrations and other clients.

Use `/` for a database-independent startup probe. After deployment, manually check `/health`, which executes SELECT 1 against the configured database. No schema creation or migrations run during startup.

Before any manual migration, compare the imported database's alembic_version with `python -m alembic heads` and review pending revisions. Do not stamp, upgrade, or downgrade automatically. The existing bootstrap migration now requires BOOTSTRAP_ADMIN_PASSWORD (8?72 UTF-8 bytes) only when creating the initial admin. Supply it securely for that manual migration if needed. Existing accounts are untouched; if the old fixed bootstrap credential was ever used, change that account password before production launch.

Company logos use a private Cloud Storage bucket in production. Set `COMPANY_LOGO_BUCKET` to its name and grant the runtime service account `roles/storage.objectUser` on that bucket. The API serves the existing `/uploads/company-logos/{filename}` URLs, so no public bucket access or expiring signed URLs are needed. Cloud Run rejects logo uploads if the bucket is not configured; it never silently saves new logos to ephemeral storage. Local development without the setting uses the backend uploads directory.

Before switching production, copy surviving files from `uploads/company-logos/` into the bucket under `company-logos/`, preserving filenames. Existing database URLs continue to work. Files already lost from old instances must be uploaded again. Deploy with the updated requirements and bucket setting together. Verify by uploading a logo, logging out/in, and loading its URL after a revision restart or from another instance.

The in-process scheduler is not started by main.py. Membership welcome emails require the separate Cloud Run Job and Cloud Scheduler setup in [WELCOME_EMAILS.md](WELCOME_EMAILS.md). Deploying the API alone does not start email delivery. The production job uses batch mode, not the local `--watch` process. `deploy/welcome-worker.sh` configures the job and a one-minute authenticated schedule from Google Cloud Shell after the actual production migration has been verified.

Validation here does not replace an actual Linux container build and Cloud SQL connectivity check. No production database is accessed by local checks.

References: [Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/mysql/connect-run), [official Python image](https://hub.docker.com/_/python).
