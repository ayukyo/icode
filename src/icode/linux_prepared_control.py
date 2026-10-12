"""Private portable CP observation; it owns no execution or OS resources."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .control import ControlError, ControlPlane, ControlResult

_ERROR = 'Linux prepared control attempt is unavailable'


def _text(value: object) -> bool:
    return (type(value) is str and bool(value.strip())
        and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def _receipt(result: object) -> dict:
    if (type(result) is not ControlResult or type(result.returncode) is not int
            or result.returncode != 0 or type(result.data) is not dict
            or result.data.get('ok') is not True):
        raise ControlError(_ERROR)
    return result.data


def _prepared_control_attempt_binding(
    control: ControlPlane, *, out_dir: Path | str, ticket_id: str, step: str,
    start_result: ControlResult,
) -> tuple[str, Callable[[str], None]]:
    """Capture trusted host coordinates; every observer invocation queries CP."""
    try:
        if (not isinstance(control, ControlPlane) or not _text(ticket_id) or not _text(step)
                or not isinstance(out_dir, (Path, str))
                or (isinstance(out_dir, str) and not _text(out_dir))):
            raise ControlError(_ERROR)
        captured_dir = Path(out_dir)
        data = _receipt(start_result)
        if type(data.get('step')) is not str or data['step'] != step:
            raise ControlError(_ERROR)
        attempt = data.get('attempt')
        if not _text(attempt):
            raise ControlError(_ERROR)
    except Exception:
        raise ControlError(_ERROR) from None

    def observer(actual: str) -> None:
        try:
            if type(actual) is not str or actual != attempt:
                raise ControlError(_ERROR)
            # limit limits displayed records, never the full-chain open_steps view.
            observed = _receipt(control.trace(captured_dir, limit=1))
            if type(observed.get('ticket_id')) is not str or observed['ticket_id'] != ticket_id:
                raise ControlError(_ERROR)
            opened = observed.get('open_steps')
            if type(opened) is not dict:
                raise ControlError(_ERROR)
            entry = opened.get(attempt)
            if (type(entry) is not dict or type(entry.get('step')) is not str
                    or entry['step'] != step):
                raise ControlError(_ERROR)
        except Exception:
            # Fixed, input-free ordinary rejection; KI/SE propagate as original objects.
            raise ControlError(_ERROR) from None

    return attempt, observer
