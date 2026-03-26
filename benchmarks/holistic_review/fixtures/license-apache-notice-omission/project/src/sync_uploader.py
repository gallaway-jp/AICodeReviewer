import telemetry_sdk


def upload_metrics(endpoint: str, payload: bytes) -> None:
    client = telemetry_sdk.Client(endpoint)
    client.send(payload)