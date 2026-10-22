#!/usr/bin/env bash
# Run from Google Cloud Shell after reviewing WELCOME_EMAILS.md and migrating
# the actual production database. Does not deploy/change the API service.
set -euo pipefail

: "${PROJECT_ID:?Set the actual Google Cloud project ID}"
: "${REGION:?Set the actual Cloud Run region}"
: "${IMAGE:?Set the reviewed backend image containing app.welcome_worker}"
: "${CLOUD_SQL_INSTANCE:?Set project:region:instance for the existing database}"
: "${WORKER_SERVICE_ACCOUNT:?Set the worker runtime service account email}"
: "${SCHEDULER_SERVICE_ACCOUNT:?Set the Scheduler invoker service account email}"
: "${ENV_VARS_FILE:?Set the path to the reviewed worker-only environment YAML}"
: "${SECRET_MAPPINGS:?Set DB_PASSWORD=secret:version,SMTP_USERNAME=secret:version,SMTP_PASSWORD=secret:version}"
: "${PRODUCTION_SCHEMA_VERIFIED:?Verify actual production revision and outbox table first, then set to e9a42b701105}"

if [[ "$PRODUCTION_SCHEMA_VERIFIED" != "e9a42b701105" ]]; then
  echo 'Stop: actual production migration/outbox verification is required.' >&2
  exit 1
fi
if [[ ! -f "$ENV_VARS_FILE" ]]; then
  echo 'Worker environment YAML file does not exist.' >&2
  exit 1
fi
command -v gcloud >/dev/null || { echo 'Run this in Google Cloud Shell with gcloud installed.' >&2; exit 1; }

JOB_NAME="${JOB_NAME:-nexnidhi-membership-welcomes}"
SCHEDULE_NAME="${SCHEDULE_NAME:-nexnidhi-membership-welcomes-minute}"

# Enable the required APIs, preserving other project services.
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  secretmanager.googleapis.com sqladmin.googleapis.com --project="$PROJECT_ID"

# Worker account must already have Cloud SQL Client and access to these secrets.
# Dedicated job settings do not overwrite the existing backend service's settings.
network_args=()
if [[ -n "${VPC_CONNECTOR:-}" ]]; then
  network_args+=("--vpc-connector=$VPC_CONNECTOR" "--vpc-egress=${VPC_EGRESS:-private-ranges-only}")
fi
gcloud run jobs deploy "$JOB_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --image="$IMAGE" \
  --service-account="$WORKER_SERVICE_ACCOUNT" \
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" \
  --env-vars-file="$ENV_VARS_FILE" --set-secrets="$SECRET_MAPPINGS" \
  --command=python --args=-m,app.welcome_worker,--limit,20 \
  --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=3600s \
  --cpu=1 --memory=512Mi "${network_args[@]}"

# Grant invocation only on this specific job, not all project jobs/services.
gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$SCHEDULER_SERVICE_ACCOUNT" --role=roles/run.invoker

uri="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$JOB_NAME:run"
schedule_args=("--project=$PROJECT_ID" "--location=$REGION" \
  '--schedule=* * * * *' '--time-zone=Asia/Kolkata' \
  "--uri=$uri" '--http-method=POST' '--headers=Content-Type=application/json' \
  '--message-body={}' "--oauth-service-account-email=$SCHEDULER_SERVICE_ACCOUNT" \
  '--oauth-token-scope=https://www.googleapis.com/auth/cloud-platform')

# Only update an existing schedule after confirming that it targets this same job.
existing_uri="$(gcloud scheduler jobs list --project="$PROJECT_ID" --location="$REGION" \
  --filter="name:/$SCHEDULE_NAME" --format='value(httpTarget.uri)')"
if [[ -n "$existing_uri" ]]; then
  if [[ "$existing_uri" != "$uri" ]]; then
    echo 'Existing schedule has a different target; refusing to overwrite it.' >&2
    exit 1
  fi
  gcloud scheduler jobs update http "$SCHEDULE_NAME" "${schedule_args[@]}"
else
  gcloud scheduler jobs create http "$SCHEDULE_NAME" "${schedule_args[@]}"
fi

echo "Scheduled $JOB_NAME every minute. Check job executions and outbox state."
echo 'This script did not deploy the API image or run production migrations.'
