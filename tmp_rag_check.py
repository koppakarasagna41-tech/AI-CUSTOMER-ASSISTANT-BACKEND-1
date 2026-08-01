import asyncio
from app.database.mongodb import connect_to_mongo, get_database
from app.rag.embeddings.query_embedder import embed_query
from app.rag.retrieval.similarity_search import similarity_search

async def main():
    await connect_to_mongo()
    db = get_database()
    vector = await embed_query('How do I request a refund?')
    chunks = await similarity_search(vector, top_k=3, category='policy')
    print('vector_dims', len(vector))
    print('chunk_count', len(chunks))
    for c in chunks:
        print(c.chunk_id, c.document_id, round(c.similarity, 4), c.content[:120])
    db.client.close()

asyncio.run(main())
