#!/bin/bash
# Activate the virtual environment if it isn't already active.
if [[ -z "${VIRTUAL_ENV}" && -f "venv/bin/activate" ]]; then
    source venv/bin/activate
fi

echo "Running in dev mode on port ${PORT:-8080}"
python -m uvicorn main:app --reload --env-file .env --port "${PORT:-8080}"