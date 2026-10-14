from __future__ import annotations

import base64
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image as ReportLabImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.utils import ImageReader
from sqlalchemy.orm import Session

from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_months import ChitMonth
from app.models.admin.chitlift import ChitLift
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.payment_transaction import PaymentTransaction


# =========================================================
# CONSTANTS
# =========================================================

ACTIVE_MEMBER_STATUSES = ("confirmed", "active", "completed")

MAX_LOGO_BYTES = 2 * 1024 * 1024

NAVY = colors.HexColor("#0b1328")
NAVY_LIGHT = colors.HexColor("#14203d")
GOLD = colors.HexColor("#d4af63")
GOLD_LIGHT = colors.HexColor("#e8cf91")
TEXT = colors.HexColor("#1c2433")
TEXT_MUTED = colors.HexColor("#667085")
BORDER = colors.HexColor("#d9dee8")
WHITE = colors.white
ROW_ALT = colors.HexColor("#f8f6f0")
SUCCESS = colors.HexColor("#117a58")


# =========================================================
# SMALL HELPERS
# =========================================================


def _money(value: Decimal | int | float | None) -> str:
    amount = Decimal(str(value or 0))
    return f"Rs. {amount:,.2f}"


def _short_money(value: Decimal | int | float | None) -> str:
    amount = Decimal(str(value or 0))
    return f"Rs. {amount:,.0f}"


def _display_date(value: date | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d %b %Y")


def _display_method(value: str | None) -> str:
    if not value:
        return "—"
    normalized = value.strip().lower()
    mapping = {
        "upi": "UPI",
        "cash": "Cash",
        "bank": "Bank",
        "bank transfer": "Bank Transfer",
        "bank_transfer": "Bank Transfer",
        "cheque": "Cheque",
        "check": "Cheque",
        "card": "Card",
    }
    return mapping.get(normalized, value.strip().title())


def _safe_filename_component(value: str | int | None) -> str:
    text = str(value or "").strip()
    cleaned = "".join(
        char if char.isalnum() or char in "-_" else "-"
        for char in text
    )
    return cleaned.strip("-") or "receipt"


def _safe_html(text: str | int | Decimal | None) -> str:
    from xml.sax.saxutils import escape

    return escape(str(text or "—"))


# =========================================================
# LOGO LOADING
# =========================================================


def _load_logo_bytes(logo_url: str | None) -> bytes | None:
    """
    Loads the company logo from either:
    - an absolute http/https URL, or
    - the application's local uploads folder.

    The database stores company.logo_url, so this helper keeps the
    receipt generator independent of how the company logo was stored.
    """

    if not logo_url:
        return None

    value = logo_url.strip()
    if not value:
        return None

    # -----------------------------------------------------
    # Remote logo URL
    # -----------------------------------------------------

    if value.startswith(("http://", "https://")):
        try:
            request = Request(
                value,
                headers={
                    "User-Agent": "SA-Chits-Receipt/1.0",
                },
            )
            with urlopen(request, timeout=5) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_LOGO_BYTES:
                    return None

                data = response.read(MAX_LOGO_BYTES + 1)
                if len(data) > MAX_LOGO_BYTES:
                    return None
                return data
        except Exception:
            return None

    # -----------------------------------------------------
    # Local uploads path
    # -----------------------------------------------------

    relative = value.replace("\\", "/")

    if relative.startswith("/uploads/"):
        relative = relative[len("/uploads/") :]
    elif relative.startswith("uploads/"):
        relative = relative[len("uploads/") :]
    elif relative.startswith("/"):
        relative = relative.lstrip("/")

    uploads_root = Path("uploads").resolve()
    candidate = (uploads_root / relative).resolve()

    try:
        candidate.relative_to(uploads_root)
    except ValueError:
        return None

    if not candidate.is_file():
        return None

    try:
        if candidate.stat().st_size > MAX_LOGO_BYTES:
            return None
        return candidate.read_bytes()
    except OSError:
        return None

# =========================================================
# LOGO DATA URL
# =========================================================

def _logo_to_data_url(
    logo_url: str | None,
) -> str | None:
    """
    Convert company logo into an inline data URL.

    Browser direct-ga logo server/CDN ni request cheyyadu.
    So html2canvas ki CORS problem undadu.
    """

    logo_bytes = _load_logo_bytes(logo_url)

    if not logo_bytes:
        return None

    try:
        image = Image.open(BytesIO(logo_bytes))

        image_format = (
            image.format or "PNG"
        ).upper()

        mime_map = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "WEBP": "image/webp",
            "GIF": "image/gif",
        }

        mime_type = mime_map.get(
            image_format,
            "image/png",
        )

        encoded = base64.b64encode(
            logo_bytes
        ).decode("ascii")

        return (
            f"data:{mime_type};base64,{encoded}"
        )

    except Exception:
        return None
    
    
    
# =========================================================
# QUERY / DATA BUILD
# =========================================================


def get_customer_receipt_data(
    db: Session,
    customer_mobile: str,
    chit_member_id: int,
) -> dict[str, Any] | None:
    """
    Fetch one exact chit slot and all payment data for that slot.

    Authorization is based on the authenticated customer's mobile
    number + the exact ChitMember.id. This is important because a
    customer may have different CustomerProfile rows in different
    companies while using the same login mobile number.
    """

    mobile = customer_mobile.strip()
    if not mobile:
        return None

    # -----------------------------------------------------
    # EXACT CUSTOMER + COMPANY + CHIT SLOT
    # -----------------------------------------------------

    row = (
        db.query(
            ChitMember,
            CustomerProfile,
            ChitGroup,
            Company,
        )
        .join(
            CustomerProfile,
            CustomerProfile.id == ChitMember.customer_profile_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .join(
            Company,
            Company.id == ChitGroup.company_id,
        )
        .filter(
            ChitMember.id == chit_member_id,
            ChitMember.status.in_(ACTIVE_MEMBER_STATUSES),
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
        )
        .first()
    )

    if not row:
        return None

    member, customer, chit, company = row

    # -----------------------------------------------------
    # INSTALLMENTS
    # -----------------------------------------------------

    installments = (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.chit_member_id == member.id,
        )
        .order_by(
            ChitInstallment.installment_number.asc(),
            ChitInstallment.id.asc(),
        )
        .all()
    )

    installment_ids = [item.id for item in installments]

    # -----------------------------------------------------
    # PAYMENTS FOR THIS EXACT SLOT
    # -----------------------------------------------------

    payments_by_installment: dict[int, list[PaymentTransaction]] = defaultdict(list)

    if installment_ids:
        payment_rows = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.installment_id.in_(installment_ids),
            )
            .order_by(
                PaymentTransaction.payment_date.asc(),
                PaymentTransaction.id.asc(),
            )
            .all()
        )

        for payment in payment_rows:
            payments_by_installment[payment.installment_id].append(payment)

    # -----------------------------------------------------
    # INSTALLMENT SUMMARIES
    # -----------------------------------------------------

    installment_items: list[dict[str, Any]] = []
    payment_items: list[dict[str, Any]] = []

    total_due = Decimal("0")
    total_paid = Decimal("0")
    paid_installments = 0
    partial_installments = 0

    for installment in installments:
        due_amount = Decimal(str(installment.due_amount or 0))
        installment_payments = payments_by_installment.get(
            installment.id,
            [],
        )
        paid_amount = sum(
            (Decimal(str(payment.amount or 0)) for payment in installment_payments),
            Decimal("0"),
        )
        balance_amount = max(
            due_amount - paid_amount,
            Decimal("0"),
        )

        total_due += due_amount
        total_paid += paid_amount

        if due_amount > 0 and paid_amount >= due_amount:
            paid_installments += 1
            installment_status = "Paid"
        elif paid_amount > 0:
            partial_installments += 1
            installment_status = "Partial"
        else:
            installment_status = "Pending"

        installment_items.append(
            {
                "installment_id": installment.id,
                "installment_number": int(installment.installment_number),
                "due_date": installment.due_date,
                "due_amount": due_amount,
                "paid_amount": paid_amount,
                "balance_amount": balance_amount,
                "status": installment_status,
            }
        )

        # -------------------------------------------------
        # PAYMENT TRANSACTION ROWS
        #
        # Only installments with an actual payment are shown
        # in the customer receipt history.
        # -------------------------------------------------

        for payment in installment_payments:
            payment_amount = Decimal(str(payment.amount or 0))
            payment_items.append(
                {
                    "payment_id": payment.id,
                    "installment_id": installment.id,
                    "installment_number": int(installment.installment_number),
                    "due_date": installment.due_date,
                    "payment_date": payment.payment_date,
                    "amount": payment_amount,
                    "payment_method": payment.payment_method,
                    "reference_number": payment.reference_number,
                    "notes": payment.notes,
                }
            )

    # -----------------------------------------------------
    # OPTIONAL LIFT DETAILS
    # -----------------------------------------------------

    lift_row = (
        db.query(ChitLift, ChitMonth)
        .outerjoin(
            ChitMonth,
            ChitMonth.id == ChitLift.chit_month_id,
        )
        .filter(
            ChitLift.chit_member_id == member.id,
        )
        .order_by(
            ChitLift.id.desc(),
        )
        .first()
    )

    lift_details = None
    if lift_row:
        lift, month = lift_row
        lift_details = {
            "lift_id": lift.id,
            "month_number": (
                month.month_number
                if month
                else lift.cycle_number
            ),
            "month_date": month.month_date if month else None,
            "lift_date": lift.lift_date,
            "monthly_lift_amount": (
                month.monthly_lift_amount
                if month
                else Decimal("0")
            ),
            "discount_amount": Decimal(str(lift.discount_amount or 0)),
            "lifted_amount": Decimal(str(lift.lifted_amount or 0)),
            "payout_status": lift.payout_status,
            "payout_date": lift.payout_date,
        }

    pending_amount = max(
        total_due - total_paid,
        Decimal("0"),
    )

    paid_months_with_activity = sum(
        1
        for item in installment_items
        if item["paid_amount"] > 0
    )

    return {
        "company": {
            "id": company.id,
            "name": company.company_name,
            "logo_url": company.logo_url,
            "email": company.email,
            "mobile": company.mobile,
            "address": company.address,
            "logo_data_url": _logo_to_data_url(company.logo_url),
        },
        "customer": {
            "id": customer.id,
            "code": customer.customer_code,
            "name": customer.display_name,
            "legal_name": customer.legal_name,
            "mobile": customer.mobile,
            "email": customer.email,
            "address": customer.address,
        },
        "chit": {
            "id": chit.id,
            "name": chit.name,
            "code": chit.code,
            "value": Decimal(str(chit.chit_value or 0)),
            "monthly_emi": Decimal(str(chit.monthly_emi or 0)),
            "duration_months": int(chit.duration_months or 0),
            "start_date": chit.start_date,
            "status": chit.status,
        },
        "member": {
            "id": member.id,
            "member_number": int(member.member_number),
            "slot_number": member.slot_number,
            "member_name": member.member_name,
            "status": member.status,
            "joined_at": member.joined_at,
        },
        "summary": {
            "total_installments": len(installments),
            "paid_installments": paid_installments,
            "partial_installments": partial_installments,
            "paid_months_with_activity": paid_months_with_activity,
            "total_due": total_due,
            "total_paid": total_paid,
            "pending_amount": pending_amount,
        },
        "installments": installment_items,
        "payments": payment_items,
        "lift": lift_details,
    }


# =========================================================
# PIL FONTS
# =========================================================


def _find_font(bold: bool = False, size: int = 24) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    )

    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue

    return ImageFont.load_default()


# =========================================================
# JPG GENERATION
# =========================================================


def generate_receipt_jpg(data: dict[str, Any]) -> bytes:
    """Create a single long JPG receipt/statement for one chit slot."""

    width = 1400
    padding = 70
    content_width = width - (padding * 2)

    font_title = _find_font(True, 38)
    font_company = _find_font(True, 32)
    font_section = _find_font(True, 24)
    font_body = _find_font(False, 22)
    font_body_bold = _find_font(True, 22)
    font_small = _find_font(False, 19)
    font_small_bold = _find_font(True, 19)

    line_height = 34

    company = data["company"]
    customer = data["customer"]
    chit = data["chit"]
    member = data["member"]
    summary = data["summary"]

    payments = data["payments"]

    # Rough height calculation.
    height = 640
    height += 200
    height += 280
    height += max(1, len(payments)) * 55
    if data.get("lift"):
        height += 180
    height += 220

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    header_height = 185
    draw.rectangle(
        (0, 0, width, header_height),
        fill="#0b1328",
    )

    logo_bytes = _load_logo_bytes(company.get("logo_url"))
    logo_rendered = False

    if logo_bytes:
        try:
            logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
            logo.thumbnail((115, 115))
            image.alpha_composite if hasattr(image, "alpha_composite") else None
            # Draw a white logo card for transparent/colored logos.
            card_x = padding
            card_y = 35
            card_size = 115
            draw.rounded_rectangle(
                (card_x, card_y, card_x + card_size, card_y + card_size),
                radius=18,
                fill="#ffffff",
            )
            image.paste(
                logo,
                (
                    card_x + (card_size - logo.width) // 2,
                    card_y + (card_size - logo.height) // 2,
                ),
                logo,
            )
            logo_rendered = True
        except Exception:
            logo_rendered = False

    company_x = padding + 145 if logo_rendered else padding
    draw.text(
        (company_x, 36),
        str(company["name"] or "Company"),
        font=font_company,
        fill="#e8cf91",
    )

    company_lines = [
        company.get("address") or "",
        company.get("mobile") or "",
        company.get("email") or "",
    ]
    y = 82
    for line in company_lines:
        if line:
            draw.text(
                (company_x, y),
                str(line),
                font=font_small,
                fill="#ffffff",
            )
            y += 29

    draw.text(
        (width - padding, 45),
        "PAYMENT RECEIPT",
        font=font_title,
        fill="#ffffff",
        anchor="ra",
    )
    draw.text(
        (width - padding, 95),
        "Consolidated statement for one chit slot",
        font=font_small,
        fill="#d6dae4",
        anchor="ra",
    )

    y = header_height + 38

    # -----------------------------------------------------
    # Customer + Chit cards
    # -----------------------------------------------------

    def card(x1: int, y1: int, x2: int, y2: int, title: str) -> int:
        draw.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=18,
            outline="#d9dee8",
            width=2,
            fill="#fbfbfc",
        )
        draw.rectangle(
            (x1, y1, x2, y1 + 52),
            fill="#f7f1e3",
        )
        draw.text(
            (x1 + 20, y1 + 14),
            title,
            font=font_section,
            fill="#0b1328",
        )
        return y1 + 72

    card_gap = 25
    card_width = (content_width - card_gap) // 2
    left_x = padding
    right_x = padding + card_width + card_gap
    card_y = y
    card_h = 300

    left_text_y = card(left_x, card_y, left_x + card_width, card_y + card_h, "CUSTOMER DETAILS")
    customer_pairs = [
        ("Name", customer.get("name")),
        ("Customer Code", customer.get("code")),
        ("Mobile", customer.get("mobile")),
        ("Email", customer.get("email") or "—"),
        ("Address", customer.get("address") or "—"),
    ]

    for label, value in customer_pairs:
        draw.text((left_x + 20, left_text_y), label, font=font_small_bold, fill="#667085")
        draw.text((left_x + 185, left_text_y), str(value or "—"), font=font_small, fill="#1c2433")
        left_text_y += 43

    right_text_y = card(right_x, card_y, right_x + card_width, card_y + card_h, "CHIT DETAILS")
    chit_pairs = [
        ("Chit", chit.get("name")),
        ("Chit Code", chit.get("code")),
        ("Member No.", member.get("member_number")),
        ("Slot No.", member.get("slot_number") or "—"),
        ("Chit Value", _short_money(chit.get("value"))),
        ("Monthly EMI", _short_money(chit.get("monthly_emi"))),
        ("Start Date", _display_date(chit.get("start_date"))),
    ]

    for label, value in chit_pairs:
        draw.text((right_x + 20, right_text_y), label, font=font_small_bold, fill="#667085")
        draw.text((right_x + 185, right_text_y), str(value or "—"), font=font_small, fill="#1c2433")
        right_text_y += 36

    y = card_y + card_h + 35

    # -----------------------------------------------------
    # Summary cards
    # -----------------------------------------------------

    summary_items = [
        ("Total Paid", _money(summary["total_paid"])),
        ("Paid Installments", str(summary["paid_installments"])),
        ("Partial Installments", str(summary["partial_installments"])),
        ("Pending Balance", _money(summary["pending_amount"])),
    ]

    box_gap = 18
    box_width = (content_width - (box_gap * 3)) // 4
    for index, (label, value) in enumerate(summary_items):
        x = padding + index * (box_width + box_gap)
        draw.rounded_rectangle(
            (x, y, x + box_width, y + 125),
            radius=18,
            fill="#0b1328" if index in (0, 3) else "#f7f1e3",
        )
        fill = "#e8cf91" if index in (0, 3) else "#0b1328"
        draw.text((x + 18, y + 18), label, font=font_small_bold, fill=fill)
        draw.text((x + 18, y + 58), value, font=font_body_bold, fill="#ffffff" if index in (0, 3) else "#1c2433")

    y += 160

    # -----------------------------------------------------
    # Payment history
    # -----------------------------------------------------

    draw.text((padding, y), "PAYMENT HISTORY", font=font_section, fill="#0b1328")
    y += 50

    columns = [
        ("Month", 100),
        ("Due Date", 150),
        ("Paid Date", 160),
        ("Amount", 180),
        ("Method", 170),
        ("Reference", 300),
    ]
    x_positions = [padding]
    for _, col_w in columns[:-1]:
        x_positions.append(x_positions[-1] + col_w)

    table_top = y
    row_h = 48

    draw.rectangle(
        (padding, table_top, padding + content_width, table_top + row_h),
        fill="#0b1328",
    )

    for idx, (label, _) in enumerate(columns):
        draw.text(
            (x_positions[idx] + 10, table_top + 13),
            label,
            font=font_small_bold,
            fill="#ffffff",
        )

    y += row_h

    for row_index, payment in enumerate(payments):
        fill = "#ffffff" if row_index % 2 == 0 else "#f8f6f0"
        draw.rectangle(
            (padding, y, padding + content_width, y + row_h),
            fill=fill,
            outline="#e1e5eb",
        )

        values = [
            f"#{payment['installment_number']}",
            _display_date(payment["due_date"]),
            _display_date(payment["payment_date"]),
            _money(payment["amount"]),
            _display_method(payment["payment_method"]),
            payment.get("reference_number") or "—",
        ]

        for idx, value in enumerate(values):
            draw.text(
                (x_positions[idx] + 10, y + 13),
                str(value),
                font=font_small,
                fill="#1c2433",
            )

        y += row_h

    if not payments:
        draw.text(
            (padding + 16, y + 12),
            "No payment transactions are available.",
            font=font_small,
            fill="#667085",
        )
        y += row_h

    y += 30

    # -----------------------------------------------------
    # Optional lift details
    # -----------------------------------------------------

    if data.get("lift"):
        lift = data["lift"]
        draw.rounded_rectangle(
            (padding, y, padding + content_width, y + 160),
            radius=18,
            fill="#fbfbfc",
            outline="#d9dee8",
            width=2,
        )
        draw.text((padding + 20, y + 18), "LIFT DETAILS", font=font_section, fill="#0b1328")

        lift_pairs = [
            ("Lift Month", lift.get("month_number") or "—"),
            ("Lift Date", _display_date(lift.get("lift_date"))),
            ("Lifted Amount", _money(lift.get("lifted_amount"))),
            ("Payout Status", str(lift.get("payout_status") or "—").title()),
            ("Payout Date", _display_date(lift.get("payout_date"))),
        ]
        lx = padding + 20
        ly = y + 65
        for label, value in lift_pairs:
            draw.text((lx, ly), label, font=font_small_bold, fill="#667085")
            draw.text((lx + 190, ly), str(value), font=font_small, fill="#1c2433")
            ly += 33

        y += 195

    # -----------------------------------------------------
    # Footer
    # -----------------------------------------------------

    footer_y = y + 10
    draw.line((padding, footer_y, padding + content_width, footer_y), fill="#d9dee8", width=2)
    footer_y += 28
    draw.text(
        (padding, footer_y),
        f"Generated on {_display_date(date.today())}",
        font=font_small,
        fill="#667085",
    )
    draw.text(
        (width - padding, footer_y),
        "System generated receipt — no signature required",
        font=font_small,
        fill="#667085",
        anchor="ra",
    )

    # Crop to actual content height.
    final_height = min(height, footer_y + 55)
    image = image.crop((0, 0, width, final_height))

    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=92,
        optimize=True,
    )
    return output.getvalue()


# =========================================================
# PDF GENERATION
# =========================================================


def _make_reportlab_logo(logo_bytes: bytes | None, max_width: float = 30 * mm, max_height: float = 30 * mm):
    if not logo_bytes:
        return None

    try:
        image_reader = ImageReader(BytesIO(logo_bytes))
        width, height = image_reader.getSize()
        if width <= 0 or height <= 0:
            return None

        scale = min(
            max_width / width,
            max_height / height,
        )

        return ReportLabImage(
            image_reader,
            width=width * scale,
            height=height * scale,
        )
    except Exception:
        return None


def generate_receipt_pdf(data: dict[str, Any]) -> bytes:
    """Create a polished A4 PDF receipt/statement for one chit slot."""

    output = BytesIO()

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="SA Chits Payment Receipt",
        author="SA Chits",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReceiptTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=WHITE,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    company_style = ParagraphStyle(
        "CompanyName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=GOLD_LIGHT,
    )
    small_white = ParagraphStyle(
        "SmallWhite",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=WHITE,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=NAVY,
        spaceBefore=5,
        spaceAfter=6,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=TEXT_MUTED,
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=TEXT,
    )
    value_bold_style = ParagraphStyle(
        "ValueBold",
        parent=value_style,
        fontName="Helvetica-Bold",
    )
    tiny_style = ParagraphStyle(
        "Tiny",
        parent=value_style,
        fontSize=7.5,
        leading=9,
    )
    right_value_style = ParagraphStyle(
        "RightValue",
        parent=value_style,
        alignment=TA_RIGHT,
    )
    right_bold_style = ParagraphStyle(
        "RightBold",
        parent=value_bold_style,
        alignment=TA_RIGHT,
    )

    company = data["company"]
    customer = data["customer"]
    chit = data["chit"]
    member = data["member"]
    summary = data["summary"]

    logo = _make_reportlab_logo(
        _load_logo_bytes(company.get("logo_url")),
        max_width=24 * mm,
        max_height=24 * mm,
    )

    company_text = [
        Paragraph(_safe_html(company["name"]), company_style),
    ]
    for value in (
        company.get("address"),
        company.get("mobile"),
        company.get("email"),
    ):
        if value:
            company_text.append(Paragraph(_safe_html(value), small_white))

    header_table = Table(
        [
            [
                logo or "",
                company_text,
                Paragraph("PAYMENT RECEIPT", title_style),
            ]
        ],
        colWidths=[28 * mm, 88 * mm, 56 * mm],
        rowHeights=[29 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ]
        )
    )

    story = [
        header_table,
        Spacer(1, 8),
        Paragraph(
            "Consolidated payment receipt for the exact customer chit slot",
            tiny_style,
        ),
        Spacer(1, 6),
    ]

    # -----------------------------------------------------
    # Customer and chit details
    # -----------------------------------------------------

    def detail_table(title: str, rows: list[tuple[str, str]]) -> Table:
        content = [[Paragraph(title, section_style), ""]]
        for label, value in rows:
            content.append(
                [
                    Paragraph(_safe_html(label), label_style),
                    Paragraph(_safe_html(value), value_style),
                ]
            )

        table = Table(
            content,
            colWidths=[34 * mm, 55 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (1, 0)),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f7f1e3")),
                    ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                    ("INNERGRID", (0, 1), (-1, -1), 0.35, colors.HexColor("#eceff3")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    customer_table = detail_table(
        "CUSTOMER DETAILS",
        [
            ("Name", str(customer.get("name") or "—")),
            ("Customer Code", str(customer.get("code") or "—")),
            ("Mobile", str(customer.get("mobile") or "—")),
            ("Email", str(customer.get("email") or "—")),
            ("Address", str(customer.get("address") or "—")),
        ],
    )

    chit_table = detail_table(
        "CHIT DETAILS",
        [
            ("Chit Name", str(chit.get("name") or "—")),
            ("Chit Code", str(chit.get("code") or "—")),
            ("Member No.", str(member.get("member_number") or "—")),
            ("Slot No.", str(member.get("slot_number") or "—")),
            ("Chit Value", _money(chit.get("value"))),
            ("Monthly EMI", _money(chit.get("monthly_emi"))),
            ("Duration", f"{chit.get('duration_months') or 0} months"),
            ("Start Date", _display_date(chit.get("start_date"))),
        ],
    )

    details_table = Table(
        [[customer_table, chit_table]],
        colWidths=[89 * mm, 89 * mm],
    )
    details_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 4),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )
    story.extend([details_table, Spacer(1, 8)])

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    summary_data = [
        [
            Paragraph("TOTAL PAID", label_style),
            Paragraph("PAID INSTALLMENTS", label_style),
            Paragraph("PARTIAL", label_style),
            Paragraph("PENDING BALANCE", label_style),
        ],
        [
            Paragraph(_money(summary["total_paid"]), value_bold_style),
            Paragraph(str(summary["paid_installments"]), value_bold_style),
            Paragraph(str(summary["partial_installments"]), value_bold_style),
            Paragraph(_money(summary["pending_amount"]), value_bold_style),
        ],
    ]
    summary_table = Table(
        summary_data,
        colWidths=[44.5 * mm] * 4,
        rowHeights=[8 * mm, 12 * mm],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfaf5")),
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 10)])

    # -----------------------------------------------------
    # Payment history
    # -----------------------------------------------------

    story.append(Paragraph("PAYMENT HISTORY", section_style))

    history_header = [
        "Month",
        "Due Date",
        "Paid Date",
        "Amount",
        "Method",
        "Reference",
    ]

    history_rows = [
        [Paragraph(_safe_html(item), small_white) for item in history_header]
    ]

    payments = data["payments"]
    for payment in payments:
        history_rows.append(
            [
                Paragraph(f"#{payment['installment_number']}", tiny_style),
                Paragraph(_display_date(payment["due_date"]), tiny_style),
                Paragraph(_display_date(payment["payment_date"]), tiny_style),
                Paragraph(_money(payment["amount"]), tiny_style),
                Paragraph(_safe_html(_display_method(payment["payment_method"])), tiny_style),
                Paragraph(_safe_html(payment.get("reference_number") or "—"), tiny_style),
            ]
        )

    if not payments:
        history_rows.append(
            [
                Paragraph("No payment transactions available.", tiny_style),
                "",
                "",
                "",
                "",
                "",
            ]
        )

    history_table = Table(
        history_rows,
        colWidths=[16 * mm, 27 * mm, 27 * mm, 29 * mm, 28 * mm, 51 * mm],
        repeatRows=1,
    )
    history_style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]

    for row_index in range(1, len(history_rows)):
        if row_index % 2 == 0:
            history_style.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), ROW_ALT)
            )

    history_table.setStyle(TableStyle(history_style))
    story.extend([history_table, Spacer(1, 10)])

    # -----------------------------------------------------
    # Optional lift
    # -----------------------------------------------------

    if data.get("lift"):
        lift = data["lift"]
        story.append(Paragraph("LIFT DETAILS", section_style))
        lift_table = Table(
            [
                [
                    Paragraph("Month", label_style),
                    Paragraph(str(lift.get("month_number") or "—"), value_style),
                    Paragraph("Lift Date", label_style),
                    Paragraph(_display_date(lift.get("lift_date")), value_style),
                ],
                [
                    Paragraph("Lifted Amount", label_style),
                    Paragraph(_money(lift.get("lifted_amount")), value_bold_style),
                    Paragraph("Payout Status", label_style),
                    Paragraph(str(lift.get("payout_status") or "—").title(), value_style),
                ],
                [
                    Paragraph("Payout Date", label_style),
                    Paragraph(_display_date(lift.get("payout_date")), value_style),
                    Paragraph("Lift ID", label_style),
                    Paragraph(str(lift.get("lift_id") or "—"), value_style),
                ],
            ],
            colWidths=[27 * mm, 62 * mm, 28 * mm, 61 * mm],
        )
        lift_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#eceff3")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfbfc")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([lift_table, Spacer(1, 10)])

    # -----------------------------------------------------
    # Footer
    # -----------------------------------------------------

    story.extend(
        [
            HRFlowable(width="100%", thickness=0.6, color=BORDER),
            Spacer(1, 7),
            Paragraph(
                (
                    f"Generated on {_display_date(date.today())}. "
                    "This is a system-generated consolidated receipt for the exact chit slot "
                    f"(Member #{member.get('member_number')}, Slot #{member.get('slot_number') or '—'})."
                ),
                tiny_style,
            ),
        ]
    )

    # -----------------------------------------------------
    # Page footer / header strip
    # -----------------------------------------------------

    def draw_page(canvas, _doc):
        canvas.saveState()
        page_width, page_height = A4
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(14 * mm, 11 * mm, page_width - 14 * mm, 11 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawString(
            14 * mm,
            7 * mm,
            "SA Chits",
        )
        canvas.drawRightString(
            page_width - 14 * mm,
            7 * mm,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=draw_page,
        onLaterPages=draw_page,
    )

    return output.getvalue()
