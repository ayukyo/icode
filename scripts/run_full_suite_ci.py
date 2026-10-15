"""GIL-held periodic diagnostics around unchanged unittest default discovery."""
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
        import threading

        stream = sys.stderr
        faulthandler.enable(file=stream, all_threads=True)
        stop = threading.Event()
        errors = []

        def sample():
            try:
                while not stop.wait(TRACE_INTERVAL_SECONDS):
                    stream.write("Periodic full-suite stack sample:\n")
                    stream.flush()
                    faulthandler.dump_traceback(file=stream, all_threads=True)
            except BaseException as error:
                errors.append(error)

        sampler = threading.Thread(target=sample,
                                   name="full-suite-stack-sampler", daemon=True)
        suite_error = None
        try:
            sampler.start()
            runpy.run_module("unittest", run_name="__main__", alter_sys=True)
        except BaseException as error:
            suite_error = error
            raise
        finally:
            # Keep stream alive until a real join; daemon is not cleanup credit.
            for action in (stop.set, sampler.join):
                try:
                    action()
                except BaseException as error:
                    errors.append(error)
            if errors:
                succeeded = (suite_error is None or
                             isinstance(suite_error, SystemExit) and
                             (suite_error.code is None or
                              isinstance(suite_error.code, int) and
                              suite_error.code == 0))
                if succeeded:
                    for error in errors:
                        if not isinstance(error, Exception):
                            raise error
                    raise RuntimeError("full-suite diagnostic sampler failed") from None
                # Never mask an existing suite failure or disclose error values.
                try:
                    stream.write("Full-suite diagnostic sampler failed; preserving suite failure.\n")
                    stream.flush()
                except BaseException:
                    pass
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path


if __name__ == "__main__":
    main()
