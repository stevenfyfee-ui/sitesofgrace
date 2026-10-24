"""Run one shell command in the production web component and print its output.

    tools/prod_run.sh "/opt/venv/bin/python manage.py showmigrations home | tail -3"

`doctl apps console` needs a terminal, which a Windows shell can't give it,
so this runs it inside a Linux container (the local tool image that
tools/prod_run.sh builds) under a pseudo-terminal: it sends the command,
reads the output up to an end marker, and prints just that output with
secrets masked (EV[...] values, API tokens, keys, passwords, credentials in
URLs) and the known system-check warning noise dropped. The remote exit code
is passed through.

The access token comes from the DIGITALOCEAN_ACCESS_TOKEN environment
variable (tools/prod_run.sh reads it from doctl's config); it is never
printed. Nothing is written locally.

(The App Platform exec websocket was tried first and refused with 403 from
DigitalOcean's side for every header variant; doctl's own client works.)
"""
import fcntl
import os
import pty
import re
import struct
import termios
import select
import sys
import time
import uuid

APP_ID = os.environ.get("SOG_APP_ID", "d3b34609-ce9d-410d-91b6-9d30044e43f0")
COMPONENT = os.environ.get("SOG_COMPONENT", "sitesofgrace")
TIMEOUT = int(os.environ.get("SOG_TIMEOUT") or "900")

_MASKS = [
    (re.compile(r"EV\[[^\]]*\]"), "EV[****]"),
    (re.compile(r"\b(dop|doo|dor)_v1_[A-Za-z0-9]+"), r"\1_v1_****"),
    (re.compile(r"\b(sk|rk|pk|whsec)_(live|test)_[A-Za-z0-9]+"), r"\1_\2_****"),
    (re.compile(r"(postgres(?:ql)?|redis|mysql)://([^:/\s]+):[^@\s]+@"), r"\1://\2:****@"),
    (re.compile(r"(?i)((?:secret|password|passwd|token|api[_-]?key|access[_-]?key|private[_-]?key)"
                r"[\w-]*\s*[:=]\s*['\"]?)[^\s'\",]+"), r"\1****"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA****"),
]
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[=>]|\r")
# Django system-check warnings every manage.py command prints in this app.
_NOISE = re.compile(
    r"^(<class '.*'>: \(treebeard\.E001\).*"
    r"|wagtailmenus\.\w+: \(wagtailadmin\.W002\).*"
    r"|\s*HINT: Ensure that \w+ uses .*"
    r"|There are no default tabs on non-Page models.*"
    r"|System check identified some issues:|WARNINGS:)$"
)


def mask(text):
    for pattern, replacement in _MASKS:
        text = pattern.sub(replacement, text)
    return text


def run(command):
    if not os.environ.get("DIGITALOCEAN_ACCESS_TOKEN"):
        sys.exit("DIGITALOCEAN_ACCESS_TOKEN is not set (tools/prod_run.sh reads it from doctl's config).")
    marker = f"__SOG_DONE_{uuid.uuid4().hex[:12]}__"
    line = f"cd /app 2>/dev/null; {{ {command} ; }} 2>&1; echo \"{marker}:$?\"; exit\n"
    done = re.compile(re.escape(marker).encode() + rb":(\d+)\r?\n")

    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("doctl", ["doctl", "apps", "console", APP_ID, COMPONENT])
    # A wide terminal, so the echoed command line isn't wrapped.
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 1000, 0, 0))

    buffer, sent, started = b"", False, time.time()
    while time.time() - started < TIMEOUT:
        ready, _, _ = select.select([fd], [], [], 1.0)
        if fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
        # Send once a shell prompt shows (or after 15s regardless).
        if not sent and (re.search(rb"[$#] $", buffer.rstrip(b"\r\n") + b" ") or time.time() - started > 15):
            os.write(fd, line.encode())
            sent = True
        if sent and done.search(buffer.split(line.strip().encode(), 1)[-1]):
            break
    try:
        os.kill(pid, 9)
    except OSError:
        pass

    text = _ANSI.sub("", buffer.decode("utf-8", "replace"))
    # Everything up to and including the echoed command line is the session
    # banner and prompt; the command's output starts after it.
    echoed = text.find(f'echo "{marker}')
    if echoed != -1:
        text = text[text.find(chr(10), echoed) + 1:]
    match = re.search(re.escape(marker) + r":(\d+)", text)
    exit_code = int(match.group(1)) if match else None
    output = text[: match.start()] if match else text
    kept = [row for row in output.split("\n") if not _NOISE.match(row)]
    print(mask("\n".join(kept).strip("\n")))
    if exit_code is None:
        print(f"[prod_run] no end marker within {TIMEOUT}s; output may be incomplete", file=sys.stderr)
        return 2
    print(f"[prod_run] exit {exit_code}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('usage: prod_run.py "<shell command>"')
    sys.exit(run(sys.argv[1]))
