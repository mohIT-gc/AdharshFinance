import os
from datetime import date

from sqlalchemy import text

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DB_MODE"] = "sqlite"

from app import Account, DailyLog, MonthlyLog, app, db, ensure_schema_columns


def test_full_account_flow():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()

        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Rahul",
                "loan_given_date": "2026-10-01",
                "display_name": "Rahul Sharma",
                "given_amount": 8000,
                "expected_amount": 12000,
                "total_months": 6,
            },
        )
        assert create_response.status_code == 201, create_response.get_data(as_text=True)

        accounts_response = client.get("/api/accounts")
        assert accounts_response.status_code == 200
        accounts = accounts_response.get_json()["accounts"]
        assert len(accounts) == 1
        assert accounts[0]["display_name"] == "Rahul Sharma"
        account_id = accounts[0]["id"]

        auto_name_response = client.post(
            "/api/accounts",
            json={
                "name": "Priya",
                "loan_given_date": "2026-11-02",
                "display_name": "",
                "given_amount": 5000,
                "expected_amount": 7000,
                "total_months": 4,
            },
        )
        assert auto_name_response.status_code == 201, auto_name_response.get_data(as_text=True)
        assert auto_name_response.get_json()["account"]["display_name"] == "Priya (2026-11-02)"

        log_response = client.post(
            f"/api/accounts/{account_id}/logs",
            json={"amount": 2000, "date": "2026-10-10"},
        )
        assert log_response.status_code == 201, log_response.get_data(as_text=True)

        close_response = client.post(f"/api/accounts/{account_id}/close")
        assert close_response.status_code == 200
        payload = close_response.get_json()
        assert payload["account"]["status"] == "Closed"

        summary_response = client.get("/api/dashboard")
        assert summary_response.status_code == 200
        data = summary_response.get_json()
        assert data["total_accounts"] == 2


def test_account_edit_and_status_update():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()

        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Asha",
                "loan_given_date": "2026-08-15",
                "display_name": "Asha (2026-08-15)",
                "given_amount": 12000,
                "expected_amount": 18000,
                "total_months": 6,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        page_response = client.get("/accounts")
        assert page_response.status_code == 200

        update_response = client.put(
            f"/api/accounts/{account_id}",
            json={
                "name": "Asha",
                "loan_given_date": "2026-08-15",
                "display_name": "Asha Updated",
                "given_amount": 13000,
                "expected_amount": 20000,
                "total_months": 8,
                "status": "Closed",
            },
        )
        assert update_response.status_code == 200, update_response.get_data(as_text=True)
        payload = update_response.get_json()
        assert payload["account"]["display_name"] == "Asha Updated"
        assert payload["account"]["status"] == "Closed"


def test_available_balance_updates_on_account_and_log():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()

        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Sonia",
                "loan_given_date": "2026-10-01",
                "display_name": "Sonia (2026-10-01)",
                "given_amount": 8000,
                "expected_amount": 10000,
                "total_months": 5,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        balance_after_create = client.get("/api/available-balance")
        assert balance_after_create.status_code == 200
        assert balance_after_create.get_json()["balance"] == -8000.0

        log_response = client.post(
            f"/api/accounts/{account_id}/logs",
            json={"amount": 2000, "date": "2026-10-10"},
        )
        assert log_response.status_code == 201

        balance_after_log = client.get("/api/available-balance")
        assert balance_after_log.status_code == 200
        assert balance_after_log.get_json()["balance"] == -6000.0


def test_bulk_daily_logs_can_be_saved_together():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()

        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Meera",
                "loan_given_date": "2026-10-05",
                "display_name": "Meera (2026-10-05)",
                "given_amount": 3000,
                "expected_amount": 6000,
                "total_months": 3,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        bulk_response = client.post(
            "/api/daily-logs/bulk",
            json={
                "entries": [
                    {"account_id": account_id, "amount": 500, "date": "2026-10-10"},
                    {"account_id": account_id, "amount": 700, "date": "2026-10-11"},
                ]
            },
        )
        assert bulk_response.status_code == 201, bulk_response.get_data(as_text=True)
        payload = bulk_response.get_json()
        assert len(payload["logs"]) == 2
        assert payload["logs"][0]["amount"] == 500.0
        assert payload["logs"][1]["amount"] == 700.0


def test_monthly_balance_rollover_closes_account_when_total_months_exceeded():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()

        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Nisha",
                "loan_given_date": "2026-10-01",
                "display_name": "Nisha (2026-10-01)",
                "given_amount": 1000,
                "expected_amount": 1000,
                "total_months": 1,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        log_response = client.post(
            f"/api/accounts/{account_id}/logs",
            json={"amount": 1200, "date": "2026-10-10"},
        )
        assert log_response.status_code == 201, log_response.get_data(as_text=True)

        account_data = client.get(f"/api/accounts/{account_id}").get_json()["account"]
        assert account_data["status"] == "Closed"

        monthly_rows = MonthlyLog.query.filter_by(account_id=account_id).order_by(MonthlyLog.current_month).all()
        assert len(monthly_rows) >= 2
        assert monthly_rows[0].current_amount == 1000.0
        assert monthly_rows[1].current_amount == 200.0


def test_monthly_log_records_completion_date_when_month_is_completed():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()
        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Monthly Completion",
                "loan_given_date": "2026-10-01",
                "display_name": "Monthly Completion (2026-10-01)",
                "given_amount": 1000,
                "expected_amount": 2000,
                "total_months": 2,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        log_response = client.post(
            f"/api/accounts/{account_id}/logs",
            json={"amount": 2000, "date": "2026-10-10"},
        )
        assert log_response.status_code == 201, log_response.get_data(as_text=True)

        monthly_rows = MonthlyLog.query.filter_by(account_id=account_id).order_by(MonthlyLog.current_month).all()
        assert len(monthly_rows) >= 2
        first_month = monthly_rows[0]
        assert first_month.completed_month is True
        assert first_month.completed_date == date.fromisoformat("2026-10-10")


def test_accounts_endpoint_supports_status_filter():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()
        client.post(
            "/api/accounts",
            json={
                "name": "Open Filter Account",
                "loan_given_date": "2026-10-01",
                "display_name": "Open Filter Account (2026-10-01)",
                "given_amount": 5000,
                "expected_amount": 6000,
                "total_months": 2,
            },
        )
        closed_response = client.post(
            "/api/accounts",
            json={
                "name": "Closed Filter Account",
                "loan_given_date": "2026-10-02",
                "display_name": "Closed Filter Account (2026-10-02)",
                "given_amount": 7000,
                "expected_amount": 8000,
                "total_months": 2,
            },
        )
        assert closed_response.status_code == 201
        closed_account_id = closed_response.get_json()["account"]["id"]
        client.post(f"/api/accounts/{closed_account_id}/close")

        open_response = client.get("/api/accounts?status=open")
        assert open_response.status_code == 200
        open_accounts = open_response.get_json()["accounts"]
        assert all(account["status"] in {"Open", "Active"} for account in open_accounts)

        closed_response = client.get("/api/accounts?status=closed")
        assert closed_response.status_code == 200
        closed_accounts = closed_response.get_json()["accounts"]
        assert len(closed_accounts) == 1
        assert closed_accounts[0]["status"] == "Closed"


def test_recent_daily_logs_endpoint_returns_latest_rows():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()
        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Daily Logs",
                "loan_given_date": "2026-10-01",
                "display_name": "Daily Logs (2026-10-01)",
                "given_amount": 5000,
                "expected_amount": 6000,
                "total_months": 2,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        client.post(f"/api/accounts/{account_id}/logs", json={"amount": 1000, "date": "2026-10-02"})
        client.post(f"/api/accounts/{account_id}/logs", json={"amount": 2000, "date": "2026-10-03"})

        response = client.get("/api/daily-logs/recent")
        assert response.status_code == 200
        payload = response.get_json()
        assert len(payload["logs"]) >= 2
        assert payload["logs"][0]["account_name"] == "Daily Logs (2026-10-01)"


def test_recent_daily_logs_endpoint_respects_custom_date_filter():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()
        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Filtered Logs",
                "loan_given_date": "2026-10-01",
                "display_name": "Filtered Logs (2026-10-01)",
                "given_amount": 5000,
                "expected_amount": 6000,
                "total_months": 2,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        client.post(f"/api/accounts/{account_id}/logs", json={"amount": 1000, "date": "2026-10-02"})
        client.post(f"/api/accounts/{account_id}/logs", json={"amount": 2000, "date": "2026-10-10"})
        client.post(f"/api/accounts/{account_id}/logs", json={"amount": 3000, "date": "2026-10-20"})

        response = client.get("/api/daily-logs/recent?from_date=2026-10-02&to_date=2026-10-10")
        assert response.status_code == 200
        payload = response.get_json()
        assert [log["date"] for log in payload["logs"]] == ["2026-10-10", "2026-10-02"]


def test_monthly_logs_endpoint_returns_account_rows():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()
        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Monthly Review",
                "loan_given_date": "2026-10-01",
                "display_name": "Monthly Review (2026-10-01)",
                "given_amount": 3000,
                "expected_amount": 6000,
                "total_months": 2,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        client.post(f"/api/accounts/{account_id}/logs", json={"amount": 4000, "date": "2026-10-10"})

        response = client.get(f"/api/accounts/{account_id}/monthly-logs")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["account_id"] == account_id
        assert len(payload["logs"]) >= 2
        assert payload["logs"][0]["current_month"] in {1, 2}


def test_missing_monthly_log_completed_date_is_added_via_schema_migration():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        db.session.execute(text("ALTER TABLE monthly_log DROP COLUMN completed_date"))
        db.session.commit()

        ensure_schema_columns()

        columns = db.inspect(db.engine).get_columns("monthly_log")
        assert any(column["name"] == "completed_date" for column in columns)


def test_account_delete_removes_account_and_related_rows():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        client = app.test_client()

        create_response = client.post(
            "/api/accounts",
            json={
                "name": "Delete Me",
                "loan_given_date": "2026-10-01",
                "display_name": "Delete Me (2026-10-01)",
                "given_amount": 4000,
                "expected_amount": 5000,
                "total_months": 2,
            },
        )
        assert create_response.status_code == 201
        account_id = create_response.get_json()["account"]["id"]

        delete_response = client.delete(f"/api/accounts/{account_id}")
        assert delete_response.status_code == 200, delete_response.get_data(as_text=True)
        assert client.get(f"/api/accounts/{account_id}").status_code == 404
