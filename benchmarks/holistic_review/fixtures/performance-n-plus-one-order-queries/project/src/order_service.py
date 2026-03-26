from src.order_repository import fetch_order


def build_dashboard_order_summaries(order_ids: list[int]) -> list[dict[str, int | str]]:
    summaries: list[dict[str, int | str]] = []
    for order_id in order_ids:
        row = fetch_order(order_id)
        summaries.append(
            {
                "id": row["id"],
                "status": row["status"],
                "total_cents": row["total_cents"],
            }
        )
    return summaries