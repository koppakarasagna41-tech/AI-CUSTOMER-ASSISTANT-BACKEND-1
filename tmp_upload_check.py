import asyncio
import io
from pathlib import Path
from fastapi import UploadFile
from app.knowledge.services.upload_service import handle_file_upload
from app.database.mongodb import connect_to_mongo, get_database

async def main():
    await connect_to_mongo()
    db = get_database()
    docs_col = db['knowledge_documents']
    chunks_col = db['knowledge_chunks']

    sample_path = Path('scripts/sample_knowledge/refund_policy.txt')
    data = sample_path.read_bytes()
    file_obj = UploadFile(filename=sample_path.name, file=io.BytesIO(data))

    result = await handle_file_upload(
        file=file_obj,
        category='policy',
        description='Refund policy sample',
        tags=['test', 'refund'],
        uploaded_by='system',
        docs_col=docs_col,
        chunks_col=chunks_col,
    )
    print('upload_result=', result)

    await asyncio.sleep(30)

    document = await docs_col.find_one({'document_id': result['document_id']})
    chunk_count = await chunks_col.count_documents({'document_id': result['document_id']})
    print('document_status=', document.get('status'))
    print('document_stats=', {k: document.get(k) for k in ['total_chunks', 'embedded_chunks', 'processing_error']})
    print('chunk_count=', chunk_count)

    db.client.close()

asyncio.run(main())
