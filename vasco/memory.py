"""Vasco's long-term memory: an Obsidian-style markdown vault with recall.

Improvements over the original:
- Vault defaults to ~/.vasco/memory (cross-platform) instead of E:\\ai\\memory.
- sentence-transformers is loaded lazily and is OPTIONAL — if it isn't
  installed the vault still works using keyword-overlap recall, so the
  2GB torch dependency is never required just to remember things.
- Recall returns note bodies with YAML frontmatter stripped.
- sklearn dependency dropped (cosine similarity is a three-line dot product).
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from vasco.config import config

logger = logging.getLogger("MemoryManager")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "i", "in", "is", "it", "its", "me", "my", "of", "on",
    "or", "that", "the", "this", "to", "was", "were", "what", "when",
    "where", "which", "who", "will", "with", "you", "your",
}


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def _keywords(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOPWORDS}


class MemoryManager:
    """Markdown vault with semantic recall (embeddings) or keyword fallback."""

    def __init__(self, vault_path: Optional[Path] = None):
        self.vault_path = Path(vault_path or config.vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.vault_path / "embeddings.json"
        self.index: Dict[str, List[float]] = self._load_index()
        self._model = None
        self._model_failed = False

    # -- embedding model (lazy, optional) -----------------------------------

    def _get_model(self):
        if self._model is None and not self._model_failed:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading embedding model (first use)...")
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:  # ImportError or download failure
                logger.warning("Semantic memory unavailable (%s); using keyword recall.", e)
                self._model_failed = True
        return self._model

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    # -- index persistence ---------------------------------------------------

    def _load_index(self) -> Dict[str, List[float]]:
        if self.index_path.exists():
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f)

    # -- public API ------------------------------------------------------------

    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").lower()[:80]

    def remember(
        self,
        topic: str,
        content: str,
        category: str = "general",
        links: Optional[List[str]] = None,
    ) -> str:
        """Save a memory as a markdown note and index it."""
        category_path = self.vault_path / category
        category_path.mkdir(parents=True, exist_ok=True)
        filepath = category_path / f"{self._sanitize_filename(topic)}.md"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = (
            f"---\ncreated: {now}\ncategory: {category}\n"
            f"tags: [memory, {category}]\n---"
        )
        links_section = (
            "\n\n### Connections\n" + "\n".join(f"- [[{l}]]" for l in links)
            if links else ""
        )
        filepath.write_text(
            f"{frontmatter}\n\n# {topic}\n\n{content}{links_section}",
            encoding="utf-8",
        )

        model = self._get_model()
        if model is not None:
            self.index[str(filepath)] = model.encode(content).tolist()
            self._save_index()
        return str(filepath)

    def recall(
        self, query: str, top_k: int = 3, threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Find memories relevant to the query."""
        model = self._get_model()
        if model is not None and self.index:
            return self._recall_semantic(query, top_k, threshold)
        return self._recall_keyword(query, top_k)

    def _recall_semantic(self, query: str, top_k: int, threshold: float):
        query_emb = self._get_model().encode(query).tolist()
        scores = []
        for path, emb in self.index.items():
            sim = self._cosine(query_emb, emb)
            if sim >= threshold:
                scores.append((path, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return self._read_results(scores[:top_k])

    def _recall_keyword(self, query: str, top_k: int, min_overlap: int = 1):
        query_words = _keywords(query)
        if not query_words:
            return []
        scores = []
        for md_file in self.vault_path.rglob("*.md"):
            try:
                body = _strip_frontmatter(md_file.read_text(encoding="utf-8"))
            except OSError:
                continue
            overlap = query_words & _keywords(body)
            if len(overlap) >= min_overlap:
                scores.append((str(md_file), len(overlap) / len(query_words)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return self._read_results(scores[:top_k])

    def _read_results(self, scored_paths):
        results = []
        for path, score in scored_paths:
            try:
                content = _strip_frontmatter(Path(path).read_text(encoding="utf-8"))
            except OSError:
                continue
            results.append(
                {
                    "topic": Path(path).stem,
                    "content": content,
                    "path": path,
                    "score": float(score),
                }
            )
        return results

    def reindex_vault(self):
        """Re-embed every note (no-op when embeddings are unavailable)."""
        model = self._get_model()
        if model is None:
            return
        self.index = {}
        for md_file in self.vault_path.rglob("*.md"):
            body = _strip_frontmatter(md_file.read_text(encoding="utf-8"))
            self.index[str(md_file)] = model.encode(body).tolist()
        self._save_index()
