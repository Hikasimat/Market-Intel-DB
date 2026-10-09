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

## Running Tests

```bash
cd backend
python manage.py test
```
