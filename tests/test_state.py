from app.state import AnswerMode, MemoryStateStore


async def test_memory_store_round_trip() -> None:
    store = MemoryStateStore()
    assert await store.get_mode(1, 2) is None

    await store.set_mode(1, 2, AnswerMode.LITERAL)
    assert await store.get_mode(1, 2) is AnswerMode.LITERAL

    await store.set_mode(1, 2, AnswerMode.EXPLAIN)
    assert await store.get_mode(1, 2) is AnswerMode.EXPLAIN
    assert await store.count() == 1

    await store.clear_mode(1, 2)
    assert await store.get_mode(1, 2) is None
