from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_customer

from app.models.admin.customer_profile import CustomerProfile

from app.schemas.customer.customer_receipt import (
    CustomerReceiptChitResponse,
    CustomerReceiptCompanyResponse,
    CustomerReceiptCustomerResponse,
    CustomerReceiptLiftResponse,
    CustomerReceiptMonthlyPaymentResponse,
    CustomerReceiptPaymentResponse,
    CustomerReceiptPaymentSummaryResponse,
    CustomerReceiptResponse,
)

from app.services.customer.customer_receipt_service import (
    get_customer_receipt_data,
)


router = APIRouter(
    prefix="/customer/my-chits",
    tags=["Customer Receipts"],
)


# =========================================================
# RESOLVE AUTHENTICATED CUSTOMER MOBILE
# =========================================================


def _get_customer_mobile(
    db: Session,
    current_customer: dict,
) -> str:

    """
    Resolve the authenticated customer's mobile number.

    Customer JWT may not contain mobile, so fall back to
    customer_profile_id.
    """

    mobile = current_customer.get(
        "mobile"
    )

    if mobile:

        return str(
            mobile
        ).strip()


    customer_profile_id = current_customer.get(
        "customer_profile_id"
    )

    if not customer_profile_id:

        raise HTTPException(
            status_code=401,
            detail=(
                "Customer identity is missing "
                "from authentication."
            ),
        )


    mobile_row = (
        db.query(
            CustomerProfile.mobile
        )
        .filter(
            CustomerProfile.id ==
            int(customer_profile_id),

            CustomerProfile.status ==
            "active",
        )
        .first()
    )


    if (
        not mobile_row
        or not mobile_row[0]
    ):

        raise HTTPException(
            status_code=401,
            detail=(
                "Customer mobile number "
                "could not be resolved."
            ),
        )


    return str(
        mobile_row[0]
    ).strip()


# =========================================================
# BUILD PAYMENT TRANSACTIONS BY INSTALLMENT
# =========================================================


def _build_monthly_payments(
    installments: list[dict],
    payments: list[dict],
) -> list[
    CustomerReceiptMonthlyPaymentResponse
]:

    # -------------------------------------------------------
    # Group payment transactions by installment_id
    # -------------------------------------------------------

    payments_by_installment: dict[
        int,
        list[
            CustomerReceiptPaymentResponse
        ],
    ] = {}


    for payment in payments:

        installment_id = int(
            payment["installment_id"]
        )


        payments_by_installment.setdefault(
            installment_id,
            [],
        ).append(
            CustomerReceiptPaymentResponse(
                payment_id=int(
                    payment["payment_id"]
                ),

                amount=Decimal(
                    str(
                        payment["amount"]
                    )
                ),

                payment_date=payment[
                    "payment_date"
                ],

                payment_method=str(
                    payment[
                        "payment_method"
                    ]
                    or ""
                ),

                reference_number=(
                    payment.get(
                        "reference_number"
                    )
                ),

                notes=(
                    payment.get(
                        "notes"
                    )
                ),
            )
        )


    # -------------------------------------------------------
    # Build monthly payment response
    # -------------------------------------------------------

    result: list[
        CustomerReceiptMonthlyPaymentResponse
    ] = []


    for installment in installments:

        installment_id = int(
            installment[
                "installment_id"
            ]
        )


        result.append(
            CustomerReceiptMonthlyPaymentResponse(

                installment_id=
                    installment_id,

                installment_number=int(
                    installment[
                        "installment_number"
                    ]
                ),

                due_date=
                    installment[
                        "due_date"
                    ],

                due_amount=Decimal(
                    str(
                        installment[
                            "due_amount"
                        ]
                    )
                ),

                paid_amount=Decimal(
                    str(
                        installment[
                            "paid_amount"
                        ]
                    )
                ),

                balance_amount=Decimal(
                    str(
                        installment[
                            "balance_amount"
                        ]
                    )
                ),

                status=str(
                    installment[
                        "status"
                    ]
                ),

                payments=
                    payments_by_installment.get(
                        installment_id,
                        [],
                    ),
            )
        )


    return result


# =========================================================
# GET CUSTOMER RECEIPT DATA
# =========================================================


@router.get(
    "/{chit_member_id}/receipt",
    response_model=CustomerReceiptResponse,
)
def get_customer_receipt(
    chit_member_id: int,

    db: Session = Depends(
        get_db
    ),

    current_customer: dict = Depends(
        get_current_customer
    ),
):

    # =====================================================
    # AUTHENTICATED CUSTOMER MOBILE
    # =====================================================

    mobile = _get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )


    # =====================================================
    # FETCH EXACT RECEIPT DATA
    # =====================================================

    receipt_data = (
        get_customer_receipt_data(
            db=db,
            customer_mobile=mobile,
            chit_member_id=chit_member_id,
        )
    )


    if not receipt_data:

        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized "
                "to view this chit receipt."
            ),
        )


    # =====================================================
    # RAW SERVICE DATA
    # =====================================================

    company = receipt_data[
        "company"
    ]

    customer = receipt_data[
        "customer"
    ]

    chit = receipt_data[
        "chit"
    ]

    member = receipt_data[
        "member"
    ]

    summary = receipt_data[
        "summary"
    ]

    installments = receipt_data[
        "installments"
    ]

    payments = receipt_data[
        "payments"
    ]

    lift = receipt_data.get(
        "lift"
    )


    # =====================================================
    # NO PAYMENT CHECK
    # =====================================================

    if not payments:

        raise HTTPException(
            status_code=404,
            detail=(
                "No payment transactions are "
                "available for this chit slot."
            ),
        )


    # =====================================================
    # MONTHLY PAYMENTS
    # =====================================================

    monthly_payments = (
        _build_monthly_payments(
            installments=installments,
            payments=payments,
        )
    )


    # =====================================================
    # DUE INSTALLMENTS
    # =====================================================

    due_installments = sum(
        1
        for installment in installments
        if Decimal(
            str(
                installment[
                    "balance_amount"
                ]
            )
        ) > Decimal("0")
    )


    # =====================================================
    # RECEIPT CHIT
    # =====================================================

    chit_response = (
        CustomerReceiptChitResponse(

            chit_member_id=int(
                member["id"]
            ),

            chit_id=int(
                chit["id"]
            ),

            chit_name=str(
                chit["name"]
            ),

            chit_code=str(
                chit["code"]
            ),

            customer_profile_id=int(
                customer["id"]
            ),

            customer_code=str(
                customer["code"]
            ),

            member_number=int(
                member["member_number"]
            ),

            slot_number=int(
                member["slot_number"]
            ),

            member_name=str(
                member["member_name"]
            ),

            member_status=str(
                member["status"]
            ),

            chit_value=Decimal(
                str(
                    chit["value"]
                )
            ),

            monthly_emi=Decimal(
                str(
                    chit["monthly_emi"]
                )
            ),

            duration_months=int(
                chit["duration_months"]
            ),

            start_date=chit[
                "start_date"
            ],
        )
    )


    # =====================================================
    # PAYMENT SUMMARY
    # =====================================================

    payment_summary = (
        CustomerReceiptPaymentSummaryResponse(

            total_installments=int(
                summary[
                    "total_installments"
                ]
            ),

            paid_installments=int(
                summary[
                    "paid_installments"
                ]
            ),

            due_installments=
                due_installments,

            partial_installments=int(
                summary[
                    "partial_installments"
                ]
            ),

            total_due_amount=Decimal(
                str(
                    summary[
                        "total_due"
                    ]
                )
            ),

            total_paid_amount=Decimal(
                str(
                    summary[
                        "total_paid"
                    ]
                )
            ),

            total_pending_amount=Decimal(
                str(
                    summary[
                        "pending_amount"
                    ]
                )
            ),
        )
    )


    # =====================================================
    # LIFT RESPONSE
    # =====================================================

    lift_response = None


    if lift:

        lift_response = (
            CustomerReceiptLiftResponse(

                lift_id=int(
                    lift[
                        "lift_id"
                    ]
                ),

                month_number=int(
                    lift[
                        "month_number"
                    ]
                ),

                month_date=
                    lift.get(
                        "month_date"
                    ),

                lift_date=
                    lift[
                        "lift_date"
                    ],

                monthly_lift_amount=
                    Decimal(
                        str(
                            lift[
                                "monthly_lift_amount"
                            ]
                        )
                    ),

                discount_amount=
                    Decimal(
                        str(
                            lift[
                                "discount_amount"
                            ]
                        )
                    ),

                lifted_amount=
                    Decimal(
                        str(
                            lift[
                                "lifted_amount"
                            ]
                        )
                    ),

                payout_status=str(
                    lift[
                        "payout_status"
                    ]
                ),

                payout_date=
                    lift.get(
                        "payout_date"
                    ),

                # Current receipt service may not
                # provide these two fields.
                cash_amount=(
                    Decimal(
                        str(
                            lift[
                                "cash_amount"
                            ]
                        )
                    )
                    if lift.get(
                        "cash_amount"
                    ) is not None
                    else None
                ),

                upi_amount=(
                    Decimal(
                        str(
                            lift[
                                "upi_amount"
                            ]
                        )
                    )
                    if lift.get(
                        "upi_amount"
                    ) is not None
                    else None
                ),
            )
        )


    # =====================================================
    # FINAL RESPONSE
    # =====================================================

    return CustomerReceiptResponse(

        success=True,

        message=(
            "Receipt data fetched successfully."
        ),

        company=(
            CustomerReceiptCompanyResponse(

                company_id=int(
                    company["id"]
                ),

                company_name=str(
                    company["name"]
                ),

                logo_url=
                    company.get(
                        "logo_url"
                    ),
                logo_data_url=company.get('logo_data_url'),

                email=
                    company.get(
                        "email"
                    ),

                mobile=
                    company.get(
                        "mobile"
                    ),

                address=
                    company.get(
                        "address"
                    ),
            )
        ),

        customer=(
            CustomerReceiptCustomerResponse(

                customer_profile_id=int(
                    customer["id"]
                ),

                customer_code=str(
                    customer["code"]
                ),

                display_name=str(
                    customer["name"]
                ),

                legal_name=
                    customer.get(
                        "legal_name"
                    ),

                mobile=str(
                    customer["mobile"]
                ),

                email=
                    customer.get(
                        "email"
                    ),

                address=
                    customer.get(
                        "address"
                    ),
            )
        ),

        chit=chit_response,

        payment_summary=
            payment_summary,

        monthly_payments=
            monthly_payments,

        lift_details=
            lift_response,

        generated_at=
            datetime.now(
                timezone.utc
            ),
    )