"""Start the tomits web app: python -m tomits.web [--port N] [--no-browser] [--db PATH]

Picks port 3000, or the next free one, binds 127.0.0.1 only, opens the browser.
"""

from __future__ import annotations

import os
import argparse
import socket
import sys
import webbrowser

DEFAULT_PORT = 3000


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: don't share a port someone else holds
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def find_port(start: int = DEFAULT_PORT, tries: int = 100) -> int:
    for port in range(start, start + tries):
        if port_is_free(port):
            return port
    raise RuntimeError(f"No free port between {start} and {start + tries - 1}.")


# HOST = "127.0.0.1"  # never a network address: nobody else on the network can open tomits change made for cca2
HOST = os.environ.get("TOMITS_HOST", "127.0.0.1")  # localhost unless the container sets TOMITS_HOST

def build_server(ctx, port: int):
    from werkzeug.serving import WSGIRequestHandler, make_server

    from .server import create_app

    class QuietHandler(WSGIRequestHandler):
        def log_request(self, *a, **k):  # no per-request lines in the window
            pass

    return make_server(HOST, port, create_app(ctx, port), threaded=True, request_handler=QuietHandler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tomits web")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    try:
        from ..db import MigrationError
        from .context import WebApp
    except ImportError as e:
        print(f"\nA required package is missing ({e}).\nRun start-tomits.bat again; it installs what's needed.")
        return 3

    try:
        ctx = WebApp(args.db)
    except MigrationError as e:
        print(f"\n{e}")
        return 2
    port = find_port(args.port)
    url = f"http://127.0.0.1:{port}"
    server = build_server(ctx, port)
    print("")
    if port != args.port:
        print(f"Port {args.port} was busy, so tomits is using port {port}.")
    print(f"tomits is running at {url}")
    print("Only this computer can open it. Keep this window open while you use tomits;")
    print("close it (or press Ctrl+C) to stop. Your data is saved as you go.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping tomits. Everything is already saved.")
    finally:
        server.shutdown()
        ctx.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
