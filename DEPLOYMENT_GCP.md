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

Company logos remain on the ephemeral, instance-local Cloud Run filesystem. Upload directories are created on startup; uploaded files can disappear on restart and are not shared across instances. Cloud Storage migration is required before final production launch.

The in-process scheduler is not started by main.py. Move production scheduling to Google Cloud Scheduler calling an authenticated Cloud Run endpoint/job in a later task.

Validation here does not replace an actual Linux container build and Cloud SQL connectivity check. No production database is accessed by local checks.

References: [Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/mysql/connect-run), [official Python image](https://hub.docker.com/_/python).
