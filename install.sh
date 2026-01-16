#!/bin/bash
# FB Profile Processor - One-Command Installer
# Usage: curl -sSL https://raw.githubusercontent.com/swipswaps/fb-profile-processor/main/install.sh | bash

set -e

REPO_URL="https://github.com/swipswaps/fb-profile-processor.git"
INSTALL_DIR="$HOME/fb-profile-processor"

echo "========================================"
echo "  FB Profile Processor Installer"
echo "========================================"
echo ""

# Check for required tools
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ $1 is required but not installed."
        return 1
    fi
    echo "✅ $1 found"
    return 0
}

echo "🔍 Checking prerequisites..."
echo ""

# Check for git
if ! check_command git; then
    echo ""
    echo "Please install git first:"
    echo "  Ubuntu/Debian: sudo apt install git"
    echo "  macOS: xcode-select --install"
    echo "  Fedora: sudo dnf install git"
    exit 1
fi

# Determine installation method
USE_DOCKER=false
USE_PYTHON=false

if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "✅ Docker found"
    USE_DOCKER=true
elif command -v python3 &> /dev/null; then
    echo "✅ Python3 found"
    USE_PYTHON=true
else
    echo "❌ Neither Docker nor Python3 found."
    echo ""
    echo "Please install one of:"
    echo "  - Docker: https://docs.docker.com/get-docker/"
    echo "  - Python 3.8+: https://www.python.org/downloads/"
    exit 1
fi

echo ""

# Clone or update repository
if [ -d "$INSTALL_DIR" ]; then
    echo "📁 Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --ff-only || echo "⚠️  Could not update, using existing version"
else
    echo "📥 Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""

# Install based on available method
if [ "$USE_DOCKER" = true ]; then
    echo "🐳 Installing with Docker..."
    echo ""
    
    # Build and start
    docker-compose build
    docker-compose up -d
    
    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "📍 Dashboard: http://localhost:8501"
    echo ""
    echo "📋 Useful commands:"
    echo "   cd $INSTALL_DIR"
    echo "   docker-compose logs -f    # View logs"
    echo "   docker-compose restart    # Restart"
    echo "   docker-compose down       # Stop"
    echo ""
    
elif [ "$USE_PYTHON" = true ]; then
    echo "🐍 Installing with Python..."
    echo ""
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "📦 Creating virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate and install
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    
    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "📋 To start the dashboard:"
    echo "   cd $INSTALL_DIR"
    echo "   source venv/bin/activate"
    echo "   streamlit run dashboard_integrated.py --server.port 8501 --server.runOnSave=true 2>&1 | tee /tmp/streamlit.log"
    echo ""
    echo "📍 Dashboard will open at: http://localhost:8501"
    echo ""
    echo "💡 Command breakdown:"
    echo "   --server.port 8501        Predictable port"
    echo "   --server.runOnSave=true   Hot-reload on file changes"
    echo "   2>&1 | tee /tmp/...       Captures logs for troubleshooting"
    echo ""
fi

echo "🔗 Documentation: https://github.com/swipswaps/fb-profile-processor#readme"
echo ""

