#!/usr/bin/env python3
"""Publish *human-approved* PULSE Italia longforms into the existing Android feed.

Immutable approved records are also retained in a separate file so the usual
8-times-daily news refresh cannot discard them. A bot/LLM cannot sign its own
approval. Fail closed and never manufacture approvals.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from scripts import pulse_editorial_engine_v1 as editor
from scripts.pulse_italia_newsroom import italian_official_url


def is_published_feature(item):
    if not isinstance(item, dict):
        return False
    src = item.get("public_source") or {}
    review = item.get("editorial_review") or {}
    chart = item.get("chart_spec") or {}
    table = item.get("table_spec") or {}
    documents = item.get("source_documents") or []
    return (
        item.get("publication_status") == "published" and
        item.get("editorial_status") == "verified" and
        item.get("editorial_format") ==
            "ai_assisted_independently_audited_human_approved" and
        item.get("geographic_scope", {}).get("country_code") == "IT" and
        src.get("role") == "primary_statistical_source" and
        italian_official_url(src.get("url", "")) and
        bool(review.get("reviewer")) and
        bool(review.get("approved_at")) and
        bool(review.get("evidence_sha256")) and
        isinstance(documents, list) and len(documents) >= 1 and
        len(str(documents[0].get("sha256", ""))) == 64 and
        chart.get("status") == "verified" and table.get("status") == "verified" and
        len(chart.get("data") or []) >= 2 and
        len(chart.get("data") or []) == len(table.get("rows") or []) and
        all(str(p.get("period")) == str(q[0]) and
            float(p["value"]) == float(q[1])
            for p, q in zip(chart["data"], table["rows"]))
    )


def overlay_approved(articles_doc, index_doc, store):
    """Idempotent merge; invalid external data NEVER replaces good feed."""
    articles = list(articles_doc.get("articles") or [])
    index = dict(index_doc)
    prior = {x["id"]: x for x in articles if isinstance(x, dict) and x.get("id")}
    added = 0
    reviewed = store.get("articles") or []
    if not isinstance(reviewed, list):
        raise ValueError("approved_store_must_contain_articles")
    for article in reviewed:
        if not is_published_feature(article):
            raise ValueError("approved_article_does_not_pass_feed_gate")
        if not article.get("id", "").startswith("PULSE-EDITORIAL-"):
            raise ValueError("invalid_editorial_id")
        old = prior.get(article["id"])
        if old and old.get("published_at") != article.get("published_at"):
            raise ValueError("published_edition_date_cannot_be_rewritten")
        if not old:
            added += 1
        prior[article["id"]] = article
    articles_doc = {**articles_doc,
                    "articles": sorted(prior.values(),
                                       key=lambda x: x.get("published_at", ""), reverse=True)}
    if reviewed:
        used = set()
        for bucket in ("oggi", "ieri", "archivio"):
            old = index.get(bucket, [])
            if not isinstance(old, list):
                raise ValueError("invalid_news_index")
            index[bucket] = [x for x in old if x not in used and
                             x not in {a["id"] for a in reviewed}]
            used.update(index[bucket])
        # PULSE Android recomputes date buckets from published_at in Rome.
        # Archive membership makes every approved feature visible to the client.
        index["archivio"] += [a["id"] for a in reviewed]
    return articles_doc, index, added


def load_reviewed(folder):
    """Require three independent files for each approval in approved/{id}/."""
    root = Path(folder)
    approved = []
    if not root.is_dir():
        return approved
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or not re.fullmatch(r"[A-Za-z0-9_-]{8,90}", sub.name):
            continue
        names = ["evidence.json", "llama_draft.json", "approval.json"]
        if not all((sub / name).is_file() for name in names):
            continue
        e, d, a = (json.loads((sub / n).read_text(encoding="utf8")) for n in names)
        # A model-generated file must never be allowed to self-sign:
        # explicit reviewer+copy editor, digest and independent review required.
        if (not a.get("copy_editor") or
            not a.get("independent_review_completed") is True or
            not a.get("reviewer") or
            a["reviewer"].strip().lower() in {"llama", "gemini", "pulse-bot", "ai"}):
            raise ValueError("independent_human_copy_review_required:" + sub.name)
        if not (italian_official_url(e.get("source_url")) and
                italian_official_url(e.get("dataset_url"))):
            raise ValueError("non_Italian_source_in_approved_bundle")
        article = editor.publish_article(d, e, a)
        if not is_published_feature(article):
            raise ValueError("published_article_missing_required_provenance")
        approved.append(article)
    if len({a["id"] for a in approved}) != len(approved):
        raise ValueError("duplicated_approved_identity")
    return approved


def update_feed(reviewed_dir, store_path, articles_path, index_path):
    reviewed = load_reviewed(reviewed_dir)
    store_path, articles_path, index_path = map(
        Path, (store_path, articles_path, index_path))
    prior_store = (json.loads(store_path.read_text(encoding="utf8"))
                   if store_path.exists() else {"schema_version": 1, "articles": []})
    by_id = {x["id"]: x for x in prior_store.get("articles", [])}
    for article in reviewed:
        old = by_id.get(article["id"])
        if old is not None and old != article:
            raise ValueError("approved_article_mutated_after_publication")
        by_id[article["id"]] = article
    store = {"schema_version": 1, "articles": sorted(
        by_id.values(), key=lambda x: x.get("published_at", ""), reverse=True)}
    orig_articles = json.loads(articles_path.read_text(encoding="utf8"))
    orig_index = json.loads(index_path.read_text(encoding="utf8"))
    new_articles, new_index, added = overlay_approved(orig_articles, orig_index, store)
    # Write only after every review and format check succeeds.
    editor.write_json(store_path, store)
    editor.write_json(articles_path, new_articles)
    editor.write_json(index_path, new_index)
    return {"new_reviewed": len(reviewed), "added_to_feed": added,
            "durable_published_total": len(by_id)}


def main(argv=None):
    p = argparse.ArgumentParser(description="Publish independently approved Italian features")
    p.add_argument("--reviewed-dir", default="data/editorial_italia/approved")
    p.add_argument("--store", default="data/editorial_italia/published_articles.json")
    p.add_argument("--articles", default="data/news/articles.json")
    p.add_argument("--index", default="data/news/index.json")
    a = p.parse_args(argv)
    print(json.dumps(update_feed(a.reviewed_dir, a.store, a.articles, a.index),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
