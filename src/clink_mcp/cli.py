"""Direct CLI entry point for clink-mcp."""

import argparse
import asyncio
import json
import sys

from clink_mcp.server import execute_clink_call


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clink-cli",
        description="Direct terminal wrapper for clink-mcp requests.",
    )
    parser.add_argument(
        "--tool-args-json",
        required=True,
        help="JSON object matching the clink MCP tool request shape.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Terminal-side downstream CLI timeout in seconds.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.tool_args_json)
    except json.JSONDecodeError as exc:
        print(f"[Error] Invalid JSON for --tool-args-json: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("[Error] --tool-args-json must decode to a JSON object", file=sys.stderr)
        return 2

    result = asyncio.run(execute_clink_call(timeout=args.timeout, **payload))
    print(result)
    return 1 if result.startswith("[Error]") else 0


if __name__ == "__main__":
    raise SystemExit(main())
