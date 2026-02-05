#!/bin/bash
# quick-chat.sh - Fast Q&A with Chitta memory grounding
# Usage: ./quick-chat.sh "your question"

if [ -z "$1" ]; then
    echo "Usage: ./quick-chat.sh 'your question'"
    exit 1
fi

cd /Users/VedicRGI_Worker/chitta
python3 quick-chat.py "$@"
