class SyncDispatcher:
    def dispatch(self, payload: dict) -> None:
        request = self._build_request(payload)
        self._send(request)

    def _build_request(self, payload: dict) -> dict:
        return {
            "account_id": str(payload["account_id"]),
            "mode": payload["mode"].lower(),
        }

    def _send(self, request: dict) -> None:
        return None
