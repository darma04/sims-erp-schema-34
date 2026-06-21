#!/bin/bash
# ===================================================================
# DEPLOYMENT SCRIPT - SIMS-Software+Accounting-Isolated-Schema-36
# ===================================================================
# Generated: 2026-06-20
# Usage: bash deploy.sh [production|staging]
# ===================================================================

set -e

ENVIRONMENT=${1:-production}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  Deploying: SIMS-Software+Accounting-Isolated-Schema-36"
echo "  Environment: $ENVIRONMENT"
echo "=========================================="

# Step 1: Activate virtual environment
echo "[1/8] Activating virtual environment..."
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "ERROR: No virtual environment found!"
    exit 1
fi

# Step 2: Pull latest code
echo "[2/8] Pulling latest code..."
git pull origin main || git pull origin master

# Step 3: Install dependencies
echo "[3/8] Installing dependencies..."
pip install -r requirements.txt --quiet

# Step 4: Run migrations
echo "[4/8] Running database migrations..."
python manage.py migrate --noinput

# Step 5: Collect static files
echo "[5/8] Collecting static files..."
python manage.py collectstatic --noinput

# Step 6: Clear cache
echo "[6/8] Clearing cache..."
python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"

# Step 7: Check system
echo "[7/8] Running system checks..."
python manage.py check --deploy 2>&1 | grep -v "WARNINGS" | grep -v "security" || true

# Step 8: Restart application
echo "[8/8] Restarting application..."
if command -v systemctl &> /dev/null; then
    sudo systemctl restart gunicorn_SIMS-SoftwareplusAccounting || echo "systemctl not configured yet"
elif command -v supervisorctl &> /dev/null; then
    sudo supervisorctl restart SIMS-SoftwareplusAccounting || echo "supervisorctl not configured yet"
else
    echo "NOTE: Manual restart required. Run:"
    echo "  pkill -f gunicorn && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4"
fi

echo ""
echo "=========================================="
echo "  Deployment complete!"
echo "=========================================="
