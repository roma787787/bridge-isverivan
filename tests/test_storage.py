from app.db.repository import Storage


async def test_touch_user_is_idempotent_per_user(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    await storage.connect()
    try:
        await storage.touch_user(1, "alice")
        await storage.touch_user(1, "alice_renamed")
        await storage.touch_user(2, "bob")

        stats = await storage.get_stats()
        assert stats.total_users == 2
    finally:
        await storage.close()


async def test_log_query_and_stats(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    await storage.connect()
    try:
        await storage.touch_user(1, "alice")
        await storage.log_query(1, "USDT", matched=True)
        await storage.log_query(1, "ETH", matched=True)
        await storage.log_query(1, "ETH", matched=True)
        await storage.log_query(1, "ZZZZ", matched=False)

        stats = await storage.get_stats()

        assert stats.total_users == 1
        assert stats.queries_today == 4
        assert stats.queries_month == 4
        assert stats.top_today[0] == ("ETH", 2)
    finally:
        await storage.close()
