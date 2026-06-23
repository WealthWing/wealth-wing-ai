#!/bin/bash
echo "Running in dev mode on port ${PORT:-8080}"
python -m uvicorn main:app --reload --env-file .env --port "${PORT:-8080}"