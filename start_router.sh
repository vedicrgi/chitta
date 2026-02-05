#!/bin/bash
# start-router.sh - Start the Chitta Router service
#
# Usage: ./start-router.sh
#
# The router listens on port 18800 for signal-cli webhooks.
# Configure signal-cli with RECEIVE_WEBHOOK_URL=http://localhost:18800/webhook

cd /Users/VedicRGI_Worker/chitta
exec python3 chitta-router.py
