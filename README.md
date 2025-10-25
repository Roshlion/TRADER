# TRADER
Local code + cloud data. Polygon Flat Files -> S3; compute on EC2/SageMaker later.

## Quickstart
1) `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
2) `cp .env.example .env` (fill values)
3) `python scripts/sample_pull.py` (sanity check)
