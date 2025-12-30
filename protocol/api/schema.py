import asyncio
from typing import AsyncGenerator

import strawberry


@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def ticker(self, interval: float = 1.0) -> AsyncGenerator[int, None]:
        counter = 0
        while True:
            yield counter
            counter += 1
            await asyncio.sleep(interval)


schema = strawberry.Schema(query=Query, subscription=Subscription)
