def list_users_by_status(status: str):
    query = f"SELECT id, email FROM users WHERE status = '{status}' ORDER BY created_at DESC"
    return db.execute(query).fetchall()