import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="syncctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--workspace", required=True)
    run_parser.add_argument("--apply", action="store_true")
    return parser


def run_sync(workspace: str) -> str:
    return f"sync started for {workspace}"


def main(argv: list[str] | None = None) -> str:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return run_sync(args.workspace)
    raise ValueError("unsupported command")