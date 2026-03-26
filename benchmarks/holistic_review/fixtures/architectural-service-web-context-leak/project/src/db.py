def execute_query(sql: str) -> list[dict[str, str]]:
    return [{"id": "A-100", "status": "pending", "sql": sql}]