"""Bounded CI diagnostics around the unchanged unittest default discovery."""
import os
import sys

TRACE_INTERVAL_SECONDS = 120


def main():
    original_argv = sys.argv
    original_path = sys.path[:]
    sys.path[0] = os.getcwd()
    sys.argv = ["unittest", "-v"]
    try:
        import faulthandler
        import runpy

        faulthandler.dump_traceback_later(
            TRACE_INTERVAL_SECONDS, repeat=True, file=sys.stderr, exit=False
        )
        try:
            runpy.run_module("unittest", run_name="__main__", alter_sys=True)
        finally:
            faulthandler.cancel_dump_traceback_later()
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path


if __name__ == "__main__":
    main()
