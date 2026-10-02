"""The local web server (Flask). Listens on 127.0.0.1 only.

Security for a local app:
- Host header must be 127.0.0.1:<port> or localhost:<port> (stops DNS-rebinding
  tricks from a website).
- A request carrying an Origin that isn't this app is refused, and no
  cross-origin access is ever granted (no CORS headers).
- Writes (POST) must carry the X-Tomits header, which a foreign page can't add
  without a CORS preflight that this server never approves.
- The page itself loads nothing from outside (Content-Security-Policy 'self').
"""

from __future__ import annotations

import json
import queue
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request

from ..errors import TaskError
from . import actions as _actions  # noqa: F401  (attaches the web handlers to the registry)
from .codecheck import STATIC, FrontEnd, Fingerprint
from .state import build_state

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; media-src 'self' blob:; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'")


def create_app(ctx, port: int) -> Flask:
    # The page served is the one this server started with (see codecheck.py),
    # so its buttons always match this server's command registry.
    front = FrontEnd(STATIC)
    ctx.code_check = getattr(ctx, "code_check", None) or Fingerprint()
    app = Flask(__name__, static_folder=None)
    app.config["JSON_SORT_KEYS"] = False
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    def deny(why: str):
        return jsonify({"ok": False, "error": why}), 403

    @app.before_request
    def guard():
        if request.host not in hosts:
            return deny("This address isn't the local tomits app.")
        origin = request.headers.get("Origin")
        if origin and origin not in origins:
            return deny("Requests from other websites are not allowed.")
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return deny("Requests from other websites are not allowed.")
        if request.method not in ("GET", "HEAD") and request.headers.get("X-Tomits") != "1":
            return deny("Missing the tomits request header.")
        return None

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["Cache-Control"] = "no-store" if request.path.startswith("/api") else "no-cache"
        resp.headers.pop("Access-Control-Allow-Origin", None)
        return resp

    @app.errorhandler(TaskError)
    def refused(e):
        return jsonify({"ok": False, "error": str(e)}), 422

    @app.errorhandler(Exception)
    def crashed(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"ok": False, "error": e.description}), e.code
        return jsonify({"ok": False, "error": f"Something went wrong on the server: {e}"}), 500

    def serve(rel: str):
        hit = front.get(rel)
        if hit is None:
            abort(404)
        return Response(hit[0], content_type=hit[1])

    @app.get("/")
    def index():
        return serve("index.html")

    @app.get("/static/<path:rel>")
    def static_file(rel):
        return serve(rel)

    @app.get("/api/health")
    def health():
        from .. import __version__
        return jsonify({"ok": True, "version": __version__})

    @app.get("/api/state")
    def state():
        return jsonify(build_state(ctx, request.args.to_dict()))

    @app.post("/api/command")
    def command():
        body = request.get_json(silent=True) or {}
        name = body.get("cmd")
        if not isinstance(name, str):
            raise TaskError("No action given.")
        args = body.get("args") or {}
        if not isinstance(args, dict):
            raise TaskError("Bad arguments.")
        return jsonify(ctx.execute(name, args))

    @app.post("/api/say")
    def say():
        body = request.get_json(silent=True) or {}
        text = str(body.get("text") or "")[:500]
        try:
            confidence = float(body.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        conv = body.get("conv")
        return jsonify(ctx.conversations.say(text, confidence, None, int(conv) if conv else None))

    @app.get("/api/voice/status")
    def voice_status():
        return jsonify(ctx.stt_status())

    @app.post("/api/voice/transcribe")
    def transcribe():
        import numpy as np
        try:
            rate = int(request.args.get("rate", "16000"))
        except ValueError:
            rate = 16000
        raw = request.get_data(cache=False)
        if len(raw) > 16000 * 2 * 60:          # over a minute of 16 kHz audio
            raise TaskError("That recording is too long (one minute at most).")
        samples = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
        heard = ctx.transcribe(samples, rate)
        return jsonify({"ok": True, "text": heard.text, "confidence": heard.confidence,
                        "low": heard.confidence < 0.6})

    @app.get("/api/events")
    def events():
        q = ctx.hub.subscribe()

        def stream():
            try:
                yield f"event: hello\ndata: {json.dumps({'version': ctx.hub.version})}\n\n"
                while True:
                    try:
                        yield q.get(timeout=15)
                    except queue.Empty:
                        yield ": ping\n\n"
            finally:
                ctx.hub.unsubscribe(q)

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    return app
