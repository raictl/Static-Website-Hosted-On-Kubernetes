"""
k8s-autoscaling-demo backend.

Serves the static homepage AND exposes small stress endpoints so the
homepage buttons can generate *real* CPU/memory load on this pod --
enough to actually trigger the HorizontalPodAutoscaler.

Endpoints:
  GET  /                -> index.html
  GET  /api/status       -> current pod name + active stress state
  POST /api/stress/cpu    {"action": "start", "workers": 1-4, "duration": 10-120}
  POST /api/stress/cpu    {"action": "stop"}
  POST /api/stress/memory {"action": "start", "mb": 10-150, "duration": 10-120}
  POST /api/stress/memory {"action": "stop"}
"""

import multiprocessing
import os
import socket
import threading
import time

from flask import Flask, jsonify, request, send_file

app = Flask(__name__, static_folder=".", static_url_path="")

MAX_WORKERS = 4
MAX_DURATION = 120
MAX_MEMORY_MB = 150

POD_NAME = os.environ.get("POD_NAME", socket.gethostname())

# ---- shared state ----
_lock = threading.Lock()
_cpu_processes = []
_cpu_stop_at = 0.0
_memory_block = None
_memory_mb = 0
_memory_stop_at = 0.0


def _burn_cpu(duration):
    """Tight loop that pegs a single core for `duration` seconds."""
    end = time.time() + duration
    x = 0
    while time.time() < end:
        x = (x * x + 1) % 1_000_000_007


def _clear_memory_after(duration):
    global _memory_block, _memory_mb, _memory_stop_at
    time.sleep(duration)
    with _lock:
        _memory_block = None
        _memory_mb = 0
        _memory_stop_at = 0.0


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/api/status")
def status():
    with _lock:
        cpu_active = [p for p in _cpu_processes if p.is_alive()]
        cpu_remaining = max(0, int(_cpu_stop_at - time.time())) if cpu_active else 0
        mem_remaining = max(0, int(_memory_stop_at - time.time())) if _memory_block else 0
        return jsonify(
            {
                "pod_name": POD_NAME,
                "cpu_workers_active": len(cpu_active),
                "cpu_seconds_remaining": cpu_remaining,
                "memory_mb_active": _memory_mb,
                "memory_seconds_remaining": mem_remaining,
                "time": time.time(),
            }
        )


@app.route("/api/stress/cpu", methods=["POST"])
def stress_cpu():
    global _cpu_processes, _cpu_stop_at
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")

    with _lock:
        if action == "stop":
            for p in _cpu_processes:
                if p.is_alive():
                    p.terminate()
            _cpu_processes = []
            _cpu_stop_at = 0.0
            return jsonify({"ok": True, "message": "CPU stress stopped"})

        if action == "start":
            workers = max(1, min(int(data.get("workers", 1)), MAX_WORKERS))
            duration = max(5, min(int(data.get("duration", 30)), MAX_DURATION))

            for p in _cpu_processes:
                if p.is_alive():
                    p.terminate()

            _cpu_processes = [
                multiprocessing.Process(target=_burn_cpu, args=(duration,))
                for _ in range(workers)
            ]
            for p in _cpu_processes:
                p.start()
            _cpu_stop_at = time.time() + duration

            return jsonify(
                {"ok": True, "message": f"Burning CPU with {workers} worker(s) for {duration}s"}
            )

    return jsonify({"ok": False, "message": "action must be 'start' or 'stop'"}), 400


@app.route("/api/stress/memory", methods=["POST"])
def stress_memory():
    global _memory_block, _memory_mb, _memory_stop_at
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")

    with _lock:
        if action == "stop":
            _memory_block = None
            _memory_mb = 0
            _memory_stop_at = 0.0
            return jsonify({"ok": True, "message": "Memory stress stopped"})

        if action == "start":
            mb = max(5, min(int(data.get("mb", 50)), MAX_MEMORY_MB))
            duration = max(5, min(int(data.get("duration", 30)), MAX_DURATION))

            _memory_block = bytearray(mb * 1024 * 1024)
            _memory_mb = mb
            _memory_stop_at = time.time() + duration

            threading.Thread(target=_clear_memory_after, args=(duration,), daemon=True).start()

            return jsonify({"ok": True, "message": f"Allocated {mb}MB for {duration}s"})

    return jsonify({"ok": False, "message": "action must be 'start' or 'stop'"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
