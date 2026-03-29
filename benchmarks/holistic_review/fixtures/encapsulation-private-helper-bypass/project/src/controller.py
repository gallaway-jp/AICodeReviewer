from src.dispatcher import SyncDispatcher


def queue_sync(dispatcher: SyncDispatcher, payload: dict) -> None:
    dispatcher._send(payload)
