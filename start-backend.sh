#!/bin/bash

# Banwee Backend Startup Script
# This script only starts the backend server without any migrations or database operations

set -e  # Exit on any error

echo "🚀 Starting Banwee Backend..."
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_error ".env file not found!"
    print_error "Please create a .env file with your Neon PostgreSQL and Upstash Redis URLs"
    exit 1
fi

# Load environment variables
source .env

# Verify required environment variables
print_step "Verifying environment configuration..."

if [ -z "$POSTGRES_DB_URL" ]; then
    print_error "POSTGRES_DB_URL is not set in .env file"
    exit 1
fi

if [ -z "$REDIS_URL" ]; then
    print_error "REDIS_URL is not set in .env file"
    exit 1
fi

print_status "Environment variables loaded successfully"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

print_status "Python is installed"


# Start backend server
print_step "Starting backend server..."
print_status "Backend will be available at http://localhost:8000"
print_status "API Documentation will be available at http://localhost:8000/docs"
echo ""

# Start the server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
