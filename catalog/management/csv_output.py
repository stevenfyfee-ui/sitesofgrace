"""CSV output for the read-only report commands, to a file or the console.

The DigitalOcean console can't download files, so every report command takes
--out - to print the CSV itself to the console (stdout), ready to copy out.
The one-line summary then goes to stderr, so the copied CSV stays clean.
"""
import io
from contextlib import contextmanager

STDOUT = "-"


@contextmanager
def csv_destination(path, command):
    """A text file handle for csv.writer: the file at `path`, or a buffer that
    is printed to the command's stdout when `path` is "-"."""
    if path == STDOUT:
        buffer = io.StringIO()
        yield buffer
        command.stdout.write(buffer.getvalue(), ending="")
    else:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            yield fh


def summary(command, path, message):
    """The summary line: stderr when the CSV itself is on stdout."""
    (command.stderr if path == STDOUT else command.stdout).write(message)


def describe(path):
    return "the console" if path == STDOUT else path
