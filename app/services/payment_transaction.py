from concurrent.interpreters import get_current
from enum import member

from sqlalchemy import func
from sqlalchemy.orm import Session


from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.customer_profile import CustomerProfile
from app.services.audit_log_service import create_audit_log, snapshot_model


PAYMENT_AUDIT_FIELDS = [
    "id",
    "installment_id",
    "amount",
    "payment_date",
    "payment_method",
    "reference_number",
    "notes",
    "created_by",
]


def _payment_audit_snapshot(
    payment: PaymentTransaction,
    installment: ChitInstallment,
) -> dict:
    values = snapshot_model(
        payment,
        PAYMENT_AUDIT_FIELDS,
    )
    values.update({
        "chit_member_id": installment.chit_member_id,
        "installment_number": installment.installment_number,
        "installment_due_amount": installment.due_amount,
        "installment_status": installment.status,
    })

    return values


# =========================================================
# GET INSTALLMENT FOR CURRENT COMPANY
# =========================================================

def get_installment_for_company(
    db: Session,
    company_id: int,
    installment_id: int,
):
    return (
        db.query(ChitInstallment)
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id
            == ChitMember.chit_id,
        )
        .filter(
            ChitInstallment.id
            == installment_id,

            ChitGroup.company_id
            == company_id,
        )
        .first()
    )


# =========================================================
# GET TOTAL PAID
# =========================================================

def get_paid_amount(
    db: Session,
    installment_id: int,
) -> int:

    total_paid = (
        db.query(
            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            )
        )
        .filter(
            PaymentTransaction.installment_id
            == installment_id
        )
        .scalar()
    )

    return int(total_paid or 0)


# =========================================================
# UPDATE INSTALLMENT STATUS
# =========================================================

def update_installment_status(
    installment: ChitInstallment,
    paid_amount: int,
) -> None:

    due_amount = int(
        installment.due_amount
    )

    if paid_amount <= 0:

        installment.status = "pending"

    elif paid_amount < due_amount:

        installment.status = "partial"

    else:

        installment.status = "paid"

# Helper Function for create Payment Transaction
def validate_payment_sequence(
    db: Session,
    installment: ChitInstallment,
):
    """
    A customer must pay installments sequentially.

    Example:
        #1 paid
        #2 paid
        #3 pending
        #4 pending

    #4 payment is NOT allowed until #3 is fully paid.
    """

    previous_installments = (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.chit_member_id
            == installment.chit_member_id,

            ChitInstallment.installment_number
            < installment.installment_number,
        )
        .order_by(
            ChitInstallment.installment_number.asc()
        )
        .all()
    )

    for previous in previous_installments:

        paid_amount = get_paid_amount(
            db=db,
            installment_id=previous.id,
        )

        due_amount = int(
            previous.due_amount
        )

        if paid_amount < due_amount:

            return {
                "valid": False,
                "error": "previous_installment_unpaid",
                "previous_installment_number":
                    previous.installment_number,
                "previous_due_amount":
                    due_amount,
                "previous_paid_amount":
                    paid_amount,
                "previous_remaining_amount":
                    due_amount - paid_amount,
            }

    return {
        "valid": True
    }



# =========================================================
# CREATE PAYMENT
# =========================================================

def create_payment_transaction(
    db: Session,
    company_id: int,
    installment_id: int,
    payment_data,
    created_by: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    # =====================================================
    # FIND INSTALLMENT
    # =====================================================

    installment = get_installment_for_company(
        db=db,
        company_id=company_id,
        installment_id=installment_id,
    )

    if not installment:

        return {
            "error": "installment_not_found"
        }


    # =====================================================
    # VALIDATE PAYMENT SEQUENCE
    # =====================================================

    sequence_result = validate_payment_sequence(
        db=db,
        installment=installment,
    )

    if not sequence_result["valid"]:

        return sequence_result


    # =====================================================
    # PAYMENT AMOUNT
    # =====================================================

    payment_amount = int(
        payment_data.amount
    )

    if payment_amount <= 0:

        return {
            "error": "invalid_payment_amount"
        }


    # =====================================================
    # DUE AMOUNT
    # =====================================================

    due_amount = int(
        installment.due_amount
    )


    # =====================================================
    # EXISTING PAID AMOUNT
    # =====================================================

    paid_amount = get_paid_amount(
        db=db,
        installment_id=installment_id,
    )


    # =====================================================
    # OUTSTANDING
    # =====================================================

    outstanding_amount = (
        due_amount
        - paid_amount
    )


    # =====================================================
    # ALREADY PAID
    # =====================================================

    if outstanding_amount <= 0:

        return {
            "error": "installment_already_paid"
        }


    # =====================================================
    # OVERPAYMENT
    # =====================================================

    if payment_amount > outstanding_amount:

        return {
            "error": "payment_exceeds_balance",
            "outstanding_amount":
                outstanding_amount,
        }


    # =====================================================
    # CREATE PAYMENT
    # =====================================================

    payment = PaymentTransaction(

        installment_id=
            installment_id,

        amount=
            payment_amount,

        payment_date=
            payment_data.payment_date,

        payment_method=
            payment_data.payment_method.strip(),

        reference_number=(
            payment_data.reference_number.strip()
            if payment_data.reference_number
            else None
        ),

        notes=(
            payment_data.notes.strip()
            if payment_data.notes
            else None
        ),

        created_by=
            created_by,
    )


    db.add(payment)


    # =====================================================
    # UPDATE STATUS
    # =====================================================

    new_paid_amount = (
        paid_amount
        + payment_amount
    )


    update_installment_status(
        installment=installment,
        paid_amount=new_paid_amount,
    )


    # =====================================================
    # SAVE
    # =====================================================

    db.flush()

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=created_by,
        action="CREATE",
        module="Payments",
        entity_type="PaymentTransaction",
        entity_id=payment.id,
        description=(
            f"Recorded payment {payment.id} for installment "
            f"{installment.installment_number}"
        ),
        new_values=_payment_audit_snapshot(
            payment,
            installment,
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()


    # =====================================================
    # REFRESH
    # =====================================================

    db.refresh(payment)

    db.refresh(installment)


    return payment



# =========================================================
# GET PAYMENTS FOR INSTALLMENT
# =========================================================

def get_payments_for_installment(
    db: Session,
    company_id: int,
    installment_id: int,
):

    # -----------------------------------------------------
    # VERIFY INSTALLMENT
    # -----------------------------------------------------

    installment = get_installment_for_company(
        db=db,
        company_id=company_id,
        installment_id=installment_id,
    )

    if not installment:

        return {
            "error": "installment_not_found"
        }


    # -----------------------------------------------------
    # GET PAYMENTS
    # -----------------------------------------------------

    payments = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.installment_id
            == installment_id
        )
        .order_by(
            PaymentTransaction.payment_date.desc(),
            PaymentTransaction.id.desc(),
        )
        .all()
    )

    return payments





def get_chit_payment_summary(
    db: Session,
    company_id: int,
    chit_id: int,
):
    # =====================================================
    # VERIFY CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:
        return {
            "error": "chit_not_found"
        }


    # =====================================================
    # GET INSTALLMENTS
    # =====================================================

    installments = (
        db.query(ChitInstallment)
        .join(
            ChitMember,
            ChitMember.id == ChitInstallment.chit_member_id,
        )
        .filter(
            ChitMember.chit_id == chit_id,
        )
        .all()
    )


    total_due = 0
    total_paid = 0

    paid_installments = 0
    partial_installments = 0
    pending_installments = 0


    # =====================================================
    # CALCULATE
    # =====================================================

    for installment in installments:

        due_amount = int(
            installment.due_amount
        )

        paid_amount = (
            db.query(
                func.coalesce(
                    func.sum(
                        PaymentTransaction.amount
                    ),
                    0,
                )
            )
            .filter(
                PaymentTransaction.installment_id
                == installment.id
            )
            .scalar()
        )

        paid_amount = int(
            paid_amount or 0
        )

        total_due += due_amount

        total_paid += paid_amount


        if paid_amount <= 0:

            pending_installments += 1

        elif paid_amount < due_amount:

            partial_installments += 1

        else:

            paid_installments += 1


    return {
        "total_due": total_due,

        "total_paid": total_paid,

        "total_remaining":
            max(
                total_due - total_paid,
                0,
            ),

        "paid_installments":
            paid_installments,

        "partial_installments":
            partial_installments,

        "pending_installments":
            pending_installments,
    }
    
 

    # =========================================================
    # UPDATE PAYMENT
    # =========================================================

def update_payment(
    db: Session,
    company_id: int,
    payment_id: int,
    payment_data,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    # =====================================================
    # GET PAYMENT + VERIFY COMPANY
    # =====================================================

    payment = (
        db.query(PaymentTransaction)
        .join(
            ChitInstallment,
            ChitInstallment.id
            == PaymentTransaction.installment_id,
        )
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id
            == ChitMember.chit_id,
        )
        .filter(
            PaymentTransaction.id == payment_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )
    
    
    if not payment:
        return {
            "error": "payment_not_found"
        }


    # =====================================================
    # GET INSTALLMENT
    # =====================================================

    installment = (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.id
            == payment.installment_id,
        )
        .first()
    )

    if not installment:

        return {
            "error": "installment_not_found"
        }

    old_values = _payment_audit_snapshot(
        payment,
        installment,
    )


    # =====================================================
    # VALIDATE PAYMENT AMOUNT
    # =====================================================

    amount = int(
        payment_data.amount
    )


    if amount <= 0:

        return {
            "error": "invalid_amount"
        }


    # =====================================================
    # GET OTHER PAYMENTS
    #
    # Exclude the payment currently being edited.
    # =====================================================

    other_paid_amount = (
        db.query(
            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            )
        )
        .filter(
            PaymentTransaction.installment_id
            == installment.id,

            PaymentTransaction.id
            != payment.id,
        )
        .scalar()
    )


    other_paid_amount = int(
        other_paid_amount or 0
    )


    # =====================================================
    # CHECK OVERPAYMENT
    # =====================================================

    total_after_update = (
        other_paid_amount
        + amount
    )


    if (
        total_after_update
        > int(installment.due_amount)
    ):

        remaining_for_payment = (
            int(installment.due_amount)
            - other_paid_amount
        )


        return {
            "error":
                "amount_exceeds_installment",

            "remaining_amount":
                max(
                    remaining_for_payment,
                    0,
                ),
        }


    # =====================================================
    # UPDATE PAYMENT
    # =====================================================

    payment.amount = amount


    payment.payment_date = (
        payment_data.payment_date
    )


    payment.payment_method = (
        payment_data.payment_method.strip()
    )


    payment.reference_number = (
        payment_data.reference_number.strip()
        if payment_data.reference_number
        else None
    )


    payment.notes = (
        payment_data.notes.strip()
        if payment_data.notes
        else None
    )


    # =====================================================
    # RECALCULATE INSTALLMENT STATUS
    # =====================================================

    new_paid_amount = (
        other_paid_amount
        + amount
    )


    update_installment_status(
        installment=installment,
        paid_amount=new_paid_amount,
    )


    # =====================================================
    # SAVE
    # =====================================================

    db.flush()

    new_values = _payment_audit_snapshot(
        payment,
        installment,
    )

    if old_values != new_values:
        create_audit_log(
            db=db,
            company_id=company_id,
            user_id=updated_by,
            action="UPDATE",
            module="Payments",
            entity_type="PaymentTransaction",
            entity_id=payment.id,
            description=f"Updated payment {payment.id}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    db.commit()


    db.refresh(payment)

    db.refresh(installment)


    return payment



# =========================================================
# DELETE PAYMENT
# =========================================================

def delete_payment(
    db: Session,
    company_id: int,
    payment_id: int,
    deleted_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    # =====================================================
    # GET PAYMENT + VERIFY COMPANY
    # =====================================================

    payment = (
        db.query(PaymentTransaction)
        .join(
            ChitInstallment,
            ChitInstallment.id
            == PaymentTransaction.installment_id,
        )
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id
            == ChitMember.chit_id,
        )
        .filter(
            PaymentTransaction.id == payment_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )


    if not payment:

        return {
            "error": "payment_not_found"
        }


    # =====================================================
    # GET INSTALLMENT BEFORE DELETE
    # =====================================================

    installment = (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.id
            == payment.installment_id,
        )
        .first()
    )


    if not installment:

        return {
            "error": "installment_not_found"
        }

    old_values = _payment_audit_snapshot(
        payment,
        installment,
    )


    # =====================================================
    # DELETE PAYMENT
    # =====================================================

    db.delete(payment)

    db.flush()


    # =====================================================
    # RECALCULATE PAID AMOUNT
    # =====================================================

    new_paid_amount = get_paid_amount(
        db=db,
        installment_id=installment.id,
    )


    # =====================================================
    # UPDATE INSTALLMENT STATUS
    # =====================================================

    update_installment_status(
        installment=installment,
        paid_amount=new_paid_amount,
    )


    # =====================================================
    # SAVE
    # =====================================================

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=deleted_by,
        action="DELETE",
        module="Payments",
        entity_type="PaymentTransaction",
        entity_id=payment_id,
        description=f"Deleted payment {payment_id}",
        old_values=old_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()


    db.refresh(installment)


    return True 
#========================================================
# GET MEMBER PAYMENT SUMMARY
#========================================================


def get_member_payment_summary(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
):

    member = (
        db.query(ChitMember)
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            ChitMember.id == member_id,
            ChitMember.chit_id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not member:

        return {
            "error": "member_not_found"
        }


    installments = (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.chit_member_id
            == member.id
        )
        .all()
    )


    total_due = 0
    total_paid = 0


    for installment in installments:

        due_amount = int(
            installment.due_amount
        )


        paid_amount = (
            db.query(
                func.coalesce(
                    func.sum(
                        PaymentTransaction.amount
                    ),
                    0,
                )
            )
            .filter(
                PaymentTransaction.installment_id
                == installment.id
            )
            .scalar()
        )


        paid_amount = int(
            paid_amount or 0
        )


        total_due += due_amount

        total_paid += paid_amount


    return {

        "member_id":
            member.id,

        "member_number":
            member.member_number,

        "customer_profile_id":
            member.customer_profile_id,

        "member_name":
            member.member_name,

        "total_due":
            total_due,

        "total_paid":
            total_paid,

        "total_remaining":
            max(
                total_due - total_paid,
                0,
            ),

    }
    

#=========================================================
# GET PAYMENTS FOR A CHIT
#=========================================================

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.payment_transaction import PaymentTransaction


# =========================================================
# GET CHIT PAYMENT DETAILS
# =========================================================

def get_chit_payment_details(
    db: Session,
    company_id: int,
    chit_id: int,
    month: int | None = None,
    year: int | None = None,
    status_filter: str | None = None,
):
    # =====================================================
    # VERIFY CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:
        return {
            "error": "chit_not_found"
        }

    # =====================================================
    # VALIDATE STATUS FILTER
    # =====================================================

    allowed_statuses = {
        "all",
        "paid",
        "partial",
        "due",
    }

    if status_filter:
        status_filter = status_filter.strip().lower()

        if status_filter not in allowed_statuses:
            return {
                "error": "invalid_status"
            }
    else:
        status_filter = "all"

    # =====================================================
    # GET INSTALLMENTS
    #
    # IMPORTANT:
    # ChitInstallment is the base table.
    #
    # Therefore unpaid installments also appear.
    # =====================================================

    query = (
        db.query(
            ChitInstallment,
            ChitMember,
        )
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .filter(
            ChitMember.chit_id == chit_id,
            ChitMember.status.in_([
                "active",
                "confirmed",
            ]),
        )
    )

    # =====================================================
    # MONTH FILTER
    # =====================================================

    if month is not None:
        query = query.filter(
            func.month(
                ChitInstallment.due_date
            ) == month
        )

    # =====================================================
    # YEAR FILTER
    # =====================================================

    if year is not None:
        query = query.filter(
            func.year(
                ChitInstallment.due_date
            ) == year
        )

    # =====================================================
    # ORDER
    # =====================================================

    query = query.order_by(
        ChitInstallment.installment_number.asc(),
        ChitMember.member_number.asc(),
        ChitMember.id.asc(),
    )

    installment_rows = query.all()

    # =====================================================
    # EMPTY RESULT
    # =====================================================

    if not installment_rows:
        return {
            "summary": {
                "total_months": 0,
                "total_members": 0,
                "total_due": 0,
                "total_paid": 0,
                "total_remaining": 0,
                "paid_members": 0,
                "partial_members": 0,
                "due_members": 0,
            },
            "items": [],
        }

    # =====================================================
    # GET INSTALLMENT IDS
    # =====================================================

    installment_ids = [
        installment.id
        for installment, member in installment_rows
    ]

    # =====================================================
    # GET ALL PAYMENTS IN ONE QUERY
    #
    # Avoid N+1 queries.
    # =====================================================

    payment_rows = (
        db.query(
            PaymentTransaction.installment_id,
            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            ).label("paid_amount"),
        )
        .filter(
            PaymentTransaction.installment_id.in_(
                installment_ids
            )
        )
        .group_by(
            PaymentTransaction.installment_id
        )
        .all()
    )

    # =====================================================
    # PAYMENT LOOKUP
    # =====================================================

    paid_by_installment = {
        row.installment_id: int(
            row.paid_amount or 0
        )
        for row in payment_rows
    }

    # =====================================================
    # BUILD ITEMS
    # =====================================================

    items = []

    for installment, member in installment_rows:

        due_amount = int(
            installment.due_amount or 0
        )

        paid_amount = int(
            paid_by_installment.get(
                installment.id,
                0,
            )
        )

        remaining_amount = max(
            due_amount - paid_amount,
            0,
        )

        # -------------------------------------------------
        # DERIVE STATUS
        # -------------------------------------------------

        if (
            paid_amount >= due_amount
            and due_amount > 0
        ):
            payment_status = "paid"

        elif paid_amount > 0:
            payment_status = "partial"

        else:
            payment_status = "due"

        # -------------------------------------------------
        # STATUS FILTER
        # -------------------------------------------------

        if (
            status_filter != "all"
            and payment_status != status_filter
        ):
            continue

        # -------------------------------------------------
        # ITEM
        # -------------------------------------------------

        items.append({
            "id": installment.id,

            "chit_id": chit.id,

            "chit_member_id":
                member.id,

            "member_id":
                member.id,

            "member_number":
                member.member_number,

            "member_name":
                member.member_name,

            "slot_number":
                getattr(
                    member,
                    "slot_number",
                    None,
                ),

            "installment_number":
                installment.installment_number,

            "due_date":
                installment.due_date,

            "due_amount":
                due_amount,

            "paid_amount":
                paid_amount,

            "remaining_amount":
                remaining_amount,

            "status":
                payment_status,

            "created_at":
                installment.created_at,

            "updated_at":
                installment.updated_at,
        })

    # =====================================================
    # SUMMARY
    #
    # IMPORTANT:
    # Summary is calculated AFTER status filtering.
    # So cards always match the table.
    # =====================================================

    total_due = 0
    total_paid = 0
    total_remaining = 0

    paid_members = 0
    partial_members = 0
    due_members = 0

    for item in items:

        total_due += item["due_amount"]

        total_paid += min(
            item["paid_amount"],
            item["due_amount"],
        )

        total_remaining += item[
            "remaining_amount"
        ]

        if item["status"] == "paid":
            paid_members += 1

        elif item["status"] == "partial":
            partial_members += 1

        elif item["status"] == "due":
            due_members += 1

    # =====================================================
    # TOTAL MONTHS
    #
    # Count unique installment numbers.
    # =====================================================

    total_months = len({
        item["installment_number"]
        for item in items
    })

    # =====================================================
    # RESPONSE
    # =====================================================

    return {
        "summary": {
            "total_months":
                total_months,

            "total_members":
                len(items),

            "total_due":
                total_due,

            "total_paid":
                total_paid,

            "total_remaining":
                total_remaining,

            "paid_members":
                paid_members,

            "partial_members":
                partial_members,

            "due_members":
                due_members,
        },

        "items": items,
    }
    
    
    
# =========================================================
# GET PAYMENT HISTORY FOR CUSTOMER + CHIT
# =========================================================

def get_customer_chit_payment_history(
    db: Session,
    company_id: int,
    customer_id: int,
    chit_id: int,
    member_id:int,
):

    # =====================================================
    # GET CUSTOMER
    # =====================================================

    customer = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id == customer_id,
            CustomerProfile.company_id == company_id,
        )
        .first()
    )

    if not customer:

        return {
            "error": "customer_not_found"
        }


    # =====================================================
    # GET CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:

        return {
            "error": "chit_not_found"
        }


    # =====================================================
    # GET CUSTOMER MEMBERSHIP IN THIS CHIT
    # =====================================================

    member = (
        db.query(ChitMember)
        .filter(
            ChitMember.id == member_id,
            ChitMember.chit_id == chit_id,
            ChitMember.customer_profile_id
            == customer_id,
            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
        )
        .first()
    )

    if not member:

        return {
            "error": "membership_not_found"
        }


    # =====================================================
    # GET INSTALLMENTS + PAYMENTS
    # =====================================================

    rows = (
        db.query(
            ChitInstallment,
            PaymentTransaction,
        )
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .join(
            PaymentTransaction,
            PaymentTransaction.installment_id
            == ChitInstallment.id,
        )
        .filter(
            ChitMember.id == member.id,
        )
        .order_by(
            ChitInstallment.installment_number.asc(),
            PaymentTransaction.payment_date.asc(),
            PaymentTransaction.id.asc(),
        )
        .all()
    )


    # =====================================================
    # GET ALL INSTALLMENTS FOR SUMMARY
    # =====================================================

    installment_rows = (
        db.query(
            ChitInstallment.id,

            ChitInstallment.due_amount,

            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            ).label("paid_amount"),
        )
        .outerjoin(
            PaymentTransaction,
            PaymentTransaction.installment_id
            == ChitInstallment.id,
        )
        .filter(
            ChitInstallment.chit_member_id
            == member.id,
        )
        .group_by(
            ChitInstallment.id,
            ChitInstallment.due_amount,
        )
        .order_by(
            ChitInstallment.id.asc()
        )
        .all()
    )


    # =====================================================
    # SUMMARY
    # =====================================================

    total_months = len(
        installment_rows
    )

    total_due = sum(
        int(row.due_amount or 0)
        for row in installment_rows
    )

    total_paid = sum(
        int(row.paid_amount or 0)
        for row in installment_rows
    )

    remaining_amount = max(
        total_due - total_paid,
        0,
    )

    paid_months = sum(
        1
        for row in installment_rows
        if int(row.paid_amount or 0)
        >= int(row.due_amount or 0)
        and int(row.due_amount or 0) > 0
    )

    remaining_months = max(
        total_months - paid_months,
        0,
    )


    # =====================================================
    # PAYMENT ITEMS
    # =====================================================

    payments = []


    for installment, payment in rows:

        # ---------------------------------------------
        # Total paid for this installment
        # ---------------------------------------------

        installment_paid = (
            db.query(
                func.coalesce(
                    func.sum(
                        PaymentTransaction.amount
                    ),
                    0,
                )
            )
            .filter(
                PaymentTransaction.installment_id
                == installment.id,
            )
            .scalar()
        )

        installment_paid = int(
            installment_paid or 0
        )


        due_amount = int(
            installment.due_amount or 0
        )


        remaining = max(
            due_amount - installment_paid,
            0,
        )


        payments.append({

            "payment_id":
                payment.id,

            "installment_id":
                installment.id,

            "installment_number":
                installment.installment_number,

            "due_date":
                installment.due_date,

            "due_amount":
                due_amount,
            "payment_amount": int(payment.amount or 0),
            "paid_amount": installment_paid,
            "remaining_amount":
                remaining,

            "payment_date":
                payment.payment_date,

            "payment_method":
                payment.payment_method,

            "reference_number":
                payment.reference_number,

            "notes":
                payment.notes,

            "created_by":
                payment.created_by,

            "created_at":
                payment.created_at,

        })


    # =====================================================
    # RESPONSE
    # =====================================================

    return {

        "customer_id":
            customer.id,

        "chit_id":
            chit.id,

        "member_id":
            member.id,

        "member_number":
            member.member_number,

        "member_name":
            member.member_name,

        "chit_name":
            chit.name,

        "chit_code":
            chit.code,

        "monthly_emi":
            int(chit.monthly_emi or 0),

        "total_months":
            total_months,

        "total_due":
            total_due,

        "total_paid":
            total_paid,

        "remaining_amount":
            remaining_amount,

        "paid_months":
            paid_months,

        "remaining_months":
            remaining_months,

        "payments":
            payments,
    }
