import logging
import queue

from aicodereviewer.gui.widgets import QueueLogHandler


def test_queue_log_handler_emits_level_and_message() -> None:
    log_queue: queue.Queue[tuple[int, str]] = queue.Queue()
    handler = QueueLogHandler(log_queue)
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("tests.gui_logging.queue_handler")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    logger.info("hello gui log")

    level, message = log_queue.get_nowait()
    assert level == logging.INFO
    assert message == "hello gui log"