"""
WiFi Link — TCP socket client for SenseCAP Indicator

Drop-in replacement for EventSerial: same send_cmd / send_jpeg / collect_events
API but communicates over WiFi TCP instead of USB serial.

Usage:
    # By hostname (mDNS):
    link = WiFiLink("sensecap.local")

    # By IP address:
    link = WiFiLink("192.168.1.42")

    # Then use exactly like EventSerial:
    link.send_cmd({"cmd": "face", "on": True})
    jpeg = open("photo.jpg", "rb").read()
    link.send_jpeg(jpeg)
    events = link.collect_events()
"""

import json
import socket
import time
from typing import Optional


DEFAULT_PORT = 7777
DEFAULT_TIMEOUT = 2.0


class WiFiLink:
    """
    TCP socket client for SenseCAP Indicator WiFi control.

    Interface-compatible with EventSerial from date_pipeline.py so both
    can be used interchangeably in the pipeline.
    """

    def __init__(self, host: str, port: int = DEFAULT_PORT,
                 timeout: float = DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.events: list[dict] = []
        self._recv_buf = b""

    # --- Connection management ---

    def connect(self):
        """Connect to the SenseCAP TCP server."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[WiFiLink] Connecting to {self.host}:{self.port}...")
        self.sock.connect((self.host, self.port))
        print(f"[WiFiLink] Connected!")
        # Read the initial {"status":"connected"} message
        self._read_until_status(timeout=3)

    def drain_boot(self, wait: float = 1.5):
        """
        Compatible with EventSerial.drain_boot().
        For WiFi we just connect if not already connected and drain any
        buffered messages.
        """
        if self.sock is None:
            self.connect()
        time.sleep(wait)
        self._drain_lines()

    def close(self):
        """Close the TCP connection."""
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    # --- Command interface (matches EventSerial) ---

    def send_cmd(self, cmd: dict) -> dict:
        """Send a JSON command and return the response, collecting events."""
        data = json.dumps(cmd, separators=(",", ":")) + "\n"
        self._send_all(data.encode("utf-8"))
        return self._read_until_status(timeout=5)

    def send_jpeg(self, jpeg_bytes: bytes) -> dict:
        """Send a JPEG frame using the image protocol. Returns final status."""
        length = len(jpeg_bytes)

        # Send image command
        cmd = json.dumps({"cmd": "image", "len": length}, separators=(",", ":")) + "\n"
        self._send_all(cmd.encode("utf-8"))

        # Wait for "ready"
        resp = self._read_until_status(timeout=3)
        if resp.get("status") != "ready":
            return resp

        # Send raw JPEG bytes
        self._send_all(jpeg_bytes)

        # Wait for "ok"
        return self._read_until_status(timeout=10)

    def collect_events(self) -> list[dict]:
        """Read any buffered data and return collected events."""
        self._drain_lines()
        events = list(self.events)
        self.events.clear()
        return events

    # --- Internal helpers ---

    def _send_all(self, data: bytes):
        """Send all bytes, retrying on partial sends."""
        if not self.sock:
            raise ConnectionError("Not connected")
        total_sent = 0
        while total_sent < len(data):
            sent = self.sock.send(data[total_sent:])
            if sent == 0:
                raise ConnectionError("Socket send failed")
            total_sent += sent

    def _recv_available(self) -> bytes:
        """Non-blocking receive of whatever's available."""
        if not self.sock:
            return b""
        try:
            self.sock.setblocking(False)
            data = self.sock.recv(4096)
            return data
        except BlockingIOError:
            return b""
        except OSError:
            return b""
        finally:
            self.sock.settimeout(self.timeout)

    def _drain_lines(self):
        """Read all available lines, sorting into events vs responses."""
        data = self._recv_available()
        if data:
            self._recv_buf += data

        while b"\n" in self._recv_buf:
            line, self._recv_buf = self._recv_buf.split(b"\n", 1)
            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
                if "event" in msg:
                    self.events.append(msg)
                # Discard stale status responses during drain
            except json.JSONDecodeError:
                pass

    def _read_until_status(self, timeout: float = 5) -> dict:
        """Read lines until a status response is found, collecting events."""
        if not self.sock:
            return {"status": "error", "msg": "not connected"}

        deadline = time.time() + timeout
        while time.time() < deadline:
            # Try to receive data
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                self.sock.settimeout(min(remaining, 0.5))
                data = self.sock.recv(4096)
                if not data:
                    return {"status": "error", "msg": "connection closed"}
                self._recv_buf += data
            except socket.timeout:
                pass
            except OSError:
                return {"status": "error", "msg": "recv failed"}

            # Process complete lines
            while b"\n" in self._recv_buf:
                line, self._recv_buf = self._recv_buf.split(b"\n", 1)
                text = line.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                    if "event" in msg:
                        self.events.append(msg)
                    elif "status" in msg:
                        return msg
                except json.JSONDecodeError:
                    pass

        return {"status": "timeout"}

    # --- Context manager ---

    def __enter__(self):
        if self.sock is None:
            self.connect()
        return self

    def __exit__(self, *args):
        self.close()
