from threading import BoundedSemaphore


DB_POOL_SIZE = 8
_pool_gate = BoundedSemaphore(DB_POOL_SIZE)


def borrow_connection():
    _pool_gate.acquire()
    return object()


def release_connection(connection) -> None:
    _pool_gate.release()