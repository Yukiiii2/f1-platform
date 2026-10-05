import argparse
import logging

from app.db.session import get_engine, get_session_factory
from app.ingestion.service import run_import
from app.providers.jolpica import JolpicaProvider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import normalized core F1 data from Jolpica"
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--round", dest="round_number", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        with JolpicaProvider() as provider:
            run_id = run_import(
                provider, get_session_factory(), args.season, args.round_number
            )
        print(f"Import succeeded: {run_id}")
        return 0
    except Exception as error:
        print(
            f"Import failed ({type(error).__name__}); "
            "check DATABASE_URL, migrations and import_runs."
        )
        return 1
    finally:
        if get_engine.cache_info().currsize:
            get_engine().dispose()


if __name__ == "__main__":
    raise SystemExit(main())
