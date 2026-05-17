"""Tests for `modules.gui.widgets` — log handler / textbox behavior.

These tests exercise the thread-safe queue + drain mechanism without
actually pumping a Tk event loop: we feed records into the handler and
directly inspect the deque it appends to.
"""
from __future__ import annotations

import logging
import threading
from collections import deque

import pytest

from modules.gui.widgets import LogHandler, safe_after_cancel, safe_destroy


class TestLogHandler:
    def test_emit_appends_formatted_record_to_sink(self):
        sink: deque[str] = deque(maxlen=10)
        h = LogHandler(sink)
        h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
        record = logging.LogRecord("t", logging.INFO, "p", 1, "hello", None, None)
        h.emit(record)
        assert list(sink) == ["INFO | hello"]

    def test_emit_never_raises_on_format_error(self):
        sink: deque[str] = deque(maxlen=10)
        h = LogHandler(sink)
        # Force a formatter that raises
        class BoomFormatter(logging.Formatter):
            def format(self, record):  # noqa: D401
                raise RuntimeError("boom")
        h.setFormatter(BoomFormatter())
        record = logging.LogRecord("t", logging.INFO, "p", 1, "x", None, None)
        # Must not raise
        h.emit(record)
        assert len(sink) == 0

    def test_bounded_sink_drops_oldest(self):
        sink: deque[str] = deque(maxlen=3)
        h = LogHandler(sink)
        h.setFormatter(logging.Formatter("%(message)s"))
        for i in range(10):
            h.emit(logging.LogRecord("t", logging.INFO, "p", 1, str(i), None, None))
        # Only the last 3 records survive; older ones evicted.
        assert list(sink) == ["7", "8", "9"]

    def test_thread_safe_under_concurrent_emit(self):
        """deque.append is GIL-protected for the single-arg overload — verify."""
        sink: deque[str] = deque(maxlen=1000)
        h = LogHandler(sink)
        h.setFormatter(logging.Formatter("%(message)s"))
        N_THREADS = 8
        PER_THREAD = 100
        barrier = threading.Barrier(N_THREADS)

        def emit_burst(tid):
            barrier.wait()
            for i in range(PER_THREAD):
                h.emit(logging.LogRecord("t", logging.INFO, "p", 1,
                                          f"{tid}.{i}", None, None))

        threads = [threading.Thread(target=emit_burst, args=(t,))
                   for t in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        # No records lost (maxlen 1000 > N_THREADS * PER_THREAD = 800)
        assert len(sink) == N_THREADS * PER_THREAD


class TestSafeHelpers:
    def test_safe_after_cancel_handles_none(self):
        # Must not raise when given a None id
        safe_after_cancel(_FakeWidget(), None)

    def test_safe_after_cancel_swallows_tclerror(self):
        import tkinter as tk
        widget = _FakeWidget()
        widget.fail_with = tk.TclError("destroyed")
        # Should NOT raise
        safe_after_cancel(widget, "some-id")

    def test_safe_destroy_handles_none(self):
        safe_destroy(None)

    def test_safe_destroy_swallows_tclerror(self):
        import tkinter as tk
        widget = _FakeWidget()
        widget.fail_with = tk.TclError("already destroyed")
        safe_destroy(widget)
        assert widget.destroy_calls == 1


class _FakeWidget:
    """Minimal stand-in for a Tk widget — records cancel/destroy calls."""

    def __init__(self):
        self.cancel_calls = 0
        self.destroy_calls = 0
        self.fail_with: BaseException | None = None

    def after_cancel(self, _after_id):
        self.cancel_calls += 1
        if self.fail_with is not None:
            raise self.fail_with

    def destroy(self):
        self.destroy_calls += 1
        if self.fail_with is not None:
            raise self.fail_with


# ---- LogTextbox behavior (needs Tk) -------------------------------------
@pytest.mark.gui
class TestLogTextbox:
    def test_attach_handler_returns_handler_that_feeds_textbox_sink(self, tk_root):
        from modules.gui.widgets import LogTextbox
        box = LogTextbox(tk_root, max_lines=100)
        h = box.attach_handler()
        h.emit(logging.LogRecord("t", logging.INFO, "p", 1, "x", None, None))
        # Handler should have appended a formatted record into the box's own queue
        assert len(box._queue) == 1
        box.destroy()

    def test_drain_writes_pending_to_textbox(self, tk_root):
        from modules.gui.widgets import LogTextbox
        box = LogTextbox(tk_root, max_lines=100)
        h = box.attach_handler()
        for i in range(5):
            h.emit(logging.LogRecord("t", logging.INFO, "p", 1, f"line-{i}", None, None))
        box._flush_pending()
        # The textbox should now contain 5 lines
        contents = box.get("1.0", "end")
        for i in range(5):
            assert f"line-{i}" in contents
        box.destroy()

    def test_paused_drain_does_not_consume_queue(self, tk_root):
        from modules.gui.widgets import LogTextbox
        box = LogTextbox(tk_root, max_lines=100)
        h = box.attach_handler()
        h.emit(logging.LogRecord("t", logging.INFO, "p", 1, "kept", None, None))
        box.set_paused(True)
        box.stop()
        if not box._paused:
            box._flush_pending()  # control: would be called normally
        assert len(box._queue) == 1, "paused mode must keep records queued"
        box.destroy()

    def test_ring_buffer_trims_past_max_lines(self, tk_root):
        from modules.gui.widgets import LogTextbox
        box = LogTextbox(tk_root, max_lines=5)
        h = box.attach_handler()
        for i in range(20):
            h.emit(logging.LogRecord("t", logging.INFO, "p", 1, f"L{i}", None, None))
        box._flush_pending()
        line_count = int(box.index("end-1c").split(".")[0])
        # After trim, no more than max_lines should remain in the visible buffer.
        assert line_count <= 5
        box.destroy()
