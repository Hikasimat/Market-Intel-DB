#!/usr/bin/env bash
# =============================================================================
# deploy/aws/setup_ec2.sh
# One-time bootstrap for a fresh Ubuntu EC2 instance.
# Run as root (or with sudo) on first SSH login.
#
# Usage:
#   sudo bash setup_ec2.sh
# =============================================================================
set -euo pipefail

APP_USER="marketintel"
APP_DIR="/opt/marketintel"
REPO_URL="https://github.com/YOUR_GITHUB_USER/YOUR_REPO_NAME.git"  # ← CHANGE THIS

echo "=== [1/8] System packages ==="
apt-get update -y
apt-get install -y \
    python3 python3-venv python3-pip \
    nginx git curl \
    build-essential libpq-dev \
    certbot python3-certbot-nginx \
    ufw fail2ban

echo "=== [2/8] Create application user ==="
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --create-home --home-dir "$APP_DIR" "$APP_USER"
    echo "Created user: $APP_USER"
else
    echo "User $APP_USER already exists"
fi

echo "=== [3/8] Application directory ==="
mkdir -p "$APP_DIR"
chown "$APP_USER:$APP_USER" "$APP_DIR"

echo "=== [4/8] Clone repository ==="
if [ ! -d "$APP_DIR/repo" ]; then
    sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR/repo"
else
    echo "Repository already cloned — run deploy.sh to update"
fi

echo "=== [5/8] Python virtual environment ==="
if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
fi

echo "=== [6/8] Install Python dependencies ==="
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/repo/backend/requirements.txt"

echo "=== [7/8] UFW firewall ==="
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
# CRITICAL: allow SSH before enabling UFW to avoid lockout
echo "y" | ufw enable
ufw status

echo "=== [8/8] systemd services ==="
cp "$APP_DIR/repo/deploy/aws/marketintel.service" /etc/systemd/system/marketintel.service
cp "$APP_DIR/repo/deploy/aws/marketintel-worker.service" /etc/systemd/system/marketintel-worker.service
systemctl daemon-reload
systemctl enable marketintel
systemctl enable marketintel-worker

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Create /opt/marketintel/.env (see backend/.env.example)"
echo "  2. Copy nginx.conf to /etc/nginx/sites-available/marketintel"
echo "  3. Enable nginx site and test"
echo "  4. Run: sudo systemctl start marketintel"
echo "  5. Run: sudo systemctl start marketintel-worker"
echo "  6. Run: sudo bash deploy.sh"
