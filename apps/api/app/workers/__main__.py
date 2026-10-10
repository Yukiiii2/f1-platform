"""Explicit worker CLI, independent of FastAPI/its reload processes."""

import argparse
import json
import logging
import time
from uuid import UUID

from sqlalchemy import select

from app import models
from app.core.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.providers.jolpica import JolpicaProvider
from app.providers.openf1 import OpenF1Provider
from app.workers.sessions import (
    POLL_SECONDS,
    register_session,
    retry_session,
    run_once,
    worker_lock,
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Historical finalization and opt-in provisional near-live updates"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--register", action="store_true")
    mode.add_argument("--retry", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--watch", action="store_true")
    parser.add_argument(
        "--session", type=UUID, help="Existing application session UUID"
    )
    parser.add_argument(
        "--source-session", type=int, help="Explicit OpenF1 session key"
    )
    parser.add_argument("--driver", action="append", default=[], metavar="NUMBER=UUID")
    parser.add_argument("--poll-seconds", type=int, default=POLL_SECONDS)
    parser.add_argument(
        "--live", action="store_true", help="Enable near-live refresh on registration"
    )
    parser.add_argument("--live-poll-seconds", type=int, default=None)
    args = parser.parse_args()
    if args.live and not args.register:
        parser.error("--live is only supported with --register")
    if args.live_poll_seconds is not None and not 60 <= args.live_poll_seconds <= 300:
        parser.error("--live-poll-seconds must be between 60 and 300")
    if args.poll_seconds < 900:
        parser.error("--poll-seconds must be at least 900 (default: 1800)")
    if (args.register or args.retry) and args.session is None:
        parser.error("--session is required for registration/retry")
    if args.register and (not args.source_session or not args.driver):
        parser.error(
            "Registration requires --source-session and explicit --driver mappings"
        )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        factory = get_session_factory()
        if args.status:
            with factory() as db:
                query = select(models.SessionUpdateJob)
                if args.session:
                    query = query.where(
                        models.SessionUpdateJob.session_id == args.session
                    )
                for job in db.scalars(
                    query.order_by(models.SessionUpdateJob.created_at)
                ):
                    print(
                        json.dumps(
                            {
                                "id": str(job.id),
                                "session_id": str(job.session_id),
                                "status": job.status,
                                "stage": job.stage,
                                "attempts": job.attempt_count,
                                "failures": job.consecutive_failures,
                                "next_attempt_at": job.next_attempt_at.isoformat(),
                                "row_counts": job.row_counts,
                                "failure_category": job.failure_details,
                                "live_enabled": job.live_enabled,
                                "live_suspended": job.live_suspended,
                                "data_status": job.data_status,
                                "live_updated_at": job.live_updated_at.isoformat()
                                if job.live_updated_at
                                else None,
                            }
                        )
                    )
            return 0
        if args.register or args.retry:
            with worker_lock(get_engine()) as acquired:
                if not acquired:
                    print("Another worker is active; retry registration later.")
                    return 1
                if args.retry:
                    retry_session(factory, args.session)
                    print("Session update queued for retry.")
                else:
                    drivers = {}
                    for mapping in args.driver:
                        number, identifier = mapping.split("=", 1)
                        number = int(number)
                        if number in drivers:
                            raise ValueError("Duplicate driver mapping")
                        drivers[number] = UUID(identifier)
                    identifier = register_session(
                        factory,
                        args.session,
                        args.source_session,
                        drivers,
                        live=args.live,
                    )
                    print(f"Session update registered: {identifier}")
            return 0
        settings = get_settings()
        live_interval = args.live_poll_seconds or settings.session_live_poll_seconds
        with (
            JolpicaProvider() as core,
            OpenF1Provider(
                username=settings.openf1_username.get_secret_value()
                if settings.openf1_username
                else None,
                password=settings.openf1_password.get_secret_value()
                if settings.openf1_password
                else None,
            ) as telemetry,
        ):
            while True:
                try:
                    run_once(
                        factory,
                        core,
                        telemetry,
                        interval=args.poll_seconds,
                        live_interval=live_interval,
                    )
                except Exception:
                    # Connection/provider exceptions may contain private configuration.
                    logger.error(
                        "Session worker unavailable; check configuration and migrations"
                    )
                    if args.once:
                        return 1
                if args.once:
                    return 0
                time.sleep(min(args.poll_seconds, live_interval))
    except KeyboardInterrupt:
        return 0
    except Exception:
        print(
            "Session worker failed; check mappings, configuration, "
            "migrations and job status."
        )
        return 1
    finally:
        if get_engine.cache_info().currsize:
            get_engine().dispose()


if __name__ == "__main__":
    raise SystemExit(main())
