from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MonthlyNotificationResponse(BaseModel):
    company_id: int
    company_name: str

    total: int
    sent: int
    skipped: int
    already_sent: int
    failed: int


class CompanyNotificationResult(BaseModel):
    company_id: int
    company_name: str

    total: int
    sent: int
    skipped: int
    already_sent: int
    failed: int


class AllCompaniesNotificationResponse(BaseModel):
    companies: int

    total: int
    sent: int
    skipped: int
    already_sent: int
    failed: int

    company_results: list[CompanyNotificationResult]