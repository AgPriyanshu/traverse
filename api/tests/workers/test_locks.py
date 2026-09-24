import asyncio
import uuid

from api.workers.locks import book_roster_lock


async def test_a_second_run_on_the_same_book_waits_for_the_first() -> None:
    book_id = uuid.uuid4()
    order: list[str] = []
    release = asyncio.Event()

    async def first() -> None:
        async with book_roster_lock(book_id):
            order.append("first-in")
            await release.wait()
            order.append("first-out")

    async def second() -> None:
        async with book_roster_lock(book_id):
            order.append("second-in")

    holder = asyncio.create_task(first())
    await asyncio.sleep(0.2)
    waiter = asyncio.create_task(second())
    await asyncio.sleep(0.3)

    assert order == ["first-in"]

    release.set()
    await asyncio.wait_for(asyncio.gather(holder, waiter), timeout=5)

    assert order == ["first-in", "first-out", "second-in"]


async def test_different_books_do_not_block_each_other() -> None:
    async with book_roster_lock(uuid.uuid4()):
        async with asyncio.timeout(2):
            async with book_roster_lock(uuid.uuid4()):
                pass
