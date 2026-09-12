"""RAG 向量資料庫建置程式。執行：python build_index.py"""

from __future__ import annotations

import json

from ollama_api import embed
from pypdf import PdfReader
from rag_config import CHUNK_SIZE, EMBEDDING_BATCH_SIZE, EMBEDDING_MODEL, INDEX_PATH, ROOT_DIR, SOURCE_DIRS


def split_text(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return [normalized[start : start + CHUNK_SIZE] for start in range(0, len(normalized), CHUNK_SIZE)]


def extract_chunks() -> list[dict]:
    """讀取所有來源 PDF，回傳附帶來源與頁碼的文字片段。"""
    chunks: list[dict] = []
    for source_dir in SOURCE_DIRS:
        for pdf_path in sorted(source_dir.rglob("*.pdf")):
            reader = PdfReader(str(pdf_path))
            for page_number, page in enumerate(reader.pages, start=1):
                for text in split_text(page.extract_text() or ""):
                    if len(text) >= 30:
                        chunks.append(
                            {
                                "source": str(pdf_path.relative_to(ROOT_DIR)).replace("\\", "/"),
                                "page": page_number,
                                "text": text,
                            }
                        )
    return chunks


def create_embeddings(texts: list[str]) -> list[list[float]]:
    return embed(EMBEDDING_MODEL, texts)


def build_index() -> dict:
    """產生並儲存本機向量資料庫；唯一會批次建立文件向量的函式。"""
    chunks = extract_chunks()
    if not chunks:
        raise ValueError("找不到可擷取文字的 PDF；掃描式 PDF 請先做 OCR")
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
        for chunk, embedding in zip(batch, create_embeddings([item["text"] for item in batch])):
            chunk["embedding"] = embedding
        print(f"已建立 {min(start + len(batch), len(chunks))}/{len(chunks)} 個向量")
    index = {"embedding_model": EMBEDDING_MODEL, "chunks": chunks}
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


if __name__ == "__main__":
    index = build_index()
    print(f"完成：{INDEX_PATH.name}（{len(index['chunks'])} 個片段）")
