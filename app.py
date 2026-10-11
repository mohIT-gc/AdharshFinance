import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy

load_dotenv()


def normalize_database_url(raw_url):
    if not raw_url:
        return "sqlite:///finance_dev.db"

    normalized = raw_url.strip()
    if normalized.startswith("postgres://") and "+psycopg2" not in normalized:
        normalized = normalized.replace("postgres://", "postgresql+psycopg2://", 1)
    elif normalized.startswith("postgresql://") and "+psycopg2" not in normalized:
        normalized = normalized.replace("postgresql://", "postgresql+psycopg2://", 1)
    return normalized


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:AdharshFinance2022@adharshfinance-db.c3i4u0i8kxlb.ap-south-1.rds.amazonaws.com:5432/AdharshFinance-DB"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["JSON_SORT_KEYS"] = False

app.logger.setLevel(logging.INFO)
app.logger.handlers.clear()
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
app.logger.addHandler(stream_handler)
logger = app.logger


@app.before_request
def log_request_start():
    logger.info("Incoming request: %s %s", request.method, request.path)


@app.after_request
def log_request_end(response):
    logger.info("Completed request: %s %s status=%s content_type=%s", request.method, request.path, response.status_code, response.content_type)
    return response


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logger.exception("Unhandled exception for %s %s: %s", request.method, request.path, error)
    return jsonify({"error": "Internal server error"}), 500


db = SQLAlchemy(app)


class AvailableBalance(db.Model):
    __tablename__ = "available_balance"

    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "balance": float(self.balance or 0),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Account(db.Model):
    __tablename__ = "account"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    loan_given_date = db.Column(db.Date, nullable=False)
    display_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Active")
    given_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_months = db.Column(db.Integer, nullable=False, default=0)
    amount_collected = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    completed_date = db.Column(db.Date, nullable=True)

    daily_logs = db.relationship("DailyLog", backref="account", lazy=True, cascade="all, delete-orphan")
    monthly_logs = db.relationship("MonthlyLog", backref="account", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "loan_given_date": self.loan_given_date.isoformat() if self.loan_given_date else None,
            "display_name": self.display_name,
            "status": self.status,
            "given_amount": float(self.given_amount or 0),
            "expected_amount": float(self.expected_amount or 0),
            "total_months": self.total_months,
            "amount_collected": float(self.amount_collected or 0),
            "completed_date": self.completed_date.isoformat() if self.completed_date else None,
        }


class DailyLog(db.Model):
    __tablename__ = "daily_logs"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    date = db.Column(db.Date, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "amount": float(self.amount or 0),
            "date": self.date.isoformat() if self.date else None,
        }


class MonthlyLog(db.Model):
    __tablename__ = "monthly_log"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    month_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    current_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    current_month = db.Column(db.Integer, nullable=False, default=1)
    completed_month = db.Column(db.Boolean, nullable=False, default=False)
    completed_date = db.Column(db.Date, nullable=True)
    total_months = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "month_amount": float(self.month_amount or 0),
            "current_amount": float(self.current_amount or 0),
            "current_month": self.current_month,
            "completed_month": self.completed_month,
            "completed_date": self.completed_date.isoformat() if self.completed_date else None,
            "total_months": self.total_months,
        }


def parse_decimal(value):
    if value is None or value == "":
        raise ValueError("Value is required")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal value") from exc


def parse_date(value):
    if value is None or value == "":
        raise ValueError("Date is required")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("Date must be valid ISO format like YYYY-MM-DD") from exc


def build_display_name(name, loan_date):
    clean_name = (name or "").strip()
    if not clean_name:
        return ""
    parsed_date = loan_date if isinstance(loan_date, date) else parse_date(loan_date)
    return f"{clean_name} ({parsed_date.isoformat()})"


def normalize_status(value):
    if value is None:
        return "Open"
    status = str(value).strip()
    if status.lower() in {"active", "open"}:
        return "Open"
    if status.lower() == "closed":
        return "Closed"
    return "Open"


def get_available_balance_record():
    record = AvailableBalance.query.first()
    if record is None:
        record = AvailableBalance(balance=Decimal("0.00"))
        db.session.add(record)
        db.session.flush()
    return record


def update_available_balance(delta_value):
    record = get_available_balance_record()
    previous_balance = record.balance or Decimal("0.00")
    new_balance = previous_balance + Decimal(str(delta_value))
    record.balance = new_balance
    record.updated_at = datetime.now(timezone.utc)
    db.session.add(record)
    logger.info("Available balance updated: delta=%s previous=%s new=%s", delta_value, previous_balance, new_balance)
    return record.balance


def ensure_schema_columns():
    with app.app_context():
        inspector = db.inspect(db.engine)
        if "monthly_log" not in inspector.get_table_names():
            return

        existing_columns = {column["name"] for column in inspector.get_columns("monthly_log")}
        if "completed_date" not in existing_columns:
            db.session.execute(text("ALTER TABLE monthly_log ADD COLUMN completed_date DATE"))
            db.session.commit()
            logger.info("Added completed_date column to monthly_log table")


def initialize_database():
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        if AvailableBalance.query.first() is None:
            db.session.add(AvailableBalance(balance=Decimal("0.00")))
            db.session.commit()


def build_monthly_summary(account, payment_date):
    month_amount = get_monthly_amount_for_account(account)
    monthly_entry = (
        MonthlyLog.query.filter_by(account_id=account.id)
        .order_by(MonthlyLog.current_month.desc())
        .first()
    )
    if monthly_entry is None:
        monthly_entry = MonthlyLog(
            account_id=account.id,
            month_amount=month_amount,
            current_amount=Decimal("0.00"),
            current_month=1,
            completed_month=False,
            total_months=account.total_months,
        )
        db.session.add(monthly_entry)

    monthly_entry.current_amount = (monthly_entry.current_amount or Decimal("0.00")) + Decimal("0")
    return monthly_entry, month_amount


def get_monthly_amount_for_account(account):
    if account.total_months <= 0:
        return Decimal("0.00")
    return (account.expected_amount / Decimal(account.total_months)).quantize(Decimal("0.01"))


def get_active_month_entry(account):
    entry = (
        MonthlyLog.query.filter_by(account_id=account.id)
        .order_by(MonthlyLog.current_month.desc())
        .first()
    )
    if entry is not None:
        return entry

    month_amount = get_monthly_amount_for_account(account)
    entry = MonthlyLog(
        account_id=account.id,
        month_amount=month_amount,
        current_amount=Decimal("0.00"),
        current_month=1,
        completed_month=False,
        total_months=account.total_months,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def set_month_completion_status(month_entry, completion_date):
    if month_entry is None:
        return

    if month_entry.current_amount >= month_entry.month_amount:
        month_entry.completed_month = True
        if month_entry.completed_date is None:
            month_entry.completed_date = completion_date
    else:
        month_entry.completed_month = False
        month_entry.completed_date = None


def finalize_monthly_progress(account):
    if account.total_months <= 0:
        return

    latest_row = (
        MonthlyLog.query.filter_by(account_id=account.id)
        .order_by(MonthlyLog.current_month.desc())
        .first()
    )
    if latest_row is None:
        return

    if latest_row.current_month > account.total_months:
        account.status = "Closed"
        account.completed_date = account.completed_date or date.today()
        if latest_row.completed_date is None:
            latest_row.completed_date = account.completed_date
    elif latest_row.current_amount < latest_row.month_amount and latest_row.completed_date is not None:
        latest_row.completed_date = None


@app.route("/")
def index():
    logger.info("Rendering dashboard page")
    return render_template("index.html")


@app.route("/accounts")
def accounts_page():
    logger.info("Rendering accounts page")
    return render_template("accounts.html")


@app.route("/health")
def health():
    logger.info("Health check requested")
    return jsonify({"status": "ok"})


@app.route("/api/dashboard")
def dashboard():
    logger.info("Generating dashboard summary")
    total_accounts = Account.query.count()
    active_accounts = Account.query.filter(Account.status.in_(["Active", "Open"])).count()
    closed_accounts = Account.query.filter_by(status="Closed").count()
    total_collected = db.session.query(db.func.coalesce(db.func.sum(Account.amount_collected), 0)).scalar() or 0
    available_balance = get_available_balance_record().balance

    return jsonify(
        {
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "closed_accounts": closed_accounts,
            "total_collected": float(total_collected),
            "available_balance": float(available_balance),
        }
    )


@app.route("/api/available-balance")
def available_balance():
    record = get_available_balance_record()
    return jsonify({"balance": float(record.balance or 0), "updated_at": record.updated_at.isoformat() if record.updated_at else None})


@app.route("/api/accounts", methods=["GET", "POST"])
def accounts():
    if request.method == "GET":
        status_filter = (request.args.get("status") or "all").strip().lower()
        query = Account.query

        if status_filter == "open":
            query = query.filter(Account.status.in_(["Open", "Active"]))
        elif status_filter == "closed":
            query = query.filter_by(status="Closed")
        elif status_filter not in ("all", ""):
            query = query.filter(Account.status.ilike(status_filter))

        logger.info("Fetching accounts with filter=%s", status_filter)
        accounts_list = query.order_by(Account.loan_given_date.desc()).all()
        return jsonify({"accounts": [account.to_dict() for account in accounts_list]})

    logger.info("Creating account from API payload")
    payload = request.get_json(silent=True) or {}
    required_fields = ["name", "loan_given_date", "given_amount", "expected_amount", "total_months"]
    missing = [field for field in required_fields if field not in payload or payload[field] in (None, "")]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        loan_date = parse_date(payload["loan_given_date"])
        given_amount = parse_decimal(payload["given_amount"])
        expected_amount = parse_decimal(payload["expected_amount"])
        total_months = int(payload["total_months"])
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    if total_months <= 0:
        return jsonify({"error": "Total months must be greater than zero"}), 400

    display_name = (payload.get("display_name") or "").strip() or build_display_name(payload["name"], loan_date)

    account = Account(
        name=payload["name"].strip(),
        loan_given_date=loan_date,
        display_name=display_name,
        status=normalize_status(payload.get("status", "Open")),
        given_amount=given_amount,
        expected_amount=expected_amount,
        total_months=total_months,
        amount_collected=Decimal("0.00"),
    )

    db.session.add(account)
    db.session.flush()
    update_available_balance(-given_amount)

    logger.info(
        "Account created: id=%s name=%s display_name=%s given_amount=%s expected_amount=%s total_months=%s",
        account.id,
        account.name,
        account.display_name,
        given_amount,
        expected_amount,
        total_months,
    )

    month_amount = (expected_amount / Decimal(total_months)).quantize(Decimal("0.01"))
    monthly_log = MonthlyLog(
        account_id=account.id,
        month_amount=month_amount,
        current_amount=Decimal("0.00"),
        current_month=1,
        completed_month=False,
        total_months=total_months,
    )
    db.session.add(monthly_log)
    db.session.commit()

    return jsonify({"message": "Account created successfully", "account": account.to_dict()}), 201


@app.route("/api/accounts/<int:account_id>", methods=["GET", "PUT", "DELETE"])
def account_detail(account_id):
    logger.info("Account operation requested: account_id=%s method=%s", account_id, request.method)
    account = db.session.get(Account, account_id)
    if account is None:
        logger.warning("Account not found during detail operation: account_id=%s", account_id)
        return jsonify({"error": "Account not found"}), 404

    if request.method == "GET":
        logger.info("Returning account details for account_id=%s", account_id)
        return jsonify({"account": account.to_dict()})

    if request.method == "DELETE":
        logger.warning("Deleting account: id=%s name=%s status=%s", account.id, account.name, account.status)
        db.session.delete(account)
        db.session.commit()
        return jsonify({"message": "Account deleted successfully"})

    payload = request.get_json(silent=True) or {}
    required_fields = ["name", "loan_given_date", "given_amount", "expected_amount", "total_months"]
    missing = [field for field in required_fields if field not in payload or payload[field] in (None, "")]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        loan_date = parse_date(payload["loan_given_date"])
        given_amount = parse_decimal(payload["given_amount"])
        expected_amount = parse_decimal(payload["expected_amount"])
        total_months = int(payload["total_months"])
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    if total_months <= 0:
        return jsonify({"error": "Total months must be greater than zero"}), 400

    account.name = payload["name"].strip()
    account.loan_given_date = loan_date
    account.display_name = (payload.get("display_name") or "").strip() or build_display_name(account.name, loan_date)
    account.given_amount = given_amount
    account.expected_amount = expected_amount
    account.total_months = total_months
    account.status = normalize_status(payload.get("status", account.status))
    if account.status == "Closed":
        account.completed_date = account.completed_date or date.today()
    else:
        account.completed_date = None

    logger.info(
        "Account updated: id=%s name=%s status=%s given_amount=%s expected_amount=%s total_months=%s",
        account.id,
        account.name,
        account.status,
        given_amount,
        expected_amount,
        total_months,
    )

    db.session.commit()
    return jsonify({"message": "Account updated successfully", "account": account.to_dict()})


def create_daily_log_record(account, amount, log_date):
    logger.info(
        "Processing daily log for account_id=%s amount=%s date=%s status=%s",
        account.id,
        amount,
        log_date.isoformat() if isinstance(log_date, date) else str(log_date),
        account.status,
    )
    daily_log = DailyLog(account_id=account.id, amount=amount, date=log_date)
    db.session.add(daily_log)
    db.session.flush()
    update_available_balance(amount)

    account.amount_collected = (account.amount_collected or Decimal("0.00")) + amount
    db.session.flush()

    month_amount = get_monthly_amount_for_account(account)
    month_entry = (
        MonthlyLog.query.filter_by(account_id=account.id)
        .order_by(MonthlyLog.current_month.desc())
        .first()
    )
    if month_entry is None:
        month_entry = MonthlyLog(
            account_id=account.id,
            month_amount=month_amount,
            current_amount=Decimal("0.00"),
            current_month=1,
            completed_month=False,
            completed_date=None,
            total_months=account.total_months,
        )
        db.session.add(month_entry)

    month_entry.current_amount = (month_entry.current_amount or Decimal("0.00")) + amount
    month_entry.month_amount = month_amount
    set_month_completion_status(month_entry, log_date)

    while month_entry.current_amount >= month_entry.month_amount:
        overflow = month_entry.current_amount - month_entry.month_amount
        month_entry.current_amount = month_entry.month_amount
        month_entry.completed_month = True
        if month_entry.completed_date is None:
            month_entry.completed_date = log_date

        next_month_number = month_entry.current_month + 1
        next_entry = MonthlyLog.query.filter_by(account_id=account.id, current_month=next_month_number).first()
        if next_entry is None:
            next_entry = MonthlyLog(
                account_id=account.id,
                month_amount=month_amount,
                current_amount=Decimal("0.00"),
                current_month=next_month_number,
                completed_month=False,
                completed_date=None,
                total_months=account.total_months,
            )
            db.session.add(next_entry)

        if next_month_number > account.total_months:
            account.status = "Closed"
            account.completed_date = account.completed_date or date.today()
            next_entry.current_amount = (next_entry.current_amount or Decimal("0.00")) + overflow
            next_entry.month_amount = month_amount
            if next_entry.current_amount >= next_entry.month_amount:
                next_entry.completed_month = True
                if next_entry.completed_date is None:
                    next_entry.completed_date = log_date
            else:
                next_entry.completed_month = False
                next_entry.completed_date = None
            month_entry = next_entry
            break

        next_entry.current_amount = (next_entry.current_amount or Decimal("0.00")) + overflow
        next_entry.month_amount = month_amount
        set_month_completion_status(next_entry, log_date)
        month_entry = next_entry

    if month_entry.current_amount >= month_entry.month_amount:
        month_entry.completed_month = True
        if month_entry.completed_date is None:
            month_entry.completed_date = log_date
    else:
        month_entry.completed_month = False
        month_entry.completed_date = None

    finalize_monthly_progress(account)
    logger.info(
        "Daily log saved: account_id=%s log_id=%s amount=%s month_amount=%s current_amount=%s current_month=%s status=%s",
        account.id,
        daily_log.id,
        amount,
        month_entry.month_amount,
        month_entry.current_amount,
        month_entry.current_month,
        account.status,
    )
    return daily_log


@app.route("/api/accounts/<int:account_id>/logs", methods=["POST"])
def add_daily_log(account_id):
    logger.info("Single daily-log save requested for account_id=%s", account_id)
    payload = request.get_json(silent=True) or {}
    if "amount" not in payload or payload["amount"] in (None, ""):
        logger.warning("Single daily-log validation failed: missing amount for account_id=%s", account_id)
        return jsonify({"error": "Amount is required"}), 400

    account = db.session.get(Account, account_id)
    if account is None:
        return jsonify({"error": "Account not found"}), 404
    if account.status == "Closed":
        return jsonify({"error": "Closed account cannot receive new logs"}), 400

    try:
        amount = parse_decimal(payload["amount"])
        log_date = parse_date(payload.get("date") or date.today().isoformat())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    daily_log = create_daily_log_record(account, amount, log_date)
    db.session.commit()

    return jsonify({"message": "Daily log added successfully", "log": daily_log.to_dict(), "account": account.to_dict()}), 201


@app.route("/api/daily-logs/recent", methods=["GET"])
def recent_daily_logs():
    from_date_raw = request.args.get("from_date") or request.args.get("from")
    to_date_raw = request.args.get("to_date") or request.args.get("to")

    query = DailyLog.query
    has_custom_filter = bool(from_date_raw or to_date_raw)

    if has_custom_filter:
        if from_date_raw:
            query = query.filter(DailyLog.date >= parse_date(from_date_raw))
        if to_date_raw:
            query = query.filter(DailyLog.date <= parse_date(to_date_raw))
    else:
        default_start = date.today() - timedelta(days=9)
        query = query.filter(DailyLog.date >= default_start)

    logs = query.order_by(DailyLog.date.desc(), DailyLog.id.desc()).all()
    payload = []
    for log in logs:
        account = log.account
        payload.append(
            {
                "id": log.id,
                "account_id": log.account_id,
                "account_name": account.display_name if account else None,
                "amount": float(log.amount or 0),
                "date": log.date.isoformat() if log.date else None,
            }
        )
    return jsonify({"logs": payload})


@app.route("/api/accounts/<int:account_id>/monthly-logs", methods=["GET"])
def account_monthly_logs(account_id):
    account = db.session.get(Account, account_id)
    if account is None:
        return jsonify({"error": "Account not found"}), 404

    logs = MonthlyLog.query.filter_by(account_id=account_id).order_by(MonthlyLog.current_month.asc()).all()
    return jsonify({
        "account_id": account.id,
        "account_name": account.display_name,
        "logs": [entry.to_dict() for entry in logs],
    })


@app.route("/api/daily-logs/bulk", methods=["POST"])
def add_daily_logs_bulk():
    logger.debug("Bulk daily-log save requested")
    payload = request.get_json(silent=True) or {}

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return jsonify({"error": "At least one daily log entry is required"}), 400

    prepared_entries = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return jsonify({"error": f"Entry at position {index} must be an object"}), 400

        if "account_id" not in entry or entry["account_id"] in (None, ""):
            return jsonify({"error": f"Entry at position {index} is missing account_id"}), 400
        if "amount" not in entry or entry["amount"] in (None, ""):
            return jsonify({"error": f"Entry at position {index} is missing amount"}), 400

        try:
            account_id = int(entry["account_id"])
            amount = parse_decimal(entry["amount"])
            log_date = parse_date(entry.get("date") or date.today().isoformat())
                
        except (TypeError, ValueError) as exc:
            return jsonify({"error": f"Invalid entry at position {index}: {exc}"}), 400

        if amount <= 0:
            return jsonify({"error": f"Entry at position {index} requires an amount greater than zero"}), 400

        account = db.session.get(Account, account_id)
        if account is None:
            return jsonify({"error": f"Account not found for entry at position {index}"}), 404
        if account.status == "Closed":
            return jsonify({"error": f"Closed account cannot receive new logs for entry at position {index}"}), 400

        prepared_entries.append({"account": account, "amount": amount, "date": log_date})

    created_logs = []
    logger.info("Bulk daily log save requested: %s entries", len(prepared_entries))
    for item in prepared_entries:
        created_logs.append(create_daily_log_record(item["account"], item["amount"], item["date"]))

    db.session.commit()
    logger.info("Bulk daily logs saved successfully: %s logs", len(created_logs))
    return jsonify({"message": "Daily logs added successfully", "logs": [log.to_dict() for log in created_logs]}), 201


@app.route("/api/accounts/<int:account_id>/close", methods=["POST"])
def close_account(account_id):
    logger.info("Close account request received for account_id=%s", account_id)
    account = db.session.get(Account, account_id)
    if account is None:
        logger.warning("Close request failed: account not found account_id=%s", account_id)
        return jsonify({"error": "Account not found"}), 404
    if account.status == "Closed":
        logger.info("Close request ignored: account already closed account_id=%s", account_id)
        return jsonify({"message": "Account is already closed", "account": account.to_dict()})

    account.status = "Closed"
    account.completed_date = date.today()
    logger.warning("Closing account: id=%s name=%s closed_on=%s", account.id, account.name, account.completed_date.isoformat())
    db.session.commit()

    return jsonify({"message": "Account closed successfully", "account": account.to_dict()})


initialize_database()


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
