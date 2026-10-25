"""Bounded whole-transaction retries for InnoDB deadlocks in capacity writers."""
from functools import wraps
from inspect import signature
from time import sleep

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError


def retry_subscription_transaction(function):
    parameters = signature(function)

    @wraps(function)
    def retry(*args, **kwargs):
        db = parameters.bind(*args, **kwargs).arguments["db"]
        for attempt in range(3):
            try:
                return function(*args, **kwargs)
            except OperationalError as error:
                # These writers do not perform external side effects before
                # commit. Roll back the ENTIRE attempt before reading again.
                if not error.orig.args or error.orig.args[0] not in (1205, 1213):
                    raise
                db.rollback()
                if attempt == 2:
                    raise HTTPException(503, {"code": "SUBSCRIPTION_BUSY",
                        "message": "Concurrent changes are in progress. Please retry."}) from error
                sleep(0.01 * (attempt + 1))
    return retry
