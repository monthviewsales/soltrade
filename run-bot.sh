#!/bin/bash

# Navigate to the project directory
cd "$(dirname "$0")"

# Check if virtual environment exists, create if necessary
if [ ! -d "env" ]; then
    echo "Creating virtual environment..."
    python3 -m venv env
fi

# Activate the virtual environment
source env/bin/activate

# Run the trading bot
python3 ./soltrade.py