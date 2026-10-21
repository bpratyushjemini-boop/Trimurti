"""
NARAD Phase 3.5 — Mac Node Agent CLI Entry Point.
Usage:
    python -m app.node_agent.cli --server https://narad-gqtp.onrender.com --token <node-token>
"""

import argparse
import logging
import os
import sys

from app.node_agent.agent import MacNodeAgent


def main():
    parser = argparse.ArgumentParser(
        description="NARAD Secure Mac Node Agent (Phase 3.5)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--server",
        default=os.getenv("NARAD_SERVER_URL") or os.getenv("NARAD_CLOUD_URL") or "https://narad-gqtp.onrender.com",
        help="URL of the NARAD Cloud backend.",
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="Custom unique node identifier. Defaults to hostname-based ID.",
    )
    parser.add_argument(
        "--node-name",
        default=None,
        help="Human-readable node display name.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Node authentication token (or set NARAD_NODE_TOKEN env var).",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=30.0,
        help="Interval in seconds between heartbeats.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Interval in seconds for command polling.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    agent = MacNodeAgent(
        server_url=args.server,
        node_id=args.node_id,
        node_name=args.node_name,
        token=args.token,
        heartbeat_interval=args.heartbeat_interval,
        poll_interval=args.poll_interval,
    )

    try:
        agent.run()
    except Exception as exc:
        logging.error(f"[CLI] Agent crashed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
