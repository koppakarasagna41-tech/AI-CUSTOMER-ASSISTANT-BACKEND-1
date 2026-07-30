import asyncio
import os
from pathlib import Path
from typing import List, Tuple

from fastapi import UploadFile

from app.database.mongodb import connect_to_mongo, get_database
from app.knowledge.services import upload_service
from app.rag.services.rag_service import run_ask_pipeline


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_FILES = [
    ("Employee Handbook", BASE_DIR / "employee_handbook.txt"),
    ("Product Manual", BASE_DIR / "product_manual.txt"),
    ("FAQ", BASE_DIR / "faq.txt"),
    ("Refund Policy", BASE_DIR / "refund_policy.txt"),
    ("Shipping Policy", BASE_DIR / "shipping_policy.txt"),
]


async def upload_documents() -> List[dict]:
    await connect_to_mongo()
    db = get_database()
    docs_col = db["knowledge_documents"]
    chunks_col = db["knowledge_chunks"]

    uploaded = []
    for title, path in SAMPLE_FILES:
        with path.open("rb") as handle:
            upload_file = UploadFile(filename=path.name, file=handle)
            doc = await upload_service.handle_file_upload(
                file=upload_file,
                category="sample",
                description=f"Sample knowledge document: {title}",
                tags=[title.lower().replace(" ", "_")],
                uploaded_by="sample-loader",
                docs_col=docs_col,
                chunks_col=chunks_col,
            )
            uploaded.append({"title": title, "document_id": doc["document_id"], "status": doc.get("status")})

    for item in uploaded:
        for _ in range(60):
            doc = await docs_col.find_one({"document_id": item["document_id"]})
            if doc and doc.get("status") in {"COMPLETED", "FAILED"}:
                item["status"] = doc.get("status")
                break
            await asyncio.sleep(1)

    return uploaded


async def verify_answers() -> List[Tuple[str, str, list[dict]]]:
    questions = [
        ("What is the refund window for returned products?", "30 days"),
        ("How long does standard shipping take?", "3 to 5 business days"),
        ("How do I reset my password?", "password reset link"),
    ]

    results = []
    for question, expected in questions:
        result = await run_ask_pipeline(question=question, top_k=3)
        results.append((question, result.answer, result.sources))
        print(f"\nQ: {question}")
        print(f"A: {result.answer}")
        print(f"Expected contains: {expected}")
        print(f"Sources: {[s.get('filename') for s in result.sources]}")
    return results


async def main() -> None:
    uploaded = await upload_documents()
    print("Uploaded sample documents:")
    for item in uploaded:
        print(f"- {item['title']}: {item['document_id']} -> {item['status']}")

    await verify_answers()


if __name__ == "__main__":
    asyncio.run(main())
