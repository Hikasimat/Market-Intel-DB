# MarketIntel — AWS EC2 Backend Deployment Guide

This guide details the deployment of the Django backend to a persistent AWS EC2 instance.  
The frontend is hosted on a static host. The database stays on Supabase. Gmail stays as the mail provider.

---

## Architecture Overview

```
Browser
  │
  ▼
Static Host (React/Vite frontend)
  │ HTTPS API calls
  ▼
Cloudflare DNS / HTTPS (YOUR_BACKEND_DOMAIN)
  │
  ▼
AWS EC2 — Ubuntu
  ├── Nginx :443 (TLS termination + reverse proxy)
  └── Gunicorn :8000 (127.0.0.1 only, not public)
        └── Django REST Framework
              ├── Supabase PostgreSQL (direct, port 5432)
              ├── Gmail SMTP :587 (STARTTLS)
              ├── Gmail IMAP :993 (SSL)
              └── Cloudflare R2 (HTTPS)
```

---

## Automated (Repository)

The following has already been done for you in the repository:

- [x] `gunicorn` added to `requirements.txt`  
- [x] IMAP/SMTP connections patched with `finally` blocks (no connection leaks)  
- [x] `python manage.py check_mail_configuration` diagnostic command created  
- [x] `deploy/aws/setup_ec2.sh` — one-time server bootstrap  
- [x] `deploy/aws/deploy.sh` — idempotent deployment script  
- [x] `deploy/aws/marketintel.service` — systemd unit for Gunicorn  
- [x] `deploy/aws/nginx.conf` — Nginx reverse proxy + static files  
- [x] `backend/.env.example` — full production environment template  

---

## Manual Steps Required

All steps below require the AWS Console, SSH, or your Cloudflare dashboard.

---

## PART A — AWS Account & Free Tier

1. Go to [https://aws.amazon.com/free/](https://aws.amazon.com/free/)
2. Sign in or create an account.
3. Verify Free Tier eligibility for your account at:  
   **Billing → Free Tier** in the AWS Console.

> [!IMPORTANT]
> Free Tier eligibility (750 hours/month of `t2.micro` or `t3.micro`) is valid for the **first 12 months** of a new account. Confirm in your AWS Console before proceeding.

---

## PART B — Select AWS Region

1. In the AWS Console, top-right dropdown → select **Asia Pacific (Mumbai) — ap-south-1**  
   (or any region close to your users)
2. Confirm the region is shown in the top-right before creating any resources.

---

## PART C — Launch EC2 Instance

1. Go to **EC2 → Instances → Launch Instances**
2. Fill in:

| Setting | Value |
|---|---|
| Name | `marketintel-backend` |
| AMI | Ubuntu Server 24.04 LTS (HVM) — 64-bit x86 |
| Instance type | `t3.micro` ← only if shown as **Free tier eligible** |
| Key pair | Create new → name `marketintel-key` → RSA → .pem → Download |
| Storage | 8 GB gp3 (default) |

> [!CAUTION]
> If the AWS Console does NOT show `t3.micro` as Free Tier eligible, select `t2.micro` instead. **Do not select an instance that is not marked as Free Tier eligible.**

3. Under **Network settings → Create security group**, configure:

| Type | Port | Source |
|---|---|---|
| SSH | 22 | My IP (select from dropdown) |
| HTTP | 80 | Anywhere (0.0.0.0/0, ::/0) |
| HTTPS | 443 | Anywhere (0.0.0.0/0, ::/0) |

> [!WARNING]
> Do NOT add rules for port 8000, 5432, or 6379. These must never be exposed publicly.

4. Click **Launch Instance**.

---

## PART D — Save SSH Key & Connect

1. Move the downloaded `.pem` key to a safe location:
   ```bash
   mkdir -p ~/.ssh
   mv ~/Downloads/marketintel-key.pem ~/.ssh/
   chmod 400 ~/.ssh/marketintel-key.pem
   ```
2. Note the **Public IPv4 address** from the EC2 Console.
3. Connect:
   ```bash
   ssh -i ~/.ssh/marketintel-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
   ```

> [!NOTE]
> The `.pem` file is already excluded by `.gitignore`. Never commit it to Git.

---

## PART E — Server Bootstrap (One-Time)

Run on the EC2 instance as the `ubuntu` user:

```bash
# 1. Update the repository URL inside the script first
nano /tmp/setup_ec2.sh
# (paste the contents of deploy/aws/setup_ec2.sh)
# Change REPO_URL to your actual GitHub repository URL

sudo bash /tmp/setup_ec2.sh
```

The script installs: `python3`, `python3-venv`, `nginx`, `git`, `build-essential`, `libpq-dev`, `certbot`, `fail2ban`, `ufw`.

It creates the `marketintel` user and clones your repository to `/opt/marketintel/repo`.

---

## PART F — Production Environment File

Create the `.env` file on the server. This file is NEVER in Git.

```bash
sudo -u marketintel nano /opt/marketintel/.env
```

Fill in the following (refer to `backend/.env.example` for all options):

```ini
# Django
SECRET_KEY=<generate with: python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=YOUR_BACKEND_DOMAIN,127.0.0.1,localhost

# ─── Supabase — IMPORTANT: Use the DIRECT connection, NOT Session Pooler ───
# In Supabase Dashboard → Settings → Database → Connection String
# Select "Direct Connection" mode (NOT Session Mode or Transaction Mode)
# The direct connection avoids EMAXCONNSESSION errors on a persistent server.
DATABASE_URL=postgresql://postgres.YOUR_PROJECT_REF:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres

# Mail encryption — MUST be the SAME key used to encrypt existing credentials
MAIL_CREDENTIALS_ENCRYPTION_KEY=<copy from your existing local .env>

# Tracking pixel URL — your final production backend domain
EMAIL_TRACKING_BASE_URL=https://YOUR_BACKEND_DOMAIN
EMAIL_OPEN_TRACKING_ENABLED=true
EMAIL_VERIFICATION_PROVIDER=mx_only

# CORS / CSRF — your static frontend URL
CORS_ALLOWED_ORIGINS=https://YOUR_FRONTEND_DOMAIN.com
CSRF_TRUSTED_ORIGINS=https://YOUR_FRONTEND_DOMAIN.com

# Cloudflare R2 (copy from existing working environment)
USE_OBJECT_STORAGE=true
AWS_ACCESS_KEY_ID=<your R2 access key>
AWS_SECRET_ACCESS_KEY=<your R2 secret key>
AWS_STORAGE_BUCKET_NAME=<your R2 bucket name>
AWS_S3_ENDPOINT_URL=https://<your-account-id>.r2.cloudflarestorage.com
AWS_S3_REGION_NAME=auto
```

Secure the file:
```bash
chmod 600 /opt/marketintel/.env
chown marketintel:marketintel /opt/marketintel/.env
```

---

## PART G — Supabase Direct Connection

> [!IMPORTANT]
> If you were previously using a serverless deployment that relied on Supabase **Session Pooler** on port 5432, it could cause `EMAXCONNSESSION` (max clients reached) errors. A persistent EC2 process holds connections open longer, which can exhaust pooler limits.
>
> For EC2, use the **direct database connection** from Supabase:
>
> 1. Go to Supabase Dashboard → Your Project → **Settings → Database**
> 2. Scroll to **Connection String**
> 3. Select **"Direct connection"** (URI tab)
> 4. Copy the URI — it will look like:
>    `postgresql://postgres.YOURREF:PASSWORD@db.YOURREF.supabase.co:5432/postgres`
> 5. Use this as `DATABASE_URL` in `/opt/marketintel/.env`

The `settings.py` already configures `conn_max_age=600` and `conn_health_checks=True`, which is correct for a persistent Django process.

---

## PART H — systemd Service

```bash
# Copy the service file
sudo cp /opt/marketintel/repo/deploy/aws/marketintel.service /etc/systemd/system/

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable marketintel
sudo systemctl start marketintel

# Check status
sudo systemctl status marketintel
sudo journalctl -u marketintel -n 50
```

---

## PART I — Nginx

```bash
# Copy config
sudo cp /opt/marketintel/repo/deploy/aws/nginx.conf /etc/nginx/sites-available/marketintel

# Replace the placeholder domain
sudo sed -i 's/YOUR_BACKEND_DOMAIN/api.yourdomain.com/g' /etc/nginx/sites-available/marketintel

# Enable site
sudo ln -sf /etc/nginx/sites-available/marketintel /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

---

## PART J — HTTPS with Let's Encrypt

> [!IMPORTANT]
> You need a real domain pointing to the EC2 public IP **before** running certbot.

```bash
sudo certbot --nginx -d YOUR_BACKEND_DOMAIN
```

Certbot will automatically update the Nginx config with the correct certificate paths.

Test auto-renewal:
```bash
sudo certbot renew --dry-run
```

---

## PART K — Cloudflare DNS

Point your backend subdomain to EC2:

**Option A — Cloudflare A Record (recommended):**
1. Cloudflare Dashboard → Your Domain → DNS → Add Record
2. Type: `A`
3. Name: `api` (or whatever subdomain you chose)
4. IPv4: Your EC2 public IP
5. Proxy: **Enabled (orange cloud)** — Cloudflare will handle SSL/TLS

> [!NOTE]
> If using Cloudflare proxy (orange cloud), set Django's `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` — this is already done in `settings.py`.

**Option B — Cloudflare Tunnel (if no static IP):**
```bash
# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Authenticate (opens browser)
cloudflared tunnel login

# Create named tunnel (persistent, not Quick Tunnel)
cloudflared tunnel create marketintel-backend

# Configure (create ~/.cloudflared/config.yml):
#   tunnel: <TUNNEL_ID>
#   credentials-file: /home/ubuntu/.cloudflared/<TUNNEL_ID>.json
#   ingress:
#     - hostname: YOUR_BACKEND_DOMAIN
#       service: http://localhost:8000
#     - service: http_status:404

# Install as systemd service
sudo cloudflared service install
```

---

## PART L — Initial Database Setup

```bash
cd /opt/marketintel/repo/backend
source /opt/marketintel/venv/bin/activate

# Run migrations (reads DATABASE_URL from /opt/marketintel/.env)
python manage.py migrate --noinput

# Create superuser (only first time)
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

---

## PART M — Mail Diagnostics

```bash
cd /opt/marketintel/repo/backend
/opt/marketintel/venv/bin/python manage.py check_mail_configuration
```

Expected output (all PASS):

```
DATABASE
  connection = PASS

────────────────────────────────────────────────────────────
MailAccount ID=1  email=user@example.com

SMTP
  host=smtp.gmail.com  port=587  security=STARTTLS  username=user@gmail.com
  credential_decryption = PASS
  connection = PASS
  starttls = PASS
  authentication = PASS

IMAP
  host=imap.gmail.com  port=993  security=SSL  username=user@gmail.com
  credential_decryption = PASS
  connection = PASS
  authentication = PASS
  inbox_select = PASS
```

If any step shows `FAIL`, do NOT switch the frontend URL yet.

---

## PART N — Deployment Updates

For every code update:

```bash
sudo -u marketintel bash /opt/marketintel/repo/deploy/aws/deploy.sh
```

This pulls the latest code, installs dependencies, runs migrations, collectstatic, and restarts Gunicorn.

---

## PART O — Switch Frontend API URL

Only after ALL diagnostics pass and APIs are verified:

1. In your frontend hosting environment settings, update the `VITE_API_BASE_URL` to point to your new backend:
   ```
   https://YOUR_BACKEND_DOMAIN/api
   ```
2. Redeploy the frontend.

---

## PART P — Full Verification Checklist

Run these checks from the deployed frontend before declaring success:

- [ ] `GET /api/auth/users/me/` — JWT login and token
- [ ] `POST /api/token/` — login returns access + refresh tokens
- [ ] `GET /api/prospects/` — database read
- [ ] `GET /api/companies/` — database read
- [ ] `GET /api/market-events/` — database read
- [ ] `GET /api/auth/mail-account/` — MailAccount retrieval
- [ ] `POST /api/auth/mail-account/{id}/test-smtp/` — SMTP verification
- [ ] `POST /api/auth/mail-account/{id}/test-imap/` — IMAP verification
- [ ] `GET /api/auth/mail-account/fetch_emails/` — IMAP fetch
- [ ] `POST /api/outreach/emails/` — send email
- [ ] `GET /api/email-tracking/{token}/` — tracking pixel is reachable publicly
- [ ] `POST /api/email-verifications/instant-verify/` — email verification

---

## PART Q — Troubleshooting

### Gunicorn not starting
```bash
sudo journalctl -u marketintel -n 100 --no-pager
```

### Nginx errors
```bash
sudo journalctl -u nginx -n 50
sudo nginx -t
```

### Django errors
```bash
# Test outside of systemd with env loaded
sudo -u marketintel bash
source /opt/marketintel/.env
cd /opt/marketintel/repo/backend
/opt/marketintel/venv/bin/python manage.py check --deploy
```

### Database connection error
- Confirm `DATABASE_URL` in `/opt/marketintel/.env` uses the **Supabase direct connection** (not session pooler)
- Test: `psql $DATABASE_URL -c "SELECT 1"`

### SMTP/IMAP credential decryption FAIL
- Verify `MAIL_CREDENTIALS_ENCRYPTION_KEY` in `/opt/marketintel/.env` is identical to the key used locally
- The key must match exactly (no extra spaces or newlines)

### 502 Bad Gateway from Nginx
- Gunicorn is not running: `sudo systemctl start marketintel`
- Check if Gunicorn is listening: `ss -tlnp | grep 8000`

### UFW blocking SSH
```bash
# If you get locked out, use AWS EC2 Instance Connect from the Console
# Then: sudo ufw allow 22
```

---

## Rollback Procedure

If EC2 deployment fails or introduces regressions:

1. SSH into your EC2 instance.
2. Navigate to `/opt/marketintel/repo`.
3. Check out the previous stable git commit or tag.
4. Run `sudo -u marketintel bash deploy/aws/deploy.sh` to redeploy the previous stable state.
5. If the issue is with the instance itself, provision a new instance from a previous working AMI snapshot and update your DNS records to point to the new IP.

---

## AWS Resources Created

| Resource | Type | Free Tier Eligible |
|---|---|---|
| EC2 Instance | t2.micro or t3.micro | ✅ 750 hrs/month (first 12 months) |
| EBS Volume | 8 GB gp3 | ✅ 30 GB included |
| Security Group | Default VPC | ✅ Free |
| Public IPv4 | EC2 public IP | ⚠️ $0.005/hr (new accounts, check Console) |

> [!WARNING]
> AWS now charges for **public IPv4 addresses**. If cost is a concern, use **Cloudflare Tunnel (Option B)** which does not require a static IP and has no IP-related AWS charges.

No Load Balancer, NAT Gateway, RDS, ElastiCache, EKS, or other paid services are required.
