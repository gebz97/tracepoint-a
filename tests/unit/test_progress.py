import io

from lib.progress import progress, end


def _capture(call):
    buf = io.StringIO()
    import sys

    old = sys.stdout
    sys.stdout = buf
    try:
        call()
    finally:
        sys.stdout = old
    return buf.getvalue()


def test_progress_uses_carriage_return_and_pads_to_width():
    out = _capture(lambda: progress("disks", 3, 10, 1))
    line = out.split("\r")[-1]
    assert line.startswith("[disks] 3/10 hosts | 1 failed")
    assert len(line.rstrip()) >= 3
    assert "\r" in out
    assert "\n" not in out


def test_progress_shrinking_line_is_cleared():
    out = _capture(lambda: progress("disks", 99, 100, 0))
    line = out.split("\r")[-1]
    assert "[disks] 99/100 hosts | 0 failed" in line
    assert line.endswith(" " * 5) or "failed" in line


def test_end_terminates_with_newline():
    out = _capture(lambda: end("disks", 100, 2))
    assert out.endswith("\n")
    assert "done: 100 hosts | 2 failed" in out
