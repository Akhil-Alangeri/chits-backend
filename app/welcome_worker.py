"""Run as a scheduled Cloud Run Job: python -m app.welcome_worker --limit 100."""
import argparse
import logging
import os
import time

from app.core.database import SessionLocal
from app.services.welcome_email import smtp_config, EmailConfigurationError
from app.services.welcome_notifications import process_welcome_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--watch", action="store_true", help="Keep polling for local development; use a scheduled batch job in production")
    parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds for --watch")
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    if not 5 <= args.interval <= 3600:
        parser.error("--interval must be between 5 and 3600 seconds")
    logging.basicConfig(level=logging.INFO)
    if os.getenv("WELCOME_EMAIL_DELIVERY_ENABLED", "false").lower() != "true":
        logging.warning("Welcome delivery disabled; no notifications claimed")
        return 0
    try:
        smtp_config()
    except EmailConfigurationError:
        logging.error("Configure SMTP_HOST/PORT/USERNAME/PASSWORD/FROM and encrypted transport; no notifications claimed")
        return 1
    if args.watch:
        logging.info("Welcome worker polling every %s seconds; Ctrl+C stops it", args.interval)
    while True:
        try:
            count = process_welcome_batch(SessionLocal, args.limit)
            if count or not args.watch:
                logging.info("Welcome notifications processed: %s", count)
        except KeyboardInterrupt:
            return 0
        except Exception:
            logging.error("Welcome worker database failure; check database and migration status")
            if not args.watch:
                return 1
        if not args.watch:
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
