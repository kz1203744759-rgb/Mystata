"""Compatibility launcher for mcp-stata 3.3.0's Windows stdout filter.

Some Stata versions print a prompt without a trailing newline before the JSON-RPC
response. The upstream filter discards that entire line. Keep only a valid
JSON-RPC object at the end of a line and send preceding console noise to stderr.
"""
import json
import os
import sys
import threading

from mcp_stata import server


def install_filter():
    sys.stdout.flush()
    original = os.dup(1)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 1)
    os.close(write_fd)

    def forward():
        pending = b""
        while True:
            chunk = os.read(read_fd, 4096)
            if not chunk:
                break
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                start = line.find(b'{"jsonrpc"')
                if start >= 0:
                    try:
                        obj = json.loads(line[start:])
                        if isinstance(obj, dict) and obj.get("jsonrpc") == "2.0":
                            os.write(original, line[start:] + b"\n")
                            continue
                    except (ValueError, UnicodeError):
                        pass
                os.write(2, line + b"\n")

    threading.Thread(target=forward, daemon=True).start()


if __name__ == "__main__":
    server._install_stdout_filter = install_filter
    server.main()
