# Finance Management App

A lightweight finance tracking application for managing loan accounts, daily payments, and monthly summary tracking. It is designed to run locally with SQLite for quick testing and can be pointed to a local PostgreSQL instance or an AWS RDS PostgreSQL database for deployment.

## Features

- Add new account
- Add daily payment log entries
- Close account
- Auto-calculate total collected amount and monthly progress
- Simple HTML/CSS frontend
- Minimal tech stack for easy maintenance

## Tech stack

- Backend: Python + Flask
- Frontend: HTML + CSS + vanilla JavaScript
- Database: SQLite for quick local development, PostgreSQL with psycopg2 for local and AWS deployment
- Deployment: gunicorn behind AWS-friendly hosting (EC2, Elastic Beanstalk, ECS, App Runner)

## Local development

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy environment variables:
   ```bash
   copy .env.example .env
   ```
4. Update the Postgres password in `.env` if you want to use local PostgreSQL:
   ```env
   DATABASE_URL=postgresql+psycopg2://postgres:YOUR_LOCAL_POSTGRES_PASSWORD@localhost:5432/finance_db
   ```
5. Start the app:
   ```bash
   python app.py
   ```
5. Open: http://localhost:5000

## AWS deployment notes

For AWS production, set the following environment variable to your PostgreSQL RDS connection string:

```bash
DATABASE_URL=postgresql+psycopg2://username:password@your-rds-endpoint:5432/finance_db
DB_MODE=postgres
```

Cost optimization guidance:

- Use a small PostgreSQL instance such as `db.t4g.micro` or `db.t3.micro` depending on region availability.
- Keep the app stateless and use a single RDS instance for development and production.
- Prefer a single EC2 instance or lightweight container service rather than a heavy multi-service architecture.
- Use a single database with small tables and indexed keys to keep costs low.

## Database model

### Account
- Name
- Loan Given Date
- DisplayName
- Status
- Given Amount
- Expected Amount
- Total Months
- Amount Collected
- Completed Date

### DailyLogs
- Account_id
- Amount
- Date

### MonthlyLog
- AccountId
- MonthAmount
- CurrentAmount
- CurrentMonth
- CompletedMonth
- TotalMonths

## Run with production server

```bash
gunicorn app:app
```
