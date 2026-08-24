#!/usr/bin/env python3
"""从 OpenAlex 增量同步近十年论文，并可选生成中文标题与摘要。

仅使用 Python 标准库。默认保留现有数据并按 OpenAlex ID / DOI 去重。

示例：
    python3 scripts/update_papers.py --queries "robotics" "large language model"
    LIBRETRANSLATE_URL=http://localhost:5000 \
      python3 scripts/update_papers.py --translate libretranslate
    OPENAI_API_KEY=... OPENAI_BASE_URL=https://api.openai.com/v1 \
      python3 scripts/update_papers.py --translate openai
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "papers.json"
DEFAULT_QUERIES = [
    "artificial intelligence",
    "robotics",
    "computer vision",
    "natural language processing",
    "multimodal learning",
]
USER_AGENT = os.getenv(
    "PAPER_LENS_USER_AGENT",
    "PaperLens/1.0 (mailto:paper-lens@example.com)",
)

FIELD_MAP = {
    "computer science": "计算机科学",
    "artificial intelligence": "人工智能",
    "machine learning": "人工智能",
    "natural language processing": "自然语言处理",
    "computer vision": "计算机视觉",
    "robotics": "机器人学",
    "human-computer interaction": "人机交互",
    "medicine": "医学",
    "biology": "生物学",
    "physics": "物理学",
    "chemistry": "化学",
    "engineering": "工程学",
    "mathematics": "数学",
    "environmental science": "环境科学",
    "social sciences": "社会科学",
}


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt + 1 == retries:
                raise RuntimeError(f"请求失败：{url}: {exc}") from exc
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positioned = [(position, word) for word, positions in index.items() for position in positions]
    return " ".join(word for _, word in sorted(positioned))


def clean_openalex_id(value: str | None) -> str:
    return (value or "").rsplit("/", 1)[-1]


def normalize_doi(value: str | None) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value or "", flags=re.I).lower()


def classify_field(work: dict[str, Any]) -> str:
    topic = work.get("primary_topic") or {}
    candidates = [
        topic.get("display_name", ""),
        (topic.get("field") or {}).get("display_name", ""),
        (topic.get("domain") or {}).get("display_name", ""),
    ]
    text = " ".join(candidates).lower()
    for source, translated in FIELD_MAP.items():
        if source in text:
            return translated
    return candidates[1] or candidates[2] or "跨学科"


def popularity(citations: int, year: int, current_year: int) -> int:
    """知名度：引用对数为主，辅以新近程度，范围 0—100。"""
    citation_score = min(1.0, math.log1p(max(citations, 0)) / math.log1p(5000))
    recency_score = max(0.0, 1 - (current_year - year) / 10)
    return round((citation_score * 0.82 + recency_score * 0.18) * 100)


def work_to_paper(work: dict[str, Any], current_year: int) -> dict[str, Any]:
    authors = [
        item.get("author", {}).get("display_name", "")
        for item in work.get("authorships", [])
        if item.get("author", {}).get("display_name")
    ]
    topics = [
        topic.get("display_name")
        for topic in work.get("topics", [])[:4]
        if topic.get("display_name")
    ]
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    best_oa = work.get("best_oa_location") or {}
    citations = int(work.get("cited_by_count") or 0)
    year = int(work.get("publication_year") or current_year)
    doi = normalize_doi(work.get("doi"))
    return {
        "id": f"openalex-{clean_openalex_id(work.get('id'))}",
        "doi": doi,
        "title": work.get("display_name") or work.get("title") or "Untitled",
        "title_zh": "",
        "authors": authors[:12],
        "year": year,
        "venue": source.get("display_name") or work.get("type_crossref") or "OpenAlex",
        "field": classify_field(work),
        "topics": topics,
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "abstract_zh": "",
        "citations": citations,
        "popularity": popularity(citations, year, current_year),
        "open_access": bool((work.get("open_access") or {}).get("is_oa")),
        "pdf_url": best_oa.get("pdf_url") or "",
        "url": best_oa.get("landing_page_url")
        or best_oa.get("pdf_url")
        or location.get("landing_page_url")
        or (f"https://doi.org/{doi}" if doi else work.get("id")),
    }


def fetch_works(
    queries: list[str],
    *,
    per_query: int,
    start_year: int,
    end_year: int,
    polite_email: str | None,
) -> list[dict[str, Any]]:
    works: dict[str, dict[str, Any]] = {}
    for query in queries:
        cursor = "*"
        fetched = 0
        print(f"同步：{query}", flush=True)
        while fetched < per_query:
            batch_size = min(100, per_query - fetched)
            params = {
                "filter": (
                    f"from_publication_date:{start_year}-01-01,"
                    f"to_publication_date:{end_year}-12-31,"
                    f"has_abstract:true,title_and_abstract.search:{query}"
                ),
                # 自动任务优先发现新论文；知名度排序由前端基于引用数完成。
                "sort": "publication_date:desc",
                "per-page": batch_size,
                "cursor": cursor,
                "select": (
                    "id,doi,display_name,publication_year,authorships,primary_location,"
                    "best_oa_location,open_access,cited_by_count,abstract_inverted_index,"
                    "primary_topic,topics,type_crossref"
                ),
            }
            if polite_email:
                params["mailto"] = polite_email
            url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
            payload = request_json(url)
            results = payload.get("results", [])
            if not results:
                break
            for work in results:
                works[clean_openalex_id(work.get("id"))] = work
            fetched += len(results)
            cursor = payload.get("meta", {}).get("next_cursor")
            if not cursor or len(results) < batch_size:
                break
            time.sleep(0.15)
    return list(works.values())


class Translator:
    def __init__(self, provider: str):
        self.provider = provider
        self.cache: dict[str, str] = {}
        self.cache_file = ROOT / "data" / "translation_cache.json"
        if self.cache_file.exists():
            try:
                self.cache = json.loads(self.cache_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print("警告：翻译缓存损坏，将重新生成", file=sys.stderr)

    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text in self.cache:
            return self.cache[text]
        if self.provider == "libretranslate":
            translated = self._libretranslate(text)
        elif self.provider == "openai":
            translated = self._openai(text)
        else:
            return ""
        self.cache[text] = translated
        self.cache_file.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return translated

    def _libretranslate(self, text: str) -> str:
        base_url = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000").rstrip("/")
        payload = {
            "q": text,
            "source": "en",
            "target": "zh",
            "format": "text",
        }
        api_key = os.getenv("LIBRETRANSLATE_API_KEY")
        if api_key:
            payload["api_key"] = api_key
        return request_json(f"{base_url}/translate", method="POST", payload=payload)["translatedText"]

    def _openai(self, text: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("使用 openai 翻译时必须设置 OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": "将学术文本准确、简洁地翻译成简体中文。只返回译文，不添加说明。",
                },
                {"role": "user", "content": text},
            ],
        }
        result = request_json(
            f"{base_url}/chat/completions",
            method="POST",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        return result["choices"][0]["message"]["content"].strip()


def merge_papers(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for paper in existing:
        key = normalize_doi(paper.get("doi")) or paper.get("id", "")
        by_key[key] = paper
    for paper in incoming:
        key = normalize_doi(paper.get("doi")) or paper.get("id", "")
        old = by_key.get(key, {})
        # 保留人工或先前机器生成的汉译，其余字段以学术源最新值为准。
        paper["title_zh"] = old.get("title_zh") or paper.get("title_zh", "")
        paper["abstract_zh"] = old.get("abstract_zh") or paper.get("abstract_zh", "")
        by_key[key] = {**old, **paper}
    return sorted(by_key.values(), key=lambda item: (item.get("year", 0), item.get("citations", 0)), reverse=True)


def load_dataset() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return {"meta": {}, "papers": []}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def atomic_write(payload: dict[str, Any]) -> None:
    temp_file = DATA_FILE.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(DATA_FILE)


def main() -> None:
    now = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description="增量同步 Paper Lens 论文数据")
    parser.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES, help="OpenAlex 搜索词")
    parser.add_argument("--per-query", type=int, default=40, help="每个搜索词最多抓取数")
    parser.add_argument("--start-year", type=int, default=now.year - 9)
    parser.add_argument("--end-year", type=int, default=now.year)
    parser.add_argument("--email", default=os.getenv("OPENALEX_EMAIL"), help="OpenAlex polite pool 邮箱")
    parser.add_argument("--translate", choices=["none", "libretranslate", "openai"], default="none")
    parser.add_argument("--translate-limit", type=int, default=30, help="单次最多翻译多少篇")
    parser.add_argument("--replace", action="store_true", help="不保留既有论文，仅写入本轮数据")
    args = parser.parse_args()

    if args.start_year > args.end_year:
        parser.error("--start-year 不能晚于 --end-year")
    if args.per_query < 1:
        parser.error("--per-query 必须大于 0")

    raw_works = fetch_works(
        args.queries,
        per_query=args.per_query,
        start_year=args.start_year,
        end_year=args.end_year,
        polite_email=args.email,
    )
    incoming = [work_to_paper(work, now.year) for work in raw_works]
    dataset = load_dataset()
    existing = [] if args.replace else dataset.get("papers", [])
    papers = merge_papers(existing, incoming)

    if args.translate != "none":
        translator = Translator(args.translate)
        translated = 0
        for paper in papers:
            if translated >= args.translate_limit:
                break
            if paper.get("title_zh") and paper.get("abstract_zh"):
                continue
            try:
                if not paper.get("title_zh"):
                    paper["title_zh"] = translator.translate(paper.get("title", ""))
                if not paper.get("abstract_zh"):
                    paper["abstract_zh"] = translator.translate(paper.get("abstract", ""))
                translated += 1
                print(f"已翻译：{paper.get('title', '')[:70]}")
            except RuntimeError as exc:
                print(f"翻译停止：{exc}", file=sys.stderr)
                break

    output = {
        "meta": {
            "updated_at": now.isoformat(),
            "source": "OpenAlex",
            "queries": args.queries,
            "window_years": args.end_year - args.start_year + 1,
            "count": len(papers),
        },
        "papers": papers,
    }
    atomic_write(output)
    print(f"完成：新增/刷新 {len(incoming)} 篇，数据集共 {len(papers)} 篇")
    print(f"写入：{DATA_FILE}")


if __name__ == "__main__":
    main()
