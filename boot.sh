#!/bin/bash

echo "🛑 STOPPING: Killing old sessions and zombies..."
# Kill existing screens
screen -ls | grep vedic_rgi | cut -d. -f1 | awk '{print $1}' | xargs kill 2>/dev/null

# Kill port hogs
sudo lsof -t -i:18800 | xargs sudo kill -9 2>/dev/null

# Kill heavy models
ollama stop llama-32k:latest

echo "🧹 CLEANING: Freeing VRAM..."
# Optional: Pre-load the correct model
ollama run qwen-7b-32k "System Boot" > /dev/null 2>&1

echo "🚀 STARTING: Launching Chitta Router..."
# Start screen in detached mode (-dmS)
screen -dmS vedic_rgi sudo -u VedicRGI_Worker python3 /Users/VedicRGI_Worker/chitta/chitta-router.py

echo "✅ SUCCESS: System is live in background."
echo "   - View logs:   screen -r vedic_rgi"
echo "   - Stop system: ./boot.sh (it kills old ones automatically)"
