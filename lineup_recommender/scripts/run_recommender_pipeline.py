from pathlib import Path
import argparse
import subprocess
import sys


CURRENT_FILE = Path(__file__).resolve()
SCRIPTS_DIR = CURRENT_FILE.parent
FEATURE_ROOT = CURRENT_FILE.parents[1]


def run_step(script_name, args=None, required=True):
    if args is None:
        args = []

    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        message = f"Missing script: {script_path}"

        if required:
            raise FileNotFoundError(message)

        print(f"[SKIP] {message}")
        return False

    command = [sys.executable, str(script_path)] + args

    print("\n" + "=" * 80)
    print(f"Running: {' '.join(command)}")
    print("=" * 80)

    result = subprocess.run(
        command,
        cwd=FEATURE_ROOT,
        text=True,
    )

    if result.returncode != 0:
        message = f"Step failed: {script_name}"

        if required:
            raise RuntimeError(message)

        print(f"[WARNING] {message}")
        return False

    print(f"[OK] Finished: {script_name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run the LOFI recommender pipeline and optionally query recommendations."
    )

    parser.add_argument(
        "--artist",
        type=str,
        default=None,
        help="Artist name to query after rebuilding the pipeline.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of recommendations to return.",
    )

    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0,
        help="Minimum confidence score for recommendations.",
    )

    parser.add_argument(
        "--skip-external",
        action="store_true",
        help="Skip external lineup processing.",
    )

    parser.add_argument(
        "--external-required",
        action="store_true",
        help="Fail if external lineup processing fails.",
    )

    parser.add_argument(
        "--query-only",
        action="store_true",
        help="Only run the recommendation query, without rebuilding data.",
    )

    args = parser.parse_args()

    if not args.query_only:
        run_step("build_historical_scores.py")
        run_step("build_lineup_tables.py")
        run_step("build_cooccurrence.py")

        if not args.skip_external:
            run_step(
                "build_external_lineups.py",
                required=args.external_required,
            )
            run_step(
                "build_external_cooccurrence.py",
                required=args.external_required,
            )

    if args.artist:
        run_step(
            "test_recommend_artist.py",
            args=[
                args.artist,
                "--top-n",
                str(args.top_n),
                "--min-confidence",
                str(args.min_confidence),
            ],
            required=True,
        )
    else:
        print("\nPipeline finished. No artist query was provided.")


if __name__ == "__main__":
    main()