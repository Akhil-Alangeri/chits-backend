from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import SessionLocal
from app.services.notification_service import (
    send_all_companies_monthly_notifications,
)


scheduler = BackgroundScheduler(
    timezone="Asia/Kolkata"
)


def monthly_notification_job():
    db = SessionLocal()

    try:

        print(
            "Starting monthly chit notifications..."
        )

        result = (
            send_all_companies_monthly_notifications(
                db
            )
        )

        print(
            "Monthly notification result:",
            result,
        )

    except Exception as exc:

        print(
            "Monthly notification job failed:",
            exc,
        )

    finally:
        db.close()


def start_scheduler():

    scheduler.add_job(
        monthly_notification_job,
        trigger="cron",
        day=1,
        hour=9,
        minute=0,
        id="monthly_chit_notifications",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()

    print(
        "Monthly notification scheduler started"
    )


def stop_scheduler():

    if scheduler.running:
        scheduler.shutdown()

        print(
            "Monthly notification scheduler stopped"
        )