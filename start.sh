set -e  # Exit on any error

echo "Starting Pytitan Service..."

cd "$(dirname "$0")"

if [ ! -f "bin/activate" ]; then
    echo "❌ Virtual environment not found. Please ensure you're in the project root directory."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source bin/activate

# Check if required packages are installed
echo "Checking dependencies..."
python -c "import fastapi, uvicorn" 2>/dev/null || {
    echo "❌ Required packages not found. Installing dependencies..."
    pip install -r requirements.txt
}

# Start the service
echo "Starting FastAPI service on http://localhost:8000"
echo "API documentation available at http://localhost:8000/docs"
echo "Health check available at http://localhost:8000/healthz"
echo ""
echo "Press Ctrl+C to stop the service"
echo ""

# Start uvicorn with reload for development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
