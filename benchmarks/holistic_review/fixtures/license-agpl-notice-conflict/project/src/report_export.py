import networksync


def export_report(destination: str, payload: bytes) -> None:
    client = networksync.Client(destination)
    client.upload(payload)