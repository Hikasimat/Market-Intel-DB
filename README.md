# MarketIntel DB

A full-stack CRM and market-intelligence platform for Prospect Research Engineers (PRE) and Lead Qualifiers (LQ).

## Architecture

```
Browser
  └─► Static Host (React + Vite frontend)
        └─► AWS EC2 (Nginx → Gunicorn → Django REST API)
              ├─► PostgreSQL / Supabase
              ├─► Gmail IMAP / SMTP (per-user mail accounts)
              └─► Cloudflare R2 (optional object storage)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Redux Toolkit, Tailwind CSS v4 |
| Backend | Django 6, Django REST Framework |
| Auth | JWT (SimpleJWT) |
| Database | PostgreSQL (Supabase in production) |
| Backend hosting | AWS EC2 + Gunicorn + Nginx |
| Frontend hosting | Static Host / Nginx |

## Project Structure

```
Market-Intel-DB/
├── backend/          # Django REST API
│   ├── accounts/     # Auth, UserProfile, MailAccount (IMAP/SMTP)
│   ├── prospects/    # Prospects, LQ Pipeline, Reminders, Outreach
│   ├── market_events/# Market Events
│   ├── companies/    # Companies
│   └── config/       # Django settings, URLs, WSGI
├── frontend/         # React + Vite SPA
│   └── src/
│       ├── app/      # Redux store
│       ├── features/ # Redux slices (auth, prospects, marketEvents, lqPipeline, ...)
│       ├── pages/    # Page components
│       ├── components/ # Shared components (Layout, NotificationCenter, ...)
│       ├── services/ # Axios API client + IndexedDB cache service
│       └── router/   # React Router
└── deploy/
    └── aws/          # EC2 deployment scripts, Nginx config, systemd service
```

## Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 15+

### Backend

```bash
cd backend
python -m venv env
source env/bin/activate        # Windows: env\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in values
python manage.py migrate
python manage.py runserver
```

Backend runs at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local     # fill in values
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Environment Variables

### Backend (`backend/.env`)

See [`backend/.env.example`](backend/.env.example) for a full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for local, `False` for production |
| `DATABASE_URL` | PostgreSQL connection string (production) |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `CORS_ALLOWED_ORIGINS` | Frontend origin(s) |
| `MAIL_CREDENTIALS_ENCRYPTION_KEY` | Fernet key for IMAP/SMTP password encryption |
| `EMAIL_TRACKING_BASE_URL` | Public backend URL for email open-tracking |

### Frontend (`frontend/.env.local`)

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Backend API URL, e.g. `https://YOUR_BACKEND_DOMAIN/api` |

## AWS EC2 Deployment (Backend)

See [`deploy/aws/`](deploy/aws/) for:
- `setup_ec2.sh` — one-time EC2 instance setup
- `deploy.sh` — idempotent code update and restart
- `nginx.conf` — Nginx reverse-proxy configuration
- `marketintel.service` — systemd Gunicorn service

### Deploy a backend update

```bash
# On the EC2 instance:
sudo -u marketintel bash /opt/marketintel/repo/deploy/aws/deploy.sh
```

This pulls the latest code, installs dependencies, runs migrations, collects static files, and restarts Gunicorn.

## Frontend Deployment

The frontend can be built as a static site and hosted on Nginx or any static host.
Set the following environment variable during build:

```
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN/api
```

When using Nginx, ensure you route the SPA correctly by using `try_files $uri $uri/ /index.html`.

## User Roles

| Role | Access |
|------|--------|
| **PRE** (Prospect Research Engineer) | Prospects, Market Events (full CRUD), Key People, Tasks |
| **LQ** (Lead Qualifier) | LQ Pipeline, Market Events (read-only), Key People, Inbox |
| **Superuser/Admin** | All of the above + User Management |

## Bulk Email Campaigns & Prospect Intelligence

### 1. Sequential Bulk Email Campaigns (90-Second Interval)
- **Controlled Pacing**: Sends each email sequentially with a strict **90-second minimum interval** between consecutive provider send operations. Later emails are never released prematurely if an earlier email takes time or requires retries.
- **Database Queue**: Stored persistently in PostgreSQL (`EmailCampaign`, `EmailCampaignRecipient`, `EmailCampaignAttachment`) using row-level locking (`select_for_update`). Campaigns survive browser closures, API restarts, and worker restarts.
- **Worker Execution**: Managed by the dedicated `process_campaign_queue` management command. Does not require Redis or Celery.
- **Live Controls**: Users can pause, resume, and cancel campaigns from the Inbox interface, with real-time progress indicators and duration estimates `(N - 1) * 90s`.
- **Full Deliverability Support**: Supports email templates, email signatures, multi-file attachments, and opt-in open tracking.

#### Running the Campaign Worker
**Development / Local:**
```bash
cd backend
python manage.py process_campaign_queue --poll-interval 5
# Or execute a single pass:
python manage.py process_campaign_queue --run-once
```

**Production (systemd):**
```bash
sudo systemctl start marketintel-worker
sudo systemctl status marketintel-worker
sudo journalctl -u marketintel-worker -f
```

**Production (Docker Compose):**
```bash
docker compose -f deploy/aws/docker-compose.production.yml up -d campaign-worker
docker compose -f deploy/aws/docker-compose.production.yml logs -f campaign-worker
```

### 2. Automatic Prospect Response Identification
- **Accurate Inbound Matching**: Matches incoming email sender addresses (`From` header) against:
  - Company official email (`Prospect.official_email_address`) -> attaches company badge & tag.
  - Key contact official email (`ProspectContact.official_email`) -> attaches both company tag and key-person tag.
- **Pipeline Access Control**: Strictly respects role-based visibility. PREs see their assigned prospects, LQs see their assigned pipeline, and Managers see all records.
- **Virtual Prospect Responses Folder**: Dedicated view inside the existing Inbox (`/auth/mail-account/prospect-responses/`) leveraging Gmail server-side query batching (`from:(...)`) without modifying native Gmail folder labels.

## Running Tests

```bash
cd backend
# Run all tests:
python manage.py test

# Run new bulk campaign & prospect matching tests:
python manage.py test prospects.test_bulk_campaigns prospects.test_prospect_matching
```
