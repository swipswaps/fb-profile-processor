#!/bin/bash
# Start Chrome with remote debugging for Facebook profile enrichment

echo "🌐 Starting Chrome with remote debugging..."
echo ""
echo "IMPORTANT: After Chrome opens:"
echo "  1. Go to facebook.com"
echo "  2. Log in to your Facebook account"
echo "  3. Keep this Chrome window open"
echo "  4. Run: python3 browser_enricher.py --database test_profiles.db"
echo ""
echo "Press Ctrl+C in this terminal to stop Chrome when done."
echo ""

# Kill any existing Chrome with debugging
pkill -f "chrome.*remote-debugging-port=9222" 2>/dev/null

# Start Chrome with debugging
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/google-chrome-debug" \
  --no-first-run \
  --no-default-browser-check \
  "https://www.facebook.com" \
  2>/dev/null &

CHROME_PID=$!

echo "✅ Chrome started (PID: $CHROME_PID)"
echo "✅ Debugging port: 9222"
echo ""
echo "Waiting for Chrome to be ready..."
sleep 3

# Check if Chrome is responding
if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "✅ Chrome debugging port is active"
    echo ""
    echo "📋 Next steps:"
    echo "  1. Log into Facebook in the Chrome window"
    echo "  2. Run: python3 browser_enricher.py --database test_profiles.db"
else
    echo "❌ Chrome debugging port not responding"
    echo "   Try running manually:"
    echo "   google-chrome --remote-debugging-port=9222"
fi

# Keep script running
wait $CHROME_PID

