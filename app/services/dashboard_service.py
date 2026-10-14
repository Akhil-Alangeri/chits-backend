from sqlalchemy import and_
from app.services.entitlement_service import get_company_effective_features
from datetime import date

from decimal import Decimal



from sqlalchemy import func

from sqlalchemy.orm import Session



from app.models.admin.loan import Loan

from app.models.admin.loan_transaction import LoanTransaction

from app.models.admin.expenses import Expense



from app.models.admin.chit_group import ChitGroup

from app.models.admin.chit_member import ChitMember

from app.models.admin.chit_installment import ChitInstallment

from app.models.admin.payment_transaction import PaymentTransaction

from app.models.admin.customer_profile import CustomerProfile



from app.models.admin.chit_months import ChitMonth

from app.models.admin.chitlift import ChitLift





# =========================================================

# DATE HELPERS

# =========================================================



def get_month_range(target_date: date):

    start_date = target_date.replace(day=1)



    if start_date.month == 12:

        next_month = date(

            start_date.year + 1,

            1,

            1,

        )

    else:

        next_month = date(

            start_date.year,

            start_date.month + 1,

            1,

        )



    return start_date, next_month





def get_year_range(target_date: date):

    start_date = date(

        target_date.year,

        1,

        1,

    )



    end_date = date(

        target_date.year + 1,

        1,

        1,

    )



    return start_date, end_date

# =========================================================
# DASHBOARD YEAR OPTIONS
# =========================================================

def get_available_dashboard_years(
    db: Session,
    company_id: int,
):
    """Return analysis years from the earliest relevant data through current year."""
    company_features = get_company_effective_features(db, company_id)
    current_year = date.today().year
    years = {current_year}

    earliest_chit_start = (
        db.query(func.min(ChitGroup.start_date))
        .filter(ChitGroup.company_id == company_id)
        .scalar()
    )

    earliest_installment_date = (
        db.query(func.min(ChitInstallment.due_date))
        .join(ChitMember, ChitMember.id == ChitInstallment.chit_member_id)
        .join(ChitGroup, ChitGroup.id == ChitMember.chit_id)
        .filter(ChitGroup.company_id == company_id)
        .scalar()
    )

    earliest_payment_date = (
        db.query(func.min(PaymentTransaction.payment_date))
        .join(ChitInstallment, ChitInstallment.id == PaymentTransaction.installment_id)
        .join(ChitMember, ChitMember.id == ChitInstallment.chit_member_id)
        .join(ChitGroup, ChitGroup.id == ChitMember.chit_id)
        .filter(ChitGroup.company_id == company_id)
        .scalar()
    )

    earliest_expense_date = (
        db.query(func.min(Expense.expense_date))
        .filter(and_(Expense.company_id == company_id, company_features.get("expenses", False)))
        .scalar()
    )

    for value in (
        earliest_chit_start,
        earliest_installment_date,
        earliest_payment_date,
        earliest_expense_date,
    ):
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                value = None

        if value:
            years.add(value.year)

    first_year = min(years)
    return list(range(first_year, current_year + 1))


# =========================================================

# MONEY HELPER

# =========================================================



def money(value) -> Decimal:

    """

    Safely convert DB numeric values into Decimal.

    """



    if value is None:

        return Decimal("0")



    if isinstance(value, Decimal):

        return value



    try:

        return Decimal(str(value))

    except Exception:

        return Decimal("0")





# =========================================================

# LOAN SUMMARY

# =========================================================



def get_loan_summary(

    db: Session,

    company_id: int,

):

    """

    Get company-level loan summary.



    Loan directions:

        given = money given by company

        taken = money taken by company



    Outstanding principal is calculated from

    principal repayments.

    """
    company_features = get_company_effective_features(db, company_id)



    loans = (

        db.query(Loan)

        .filter(

            and_(Loan.company_id == company_id, company_features.get("loans", False)),

        )

        .all()

    )



    total_count = len(loans)



    active_count = 0

    partially_settled_count = 0

    closed_count = 0



    given_amount = Decimal("0")

    taken_amount = Decimal("0")



    given_outstanding = Decimal("0")

    taken_outstanding = Decimal("0")



    # -----------------------------------------------------

    # Get all transactions once

    # -----------------------------------------------------



    loan_ids = [

        loan.id

        for loan in loans

    ]



    transactions_by_loan = {}



    if loan_ids:



        transactions = (

            db.query(LoanTransaction)

            .filter(

                and_(LoanTransaction.company_id == company_id, company_features.get("loans", False)),

                LoanTransaction.loan_id.in_(loan_ids),

            )

            .all()

        )



        for transaction in transactions:



            transactions_by_loan.setdefault(

                transaction.loan_id,

                [],

            ).append(transaction)



    # -----------------------------------------------------

    # Calculate loans

    # -----------------------------------------------------



    for loan in loans:



        principal = money(

            loan.principal_amount

        )



        principal_paid = Decimal("0")



        transactions = transactions_by_loan.get(

            loan.id,

            [],

        )



        for transaction in transactions:



            if transaction.transaction_type == "principal_repayment":



                principal_paid += money(

                    transaction.principal_amount

                )



        outstanding = max(

            principal - principal_paid,

            Decimal("0"),

        )



        # -------------------------------------------------

        # STATUS

        # -------------------------------------------------



        if loan.status == "active":



            active_count += 1



        elif loan.status == "partially_settled":



            partially_settled_count += 1



        elif loan.status == "closed":



            closed_count += 1



        # -------------------------------------------------

        # DIRECTION

        # -------------------------------------------------



        if loan.direction == "given":



            given_amount += principal

            given_outstanding += outstanding



        elif loan.direction == "taken":



            taken_amount += principal

            taken_outstanding += outstanding



    total_outstanding = (

        given_outstanding

        + taken_outstanding

    )



    return {

        "total_count": total_count,



        "active_count": active_count,



        "partially_settled_count":

            partially_settled_count,



        "closed_count":

            closed_count,



        "given_amount":

            given_amount,



        "taken_amount":

            taken_amount,



        "given_outstanding":

            given_outstanding,



        "taken_outstanding":

            taken_outstanding,



        "total_outstanding":

            total_outstanding,

    }





# =========================================================

# LOAN CASH FLOW

# =========================================================



def get_loan_cash_flow(

    db: Session,

    company_id: int,

):

    company_features = get_company_effective_features(db, company_id)
    loans = (

        db.query(Loan)

        .filter(

            and_(Loan.company_id == company_id, company_features.get("loans", False)),

        )

        .all()

    )



    loan_given = Decimal("0")



    loan_given_cash = Decimal("0")

    loan_given_upi = Decimal("0")



    for loan in loans:



        if loan.direction == "given":



            loan_given += money(

                loan.principal_amount

            )



            # Get disbursement transaction

            disbursement = (

                db.query(LoanTransaction)

                .filter(

                    and_(LoanTransaction.company_id == company_id, company_features.get("loans", False)),

                    LoanTransaction.loan_id == loan.id,

                    LoanTransaction.transaction_type == "disbursement",

                )

                .first()

            )



            if disbursement:



                loan_given_cash += money(

                    disbursement.cash_amount

                )



                loan_given_upi += money(

                    disbursement.upi_amount

                )



    # -----------------------------------------------------

    # LOAN REPAYMENTS

    # -----------------------------------------------------



    repayment_rows = (

        db.query(

            func.coalesce(

                func.sum(

                    LoanTransaction.principal_amount

                ),

                0,

            ),

            func.coalesce(

                func.sum(

                    LoanTransaction.interest_amount

                ),

                0,

            ),

            func.coalesce(

                func.sum(

                    LoanTransaction.cash_amount

                ),

                0,

            ),

            func.coalesce(

                func.sum(

                    LoanTransaction.upi_amount

                ),

                0,

            ),

        )

        .filter(

            and_(LoanTransaction.company_id == company_id, company_features.get("loans", False)),

            LoanTransaction.transaction_type.in_([

                "principal_repayment",

                "interest_payment",

            ]),

        )

        .one()

    )



    principal_repaid = money(

        repayment_rows[0]

    )



    interest_received = money(

        repayment_rows[1]

    )



    loan_repayments = (

        principal_repaid

        + interest_received

    )



    loan_repayment_cash = money(

        repayment_rows[2]

    )



    loan_repayment_upi = money(

        repayment_rows[3]

    )



    return {

        "loan_given": loan_given,



        "loan_given_cash":

            loan_given_cash,



        "loan_given_upi":

            loan_given_upi,



        "loan_repayments":

            loan_repayments,



        "loan_repayment_cash":

            loan_repayment_cash,



        "loan_repayment_upi":

            loan_repayment_upi,

    }




# =========================================================

# COMPANY CASH / BANK LEDGER

# =========================================================



def get_company_cash_bank_ledger(

    db: Session,

    company_id: int,

):

    """

    Calculate the company's current Cash-in-Hand and

    Bank/UPI balance from all recorded financial transactions.



    MONEY IN:

        - Chit collections

        - Loan taken

        - Given loan repayments



    MONEY OUT:

        - Loan given

        - Taken loan repayments

        - Expenses



    Returns:

        cash

        bank

        total

    """
    company_features = get_company_effective_features(db, company_id)



    cash_balance = Decimal("0")

    bank_balance = Decimal("0")



    # =====================================================

    # 1. CHIT COLLECTIONS

    # =====================================================



    collection_rows = (

        db.query(

            PaymentTransaction.payment_method,

            func.coalesce(

                func.sum(PaymentTransaction.amount),

                0,

            ),

        )

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

            ChitGroup.company_id == company_id,

        )

        .group_by(

            PaymentTransaction.payment_method,

        )

        .all()

    )



    for payment_method, amount in collection_rows:



        method = (

            payment_method or ""

        ).strip().lower()



        amount = money(amount)



        if method == "cash":



            cash_balance += amount



        elif method in (

            "upi",

            "bank_transfer",

        ):



            bank_balance += amount





    # ======================================================

    # Lift Rows&#x20;

    # ======================================================

    lift_rows =(

        db.query(

            ChitLift.cash_amount,

            ChitLift.upi_amount

        )

        .filter(

            ChitLift.company_id == company_id,

            ChitLift.payout_status == "paid",

        )

        .all()

    )



    for cash_amount,upi_amount in lift_rows:

        cash_amount=money(cash_amount)

        upi_amount=money(upi_amount)

        # Company pays chit winner

         # => MONEY OUT

        cash_balance -= cash_amount

        bank_balance -= upi_amount





    # =====================================================

    # 2. LOAN TRANSACTIONS

    # =====================================================



    loan_rows = (

        db.query(

            Loan.direction,

            LoanTransaction.transaction_type,

            LoanTransaction.cash_amount,

            LoanTransaction.upi_amount,

        )

        .join(

            Loan,

            Loan.id == LoanTransaction.loan_id,

        )

        .filter(

            and_(Loan.company_id == company_id, company_features.get("loans", False)),

            and_(LoanTransaction.company_id == company_id, company_features.get("loans", False)),

        )

        .all()

    )



    for (

        direction,

        transaction_type,

        cash_amount,

        upi_amount,

    ) in loan_rows:



        cash_amount = money(

            cash_amount

        )



        upi_amount = money(

            upi_amount

        )



        # -------------------------------------------------

        # LOAN GIVEN

        # -------------------------------------------------

        #

        # Company gives money to customer

        # => MONEY OUT

        #

        # -------------------------------------------------



        if (

            direction == "given"

            and transaction_type == "disbursement"

        ):



            cash_balance -= cash_amount

            bank_balance -= upi_amount



        # -------------------------------------------------

        # LOAN TAKEN

        # -------------------------------------------------

        #

        # Company receives money

        # => MONEY IN

        #

        elif (

            direction == "taken"

            and transaction_type == "disbursement"

        ):



            cash_balance += cash_amount

            bank_balance += upi_amount



        # -------------------------------------------------

        # GIVEN LOAN REPAYMENT

        # -------------------------------------------------

        #

        # Customer pays company

        # => MONEY IN

        #

        elif (

            direction == "given"

            and transaction_type in (

                "principal_repayment",

                "interest_payment",

            )

        ):



            cash_balance += cash_amount

            bank_balance += upi_amount



        # -------------------------------------------------

        # TAKEN LOAN REPAYMENT

        # -------------------------------------------------

        #

        # Company pays lender

        # => MONEY OUT

        #

        elif (

            direction == "taken"

            and transaction_type in (

                "principal_repayment",

                "interest_payment",

            )

        ):



            cash_balance -= cash_amount

            bank_balance -= upi_amount



    # =====================================================

    # 3. EXPENSES

    # =====================================================



    expense_rows = (

        db.query(

            Expense.payment_method,

            func.coalesce(

                func.sum(Expense.amount),

                0,

            ),

        )

        .filter(

            and_(Expense.company_id == company_id, company_features.get("expenses", False)),

        )

        .group_by(

            Expense.payment_method,

        )

        .all()

    )



    for payment_method, amount in expense_rows:



        method = (

            payment_method or ""

        ).strip().lower()



        amount = money(amount)



        # Company spends money

        if method == "cash":



            cash_balance -= amount



        elif method in (

            "upi",

            "bank_transfer",

        ):



            bank_balance -= amount



    # =====================================================

    # FINAL

    # =====================================================



    cash_balance = money(

        cash_balance

    )





    bank_balance = money(

        bank_balance

    )





    total_balance = money(

        cash_balance

        + bank_balance

    )



    return {

        "cash": cash_balance,

        "bank": bank_balance,

        "total": total_balance,

    }


def get_expense_summary(
    db: Session,
    company_id: int,
    selected_year: int | None = None,
    selected_month: int | None = None,
):
    """Company-wide expense summary with selectable year/month."""
    company_features = get_company_effective_features(db, company_id)

    today = date.today()
    selected_year = selected_year or today.year
    selected_month = selected_month or today.month

    if selected_month < 1 or selected_month > 12:
        selected_month = today.month

    selected_date = date(selected_year, selected_month, 1)
    selected_month_start, selected_next_month_start = get_month_range(selected_date)

    total_expense_row = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(and_(Expense.company_id == company_id, company_features.get("expenses", False)))
        .one()
    )
    total_expense = money(total_expense_row[0])

    expense_cash_row = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            and_(Expense.company_id == company_id, company_features.get("expenses", False)),
            func.lower(Expense.payment_method) == "cash",
        )
        .one()
    )

    expense_upi_row = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            and_(Expense.company_id == company_id, company_features.get("expenses", False)),
            func.lower(Expense.payment_method) == "upi",
        )
        .one()
    )

    expense_cash = money(expense_cash_row[0])
    expense_upi = money(expense_upi_row[0])

    month_expense_row = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            and_(Expense.company_id == company_id, company_features.get("expenses", False)),
            Expense.expense_date >= selected_month_start,
            Expense.expense_date < selected_next_month_start,
        )
        .one()
    )

    month_expense_cash_row = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            and_(Expense.company_id == company_id, company_features.get("expenses", False)),
            Expense.expense_date >= selected_month_start,
            Expense.expense_date < selected_next_month_start,
            func.lower(Expense.payment_method) == "cash",
        )
        .one()
    )

    month_expense_upi_row = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            and_(Expense.company_id == company_id, company_features.get("expenses", False)),
            Expense.expense_date >= selected_month_start,
            Expense.expense_date < selected_next_month_start,
            func.lower(Expense.payment_method) == "upi",
        )
        .one()
    )

    month_expense = money(month_expense_row[0])
    month_expense_cash = money(month_expense_cash_row[0])
    month_expense_upi = money(month_expense_upi_row[0])

    category_rows = (
        db.query(
            Expense.category,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(and_(Expense.company_id == company_id, company_features.get("expenses", False)))
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    categories = [
        {
            "category": category or "Other",
            "amount": money(amount),
        }
        for category, amount in category_rows
    ]

    return {
        "total": total_expense,
        "this_month": month_expense,
        "cash": expense_cash,
        "upi": expense_upi,
        "this_month_cash": month_expense_cash,
        "this_month_upi": month_expense_upi,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "selected_period_total": month_expense,
        "categories": categories,
    }

# UPCOMING AUCTIONS

# =========================================================



def get_upcoming_auctions(

    db: Session,

    company_id: int,

):

    """

    Upcoming chit auction/lift slots.



    A ChitMonth is considered upcoming when:

        - chit is active

        - month date is today/future

        - no ChitLift exists for that month

    """



    rows = (

        db.query(

            ChitMonth,

            ChitGroup,

        )

        .join(

            ChitGroup,

            ChitGroup.id == ChitMonth.chit_id,

        )

        .outerjoin(

            ChitLift,

            ChitLift.chit_month_id == ChitMonth.id,

        )

        .filter(

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMonth.month_date >= date.today(),

            ChitLift.id.is_(None),

        )

        .order_by(

            ChitMonth.month_date.asc(),

        )

        .limit(5)

        .all()

    )



    result = []



    for month, chit in rows:



        result.append(

            {

                "chit_id":

                    chit.id,



                "chit_name":

                    chit.name,



                "chit_code":

                    chit.code,



                "chit_month_id":

                    month.id,



                "month_number":

                    month.month_number,



                "auction_date":

                    month.month_date,



                "planned_lift_amount":

                    money(

                        month.monthly_lift_amount

                    ),

            }

        )



    return result





# =========================================================

# DASHBOARD

# =========================================================



def get_dashboard(
    db: Session,
    company_id: int,
    year: int | None = None,
    expense_month: int | None = None,
):

    today = date.today()

    available_years = get_available_dashboard_years(
        db=db,
        company_id=company_id,
    )

    selected_year = year if year is not None else today.year

    if selected_year not in available_years:
        selected_year = today.year

    selected_expense_month = (
        expense_month if expense_month is not None else today.month
    )

    if selected_expense_month < 1 or selected_expense_month > 12:
        selected_expense_month = today.month

    month_start, next_month_start = get_month_range(today)

    year_start, next_year_start = get_year_range(today)

    selected_year_start, selected_year_end = get_year_range(
        date(selected_year, 1, 1)
    )

    # =====================================================
    # ACTIVE CHITS
    # =====================================================



    active_chits = (

        db.query(ChitGroup)

        .filter(

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

        )

        .order_by(

            ChitGroup.id.asc()

        )

        .all()

    )



    # =====================================================

    # ACTIVE MEMBERS

    # =====================================================



    active_member_count = (

        db.query(

            func.count(ChitMember.id)

        )

        .join(

            ChitGroup,

            ChitGroup.id == ChitMember.chit_id,

        )

        .filter(

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMember.status.in_(

                [

                    "confirmed",

                    "active",

                ]

            ),

        )

        .scalar()

        or 0

    )



    # =====================================================

    # TOTAL CUSTOMERS

    # =====================================================



    total_customers = (

        db.query(

            func.count(CustomerProfile.id)

        )

        .filter(

            CustomerProfile.company_id == company_id,

            CustomerProfile.status == "active",

        )

        .scalar()

        or 0

    )



    # =====================================================

    # ACTIVE INSTALLMENTS

    # =====================================================



    installment_rows = (

        db.query(

            ChitInstallment,

            ChitMember,

            ChitGroup,

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

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMember.status.in_(

                [

                    "confirmed",

                    "active",

                ]

            ),

        )

        .all()

    )



    # =====================================================

    # INSTALLMENT PAYMENT CACHE

    # =====================================================



    installment_ids = [

        installment.id

        for installment, _, _

        in installment_rows

    ]



    paid_by_installment = {}



    if installment_ids:



        payment_totals = (

            db.query(

                PaymentTransaction.installment_id,

                func.coalesce(

                    func.sum(

                        PaymentTransaction.amount

                    ),

                    0,

                ),

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



        paid_by_installment = {

            installment_id:

                money(paid_amount)



            for installment_id, paid_amount

            in payment_totals

        }



    # =====================================================

    # OVERALL FINANCIAL SUMMARY

    # =====================================================



    total_due = Decimal("0")

    total_paid = Decimal("0")



    paid_installments = 0

    partial_installments = 0

    pending_installments = 0



    overdue_count = 0

    overdue_amount = Decimal("0")



    due_this_month_count = 0

    due_this_month_amount = Decimal("0")



    for installment, member, chit in installment_rows:



        due_amount = money(

            installment.due_amount

        )



        paid_amount = money(

            paid_by_installment.get(

                installment.id,

                0,

            )

        )



        outstanding = max(

            due_amount - paid_amount,

            Decimal("0"),

        )



        total_due += due_amount



        total_paid += min(

            paid_amount,

            due_amount,

        )



        # -------------------------------------------------

        # PAYMENT STATUS

        # -------------------------------------------------



        if (

            paid_amount >= due_amount

            and due_amount > 0

        ):



            paid_installments += 1



        elif paid_amount > 0:



            partial_installments += 1



        else:



            pending_installments += 1



        # -------------------------------------------------

        # OVERDUE

        # -------------------------------------------------



        if (

            installment.due_date

            and installment.due_date < today

            and outstanding > 0

        ):



            overdue_count += 1



            overdue_amount += outstanding



        # -------------------------------------------------

        # DUE THIS MONTH

        # -------------------------------------------------



        if (

            installment.due_date

            and month_start

            <= installment.due_date

            < next_month_start

            and outstanding > 0

        ):



            due_this_month_count += 1



            due_this_month_amount += outstanding



    total_outstanding = max(

        total_due - total_paid,

        Decimal("0"),

    )



    collection_rate = (

        (

            total_paid

            / total_due

        )

        * 100

        if total_due > 0

        else Decimal("0")

    )



    # =====================================================

    # MONTHLY PAYMENTS

    # =====================================================



    monthly_payment_rows = (

        db.query(

            PaymentTransaction,

            ChitInstallment,

            ChitMember,

            ChitGroup,

        )

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

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMember.status.in_(

                [

                    "confirmed",

                    "active",

                ]

            ),

            PaymentTransaction.payment_date

            >= month_start,

            PaymentTransaction.payment_date

            < next_month_start,

        )

        .all()

    )



    # =====================================================

    # COLLECTIONS

    # =====================================================



    today_collection = Decimal("0")



    today_upi = Decimal("0")

    today_cash = Decimal("0")

    today_bank = Decimal("0")

    today_cheque = Decimal("0")

    today_other = Decimal("0")



    month_collection = Decimal("0")



    month_upi = Decimal("0")

    month_cash = Decimal("0")

    month_bank = Decimal("0")

    month_cheque = Decimal("0")

    month_other = Decimal("0")



    for payment, installment, member, chit in monthly_payment_rows:



        amount = money(

            payment.amount

        )



        month_collection += amount



        payment_method = (

            payment.payment_method or ""

        ).strip().lower()



        # -------------------------------------------------

        # MONTH PAYMENT METHOD

        # -------------------------------------------------



        if payment_method == "upi":



            month_upi += amount



        elif payment_method == "cash":



            month_cash += amount



        elif payment_method == "bank_transfer":



            month_bank += amount



        elif payment_method == "cheque":



            month_cheque += amount



        else:



            month_other += amount



        # -------------------------------------------------

        # TODAY

        # -------------------------------------------------



        payment_date = payment.payment_date



        if isinstance(

            payment_date,

            str,

        ):



            try:



                payment_date = date.fromisoformat(

                    payment_date

                )



            except ValueError:



                payment_date = None



        if payment_date == today:



            today_collection += amount



            if payment_method == "upi":



                today_upi += amount



            elif payment_method == "cash":



                today_cash += amount



            elif payment_method == "bank_transfer":



                today_bank += amount



            elif payment_method == "cheque":



                today_cheque += amount



            else:



                today_other += amount



    # =====================================================
    # SELECTED-YEAR MONTHLY COLLECTION VS OUTSTANDING DUE
    # =====================================================
    #
    # LOGIC:
    #
    # 1. Only this company's ACTIVE chits.
    # 2. Only ACTIVE / CONFIRMED chit members.
    # 3. Month is decided by ChitInstallment.due_date.
    # 4. PaymentTransaction.payment_date does NOT decide
    #    the graph month.
    #
    # Example:
    #   Sep installment paid in Oct
    #       -> September collection increases
    #       -> September outstanding due decreases
    #
    # Collection:
    #   Total payment applied against installments
    #   belonging to that month.
    #
    # Due:
    #   Remaining outstanding amount of installments
    #   belonging to that month.
    #
    # Future months of the current year are not counted yet.
    # =====================================================


    # -----------------------------------------------------
    # PAYMENT TOTAL PER INSTALLMENT
    #
    # IMPORTANT:
    # No payment_date filtering here.
    #
    # A September installment paid in October must still
    # be applied against the September installment.
    # -----------------------------------------------------

    payment_totals_subquery = (
        db.query(
            PaymentTransaction.installment_id.label(
                "installment_id"
            ),
            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            ).label(
                "paid_amount"
            ),
        )
        .group_by(
            PaymentTransaction.installment_id
        )
        .subquery()
    )


    # -----------------------------------------------------
    # ALL INSTALLMENTS FOR:
    #
    # - current company
    # - active chits
    # - active / confirmed members
    # - selected dashboard year
    #
    # outerjoin is IMPORTANT because unpaid installments
    # do not have PaymentTransaction rows.
    # -----------------------------------------------------

    monthly_installment_rows = (
        db.query(
            ChitInstallment.id.label(
                "installment_id"
            ),

            ChitInstallment.due_date.label(
                "due_date"
            ),

            ChitInstallment.due_amount.label(
                "due_amount"
            ),

            func.coalesce(
                payment_totals_subquery.c.paid_amount,
                0,
            ).label(
                "paid_amount"
            ),
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
        .outerjoin(
            payment_totals_subquery,
            payment_totals_subquery.c.installment_id
            == ChitInstallment.id,
        )
        .filter(
            ChitGroup.company_id
            == company_id,

            ChitGroup.status
            == "active",

            ChitMember.status.in_(
                [
                    "confirmed",
                    "active",
                ]
            ),

            ChitInstallment.due_date
            >= selected_year_start,

            ChitInstallment.due_date
            < selected_year_end,
        )
        .order_by(
            ChitInstallment.due_date.asc(),
            ChitInstallment.id.asc(),
        )
        .all()
    )


    # =====================================================
    # MONTH BUCKETS
    # =====================================================

    monthly_collection = {
        month: Decimal("0")
        for month in range(1, 13)
    }


    monthly_due = {
        month: Decimal("0")
        for month in range(1, 13)
    }


    # =====================================================
    # CALCULATE MONTH-WISE PERFORMANCE
    # =====================================================

    for row in monthly_installment_rows:

        due_date = row.due_date

        if not due_date:
            continue

        if isinstance(due_date, str):
            try:
                due_date = date.fromisoformat(due_date)
            except ValueError:
                continue

        # if (
        #     selected_year == today.year
        #     and due_date.month > today.month
        # ):
        #     continue

        due_amount = money(
            row.due_amount
        )

        paid_amount = money(
            row.paid_amount
        )

        applied_amount = min(
            paid_amount,
            due_amount,
        )

        remaining_due = max(
            due_amount - applied_amount,
            Decimal("0"),
        )

        month_number = due_date.month

        monthly_collection[
            month_number
        ] += applied_amount

        monthly_due[
            month_number
        ] += remaining_due


    # =====================================================
    # VERY IMPORTANT:
    # FROM HERE WE ARE OUTSIDE THE MONTHLY LOOP
    # =====================================================

    chit_data = []

    for chit in active_chits:

        chit_payment_rows = (
            db.query(
                PaymentTransaction.amount,
                PaymentTransaction.payment_method,
            )
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
            .filter(
                ChitMember.chit_id == chit.id,

                ChitMember.status.in_(
                    [
                        "confirmed",
                        "active",
                    ]
                ),

                PaymentTransaction.payment_date
                >= month_start,

                PaymentTransaction.payment_date
                < next_month_start,
            )
            .all()
        )

    # ... existing chit-wise logic continues here



        chit_month_collection = Decimal("0")



        chit_upi = Decimal("0")

        chit_cash = Decimal("0")

        chit_bank = Decimal("0")

        chit_cheque = Decimal("0")

        chit_other = Decimal("0")



        for amount, payment_method in chit_payment_rows:



            amount = money(amount)



            chit_month_collection += amount



            method = (

                payment_method or ""

            ).strip().lower()



            if method == "upi":



                chit_upi += amount



            elif method == "cash":



                chit_cash += amount



            elif method == "bank_transfer":



                chit_bank += amount



            elif method == "cheque":



                chit_cheque += amount



            else:



                chit_other += amount



        # -------------------------------------------------

        # CHIT DUE / PAID

        # -------------------------------------------------



        chit_due = Decimal("0")

        chit_paid = Decimal("0")



        for (

            installment,

            member,

            installment_chit,

        ) in installment_rows:



            if installment_chit.id != chit.id:

                continue



            due_amount = money(

                installment.due_amount

            )



            paid_amount = money(

                paid_by_installment.get(

                    installment.id,

                    0,

                )

            )



            chit_due += due_amount



            chit_paid += min(

                paid_amount,

                due_amount,

            )



        chit_outstanding = max(

            chit_due - chit_paid,

            Decimal("0"),

        )



        chit_collection_rate = (

            (

                chit_paid

                / chit_due

            )

            * 100

            if chit_due > 0

            else Decimal("0")

        )



        chit_data.append(

            {

                "chit_id":

                    chit.id,



                "chit_name":

                    chit.name,



                "chit_code":

                    chit.code,



                "monthly_emi":

                    money(chit.monthly_emi),



                "total_due":

                    chit_due,



                "total_paid":

                    chit_paid,



                "outstanding":

                    chit_outstanding,



                "collection_rate":

                    round(

                        chit_collection_rate,

                        2,

                    ),



                "this_month_collection":

                    chit_month_collection,



                "upi":

                    chit_upi,



                "cash":

                    chit_cash,



                "bank_transfer":

                    chit_bank,



                "cheque":

                    chit_cheque,



                "other":

                    chit_other,

            }

        )



    # =====================================================

    # RECENT PAYMENTS

    # =====================================================



    recent_rows = (

        db.query(

            PaymentTransaction,

            ChitInstallment,

            ChitMember,

            ChitGroup,

            CustomerProfile,

        )

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

        .join(

            CustomerProfile,

            CustomerProfile.id

            == ChitMember.customer_profile_id,

        )

        .filter(

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMember.status.in_(

                [

                    "confirmed",

                    "active",

                ]

            ),

        )

        .order_by(

            PaymentTransaction.payment_date.desc(),

            PaymentTransaction.id.desc(),

        )

        .limit(5)

        .all()

    )



    recent_payments = []



    for (

        payment,

        installment,

        member,

        chit,

        customer,

    ) in recent_rows:



        recent_payments.append(

            {

                "payment_id":

                    payment.id,



                "customer_id":

                    customer.id,



                "customer_name":

                    customer.display_name,



                "customer_code":

                    customer.customer_code,



                "chit_id":

                    chit.id,



                "chit_name":

                    chit.name,



                "chit_code":

                    chit.code,



                "member_id":

                    member.id,



                "member_number":

                    member.member_number,



                "installment_number":

                    installment.installment_number,



                "amount":

                    money(payment.amount),



                "payment_method":

                    payment.payment_method,



                "payment_date":

                    payment.payment_date,



                "reference_number":

                    payment.reference_number,

            }

        )



    # =====================================================

    # LOANS

    # =====================================================



    loan_summary = get_loan_summary(

        db=db,

        company_id=company_id,

    )



    loan_cash_flow = get_loan_cash_flow(

        db=db,

        company_id=company_id,

    )



    # =====================================================

    # ADD LOAN CASH / UPI BREAKDOWN

    # =====================================================



    loan_summary.update({

        "given_cash":

            loan_cash_flow["loan_given_cash"],



        "given_upi":

            loan_cash_flow["loan_given_upi"],



        "repayment_cash":

            loan_cash_flow["loan_repayment_cash"],



        "repayment_upi":

            loan_cash_flow["loan_repayment_upi"],

    })



    # =====================================================

    # EXPENSES

    # =====================================================



    expense_summary = get_expense_summary(
        db=db,
        company_id=company_id,
        selected_year=selected_year,
        selected_month=selected_expense_month,
    )



    # =====================================================

    # COMPANY CASH / BANK CLOSING BALANCE

    # =====================================================



    company_cash_bank = get_company_cash_bank_ledger(

        db=db,

        company_id=company_id,

    )



    # Keep the existing cash response fields for frontend compatibility.

    cash_closing_balance = money(company_cash_bank["cash"])

    bank_upi_closing_balance = money(company_cash_bank["bank"])

    total_cash_bank_balance = money(company_cash_bank["total"])



    # =====================================================

    # UPCOMING AUCTIONS

    # =====================================================



    upcoming_auctions = get_upcoming_auctions(

        db=db,

        company_id=company_id,

    )





    # =====================================================

    # =====================================================

    # TOTAL CASH COLLECTION

    # =====================================================


    cash_collected_total = (

        db.query(
            func.coalesce(
                func.sum(PaymentTransaction.amount),
                0,
            )
        )

        .join(
            ChitInstallment,
            ChitInstallment.id == PaymentTransaction.installment_id,
        )

        .join(
            ChitMember,
            ChitMember.id == ChitInstallment.chit_member_id,
        )

        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )

        .filter(
            ChitGroup.company_id == company_id,
            ChitGroup.status == "active",
            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
            func.lower(
                PaymentTransaction.payment_method
            ) == "cash",
        )

        .scalar()
        or 0
    )


    cash_collected_total = money(
        cash_collected_total
    )


    # =====================================================

    # TOTAL BANK / UPI COLLECTION

    # =====================================================



    bank_upi_collected_total = (

        db.query(

            func.coalesce(

                func.sum(PaymentTransaction.amount),

                0,

            )

        )

        .join(

            ChitInstallment,

            ChitInstallment.id == PaymentTransaction.installment_id,

        )

        .join(

            ChitMember,

            ChitMember.id == ChitInstallment.chit_member_id,

        )

        .join(

            ChitGroup,

            ChitGroup.id == ChitMember.chit_id,

        )

        .filter(

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMember.status.in_([

                "confirmed",

                "active",

            ]),

            func.lower(

                PaymentTransaction.payment_method

            ).in_([

                "upi",

                "bank_transfer",

            ]),

        )

        .scalar()

        or 0

    )



    bank_upi_collected_total = money(

        bank_upi_collected_total

    )







    # =====================================================

    # OPERATIONAL BALANCE

    # =====================================================



    operational_balance = (

        total_paid

        + loan_cash_flow["loan_repayments"]

        - loan_cash_flow["loan_given"]

        - expense_summary["total"]

    )



    # =====================================================

    # PAYMENT STATUS

    # =====================================================



    total_installments = (

        paid_installments

        + partial_installments

        + pending_installments

    )



    # =====================================================

    # RESPONSE

    # =====================================================



    return {

    # =================================================
    # DASHBOARD PERIOD
    # =================================================

    "available_years": available_years,
    "selected_year": selected_year,
    "selected_expense_month": selected_expense_month,



        # =================================================

        # OVERVIEW

        # =================================================



        "overview": {



            "active_chits":

                len(active_chits),



            "total_customers":

                int(total_customers),



            "active_members":

                int(active_member_count),



            "today_collection":

                today_collection,



            "this_month_collection":

                month_collection,



            "total_due":

                total_due,



            "total_paid":

                total_paid,



            "total_outstanding":

                total_outstanding,



            "collection_rate":

                round(

                    collection_rate,

                    2,

                ),

        },



        # =================================================

        # TODAY COLLECTION

        # =================================================



        "today_collection": {



            "total":

                today_collection,



            "upi":

                today_upi,



            "cash":

                today_cash,



            "bank_transfer":

                today_bank,



            "cheque":

                today_cheque,



            "other":

                today_other,

        },



        # =================================================

        # THIS MONTH COLLECTION

        # =================================================



        "this_month_collection": {



            "total":

                month_collection,



            "upi":

                month_upi,



            "cash":

                month_cash,



            "bank_transfer":

                month_bank,



            "cheque":

                month_cheque,



            "other":

                month_other,

        },



        # =================================================

        # PAYMENT STATUS

        # =================================================



        "payment_status": {



            "total":

                total_installments,



            "paid":

                paid_installments,



            "partial":

                partial_installments,



            "pending":

                pending_installments,

        },



        # =================================================

        # DUES

        # =================================================



        "dues": {



            "overdue_count":

                overdue_count,



            "overdue_amount":

                overdue_amount,



            "due_this_month_count":

                due_this_month_count,



            "due_this_month_amount":

                due_this_month_amount,

        },

        "cash_bank": {

            "cash": money(

                company_cash_bank["cash"]

            ),



            "bank": money(

                company_cash_bank["bank"]

            ),



            "total": money(

                company_cash_bank["total"]

            ),

        },







        # =================================================

        # CASH

        # =================================================



        "cash": {

            "cash_collected_today": today_cash,

            "cash_collected_this_month": month_cash,

            "cash_collected_total": cash_collected_total,

            "upi_collected_total": bank_upi_collected_total,



            # Actual closing balances

            "cash_closing_balance": cash_closing_balance,

            "bank_upi_closing_balance": bank_upi_closing_balance,

            "total_cash_bank_balance": total_cash_bank_balance,

        },



        # =================================================

        # LOANS

        # =================================================



        "loans": loan_summary,



        # =================================================

        # EXPENSES

        # =================================================



        "expenses": expense_summary,



        # =================================================

        # BALANCE

        # =================================================



        "balance": {



            "collections":

                total_paid,



            "loan_given":

                loan_cash_flow["loan_given"],



            "loan_repayments":

                loan_cash_flow["loan_repayments"],



            "expenses":

                expense_summary["total"],



            "available_balance":

                operational_balance,

        },



        # =================================================

        # UPCOMING AUCTIONS

        # =================================================



        "upcoming_auctions":

            upcoming_auctions,



        # =================================================

        # MONTHLY CHART

        # =================================================



        "monthly_chart": [
            {
                "month": month,

                "collection":
                    monthly_collection[month],

                "due":
                    monthly_due[month],
            }

            for month in range(1, 13)
        ],

        # CHIT WISE

        # =================================================
        "chit_wise":

            chit_data,
        # =================================================

        # RECENT PAYMENTS

        # =================================================
        "recent_payments":

            recent_payments,

    }
