from __future__ import annotations

from typing import Any

import chromadb

from planectra import config

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def get_collection() -> chromadb.Collection:
    global _client, _collection
    if _collection is None:
        config.VECTORDB_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(config.VECTORDB_DIR))
        _collection = _client.get_or_create_collection(
            name="plans",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_plan(plan_uuid: str, document: str, project_uuid: str, created_at: str) -> None:
    collection = get_collection()
    collection.upsert(
        ids=[plan_uuid],
        documents=[document],
        metadatas=[{"project_uuid": project_uuid, "created_at": created_at}],
    )


def query_similar(
    query_text: str,
    project_uuids: list[str] | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    collection = get_collection()

    if collection.count() == 0:
        return []

    where = None
    if project_uuids:
        if len(project_uuids) == 1:
            where = {"project_uuid": project_uuids[0]}
        else:
            where = {"project_uuid": {"$in": project_uuids}}

    actual_k = min(top_k, collection.count())
    if actual_k == 0:
        return []

    results = collection.query(
        query_texts=[query_text],
        n_results=actual_k,
        where=where,
    )

    plans = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    for i, plan_id in enumerate(ids):
        similarity = 1 - distances[i]  # cosine distance -> similarity
        plans.append({
            "plan_uuid": plan_id,
            "similarity": round(similarity, 3),
            "metadata": metadatas[i] if i < len(metadatas) else {},
        })

    return plans


def plan_exists(plan_uuid: str) -> bool:
    collection = get_collection()
    try:
        result = collection.get(ids=[plan_uuid])
        return len(result["ids"]) > 0
    except Exception:
        return False
