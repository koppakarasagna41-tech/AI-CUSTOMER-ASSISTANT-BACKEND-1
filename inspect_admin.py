import asyncio
from app.database.mongodb import connect_to_mongo, close_mongo_connection
from app.database import get_database
from app.services.user_service import seed_initial_admin

async def main():
    await connect_to_mongo()
    try:
        db = get_database()
        result = await seed_initial_admin(db['users'])
        print('SEED_RESULT', result)
        user = await db['users'].find_one({'email': 'koppakarasagna41@gmail.com'})
        print('USER', user)
    finally:
        await close_mongo_connection()

asyncio.run(main())
