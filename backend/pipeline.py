"""
Manual pipeline entry point — dev/ops convenience only.

The REAL daily driver is the in-process scheduler in api/main.py
(_daily_pipeline_scheduler): it fetches/matches once per day and delivers
to each user at their chosen digest slot, with per-user day-locks and
admin failure alerts. In production there is nothing to run by hand.

This script just runs the same full pipeline once, immediately, for all
active users — identical to clicking "Run pipeline now" on /admin:

    PYTHONPATH=. python3 pipeline.py
"""
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()

from core.pipeline_runner import run_fetch_and_match

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")


if __name__ == "__main__":
    stats = asyncio.run(run_fetch_and_match())
    print(f"\nDone: {stats}")
