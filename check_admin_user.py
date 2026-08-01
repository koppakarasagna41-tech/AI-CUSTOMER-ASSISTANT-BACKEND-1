import asyncio
from app.database.mongodb import connect_to_mongo, close_mongo_connection
from app.database import get_database

async def main():
    await connect_to_mongo()
    try:
        db = get_database()
        user = await db['users'].find_one({'email': 'koppakarasagna41@gmail.com'})
        print(user)
    finally:
        await close_mongo_connection()

asyncio.run(main())
