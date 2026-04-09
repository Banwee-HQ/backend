#!/usr/bin/env bash
# Usage: ./start-app.sh [dev|prod]
# Default: dev

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()    { echo -e "${BLUE}[STEP]${NC} $1"; }

MODE="${1:-dev}"

# Load the right env file
case "$MODE" in
  dev|development)
    ENV_FILE=".env.dev"
    export ENVIRONMENT=dev
    ;;
  prod|production)
    ENV_FILE=".env.prod"
    export ENVIRONMENT=prod
    ;;
  *)
    print_error "Unknown mode: $MODE"
    echo "Usage: ./start-app.sh [dev|prod]"
    exit 1
    ;;
esac

echo "🚀 Starting Banwee Backend ($MODE)..."
echo "=================================="

# Load env file
if [ -f "$ENV_FILE" ]; then
  print_status "Loading $ENV_FILE"
  set -a; source "$ENV_FILE"; set +a
elif [ -f ".env" ]; then
  print_warning "$ENV_FILE not found, falling back to .env"
  set -a; source ".env"; set +a
else
  print_error "No env file found ($ENV_FILE or .env)"
  exit 1
fi

# Validate required vars
print_step "Verifying environment..."
if [ -z "$DATABASE_URL" ]; then
  print_error "DATABASE_URL is not set"
  exit 1
fi
if [ -z "$SECRET_KEY" ]; then
  print_error "SECRET_KEY is not set"
  exit 1
fi
print_status "Environment OK"

# Check Python
if ! command -v python3 &> /dev/null; then
  print_error "Python 3 is not installed"
  exit 1
fi

# Parse host and port from BACKEND_URL (e.g. http://localhost:8000)
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
HOST=$(echo "$BACKEND_URL" | sed -E 's|https?://([^:/]+).*|\1|')
PORT=$(echo "$BACKEND_URL" | sed -E 's|.*:([0-9]+).*|\1|')
# If no port found in URL, default to 8000
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then PORT=8000; fi

# Start server
print_step "Starting server in $MODE mode..."
print_status "API: $BACKEND_URL"
print_status "Docs: $BACKEND_URL/docs"
echo ""

case "$MODE" in
  dev|development)
    uvicorn main:app --host "$HOST" --port "$PORT" --reload
    ;;
  prod|production)
    WORKERS="${WORKERS:-4}"
    print_status "Workers: $WORKERS"
    gunicorn main:app \
      --workers "$WORKERS" \
      --worker-class uvicorn.workers.UvicornWorker \
      --bind "$HOST:$PORT" \
      --log-level info \
      --access-logfile - \
      --error-logfile -
    ;;
esac
