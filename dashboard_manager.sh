#!/bin/bash
#
# Dashboard Manager - Start/Stop/Status for Streamlit Apps
# Usage: ./dashboard_manager.sh [start|stop|restart|status]
#
# Ports:
#   8501 - Main dashboard (dashboard_integrated.py)
#   8502 - Alternative/testing
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_FILE="dashboard_integrated.py"
DEFAULT_PORT=8501
PID_FILE="/tmp/streamlit_dashboard_${DEFAULT_PORT}.pid"
LOG_FILE="/tmp/streamlit_dashboard_${DEFAULT_PORT}.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

# Check if port is in use
check_port() {
    local port=$1
    if netstat -tlnp 2>/dev/null | grep -q ":${port} " || \
       ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        return 0  # Port in use
    fi
    return 1  # Port free
}

# Get PID of process using port
get_port_pid() {
    local port=$1
    local pid=$(lsof -ti:${port} 2>/dev/null | head -1)
    echo "$pid"
}

# Check if Streamlit is running
is_running() {
    local port=${1:-$DEFAULT_PORT}
    if check_port $port; then
        return 0
    fi
    return 1
}

# Start dashboard
start_dashboard() {
    local port=${1:-$DEFAULT_PORT}
    
    echo "🚀 Starting Streamlit Dashboard on port $port..."
    
    # Check if already running
    if is_running $port; then
        local existing_pid=$(get_port_pid $port)
        print_warning "Dashboard already running on port $port (PID: $existing_pid)"
        echo "   Use './dashboard_manager.sh restart' to restart"
        echo "   Or  './dashboard_manager.sh stop' to stop"
        return 1
    fi
    
    # Check if dashboard file exists
    if [[ ! -f "$SCRIPT_DIR/$DASHBOARD_FILE" ]]; then
        print_error "Dashboard file not found: $SCRIPT_DIR/$DASHBOARD_FILE"
        return 1
    fi
    
    # Start Streamlit in background
    cd "$SCRIPT_DIR"
    nohup streamlit run "$DASHBOARD_FILE" \
        --server.port=$port \
        --server.headless=true \
        --browser.gatherUsageStats=false \
        > "$LOG_FILE" 2>&1 &
    
    local pid=$!
    echo $pid > "$PID_FILE"
    
    # Wait for startup
    echo "   Waiting for startup..."
    sleep 3
    
    # Verify it's running
    if is_running $port; then
        print_status "Dashboard started successfully!"
        echo ""
        echo "   📊 URL:  http://localhost:$port"
        echo "   📝 Logs: $LOG_FILE"
        echo "   🔢 PID:  $(cat $PID_FILE 2>/dev/null || echo $pid)"
        echo ""
        return 0
    else
        print_error "Failed to start dashboard"
        echo "   Check logs: cat $LOG_FILE"
        return 1
    fi
}

# Stop dashboard
stop_dashboard() {
    local port=${1:-$DEFAULT_PORT}
    
    echo "🛑 Stopping Streamlit Dashboard on port $port..."
    
    # Method 1: Kill by PID file
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            sleep 1
        fi
        rm -f "$PID_FILE"
    fi
    
    # Method 2: Kill by port
    local port_pid=$(get_port_pid $port)
    if [[ -n "$port_pid" ]]; then
        kill "$port_pid" 2>/dev/null
        sleep 1
    fi
    
    # Method 3: Kill all streamlit processes for this file
    pkill -f "streamlit run $DASHBOARD_FILE" 2>/dev/null || true
    
    sleep 1
    
    # Verify stopped
    if ! is_running $port; then
        print_status "Dashboard stopped"
        return 0
    else
        print_warning "Dashboard may still be running, forcing kill..."
        local force_pid=$(get_port_pid $port)
        if [[ -n "$force_pid" ]]; then
            kill -9 "$force_pid" 2>/dev/null
        fi
        sleep 1
        if ! is_running $port; then
            print_status "Dashboard force stopped"
            return 0
        else
            print_error "Failed to stop dashboard"
            return 1
        fi
    fi
}

# Restart dashboard
restart_dashboard() {
    local port=${1:-$DEFAULT_PORT}
    stop_dashboard $port
    sleep 1
    start_dashboard $port
}

# Show status
show_status() {
    echo "📊 Streamlit Dashboard Status"
    echo "=============================="
    echo ""
    
    # Check common ports
    for port in 8501 8502; do
        if is_running $port; then
            local pid=$(get_port_pid $port)
            echo -e "  Port $port: ${GREEN}RUNNING${NC} (PID: $pid)"
        else
            echo -e "  Port $port: ${YELLOW}STOPPED${NC}"
        fi
    done
    
    echo ""
    
    # Show all streamlit processes
    local procs=$(pgrep -af streamlit 2>/dev/null || true)
    if [[ -n "$procs" ]]; then
        echo "📋 Running Streamlit processes:"
        echo "$procs" | while read line; do
            echo "   $line"
        done
    else
        echo "📋 No Streamlit processes running"
    fi
    
    echo ""
    
    # Show log file location
    if [[ -f "$LOG_FILE" ]]; then
        echo "📝 Log file: $LOG_FILE"
        echo "   Last 3 lines:"
        tail -3 "$LOG_FILE" 2>/dev/null | sed 's/^/   /'
    fi
}

# Main
case "${1:-status}" in
    start)
        start_dashboard ${2:-$DEFAULT_PORT}
        ;;
    stop)
        stop_dashboard ${2:-$DEFAULT_PORT}
        ;;
    restart)
        restart_dashboard ${2:-$DEFAULT_PORT}
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status} [port]"
        echo ""
        echo "Commands:"
        echo "  start   - Start the dashboard (default port: 8501)"
        echo "  stop    - Stop the dashboard"
        echo "  restart - Restart the dashboard"
        echo "  status  - Show running status"
        echo ""
        echo "Examples:"
        echo "  $0 start        # Start on port 8501"
        echo "  $0 start 8502   # Start on port 8502"
        echo "  $0 stop         # Stop port 8501"
        echo "  $0 status       # Check status"
        exit 1
        ;;
esac

