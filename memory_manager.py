import os
import re
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class MemoryManager:
    """
    Implements a 'Visual Brain' using Obsidian-style Markdown files
    with Semantic Retrieval using Sentence Embeddings.
    """
    def __init__(self, vault_path: str = "E:\\ai\\memory"):
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.vault_path / "embeddings.json"

        # Initialize embedding model (all-MiniLM-L6-v2 is fast and efficient)
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = self._load_index()

    def _load_index(self) -> Dict[str, List[float]]:
        """Load stored embeddings from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_index(self):
        """Persist embeddings to disk."""
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f)

    def _sanitize_filename(self, name: str) -> str:
        """Convert a topic name into a safe filename."""
        return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").lower()

    def remember(self, topic: str, content: str, category: str = "general", links: List[str] = None):
        """
        Saves a memory as a Markdown file and updates the semantic index.
        """
        links = links or []
        category_path = self.vault_path / category
        category_path.mkdir(parents=True, exist_ok=True)

        filename = f"{self._sanitize_filename(topic)}.md"
        filepath = category_path / filename

        # Generate YAML frontmatter
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = (
            f"---\n"
            f"created: {now}\n"
            f"category: {category}\n"
            f"tags: [memory, {category}]\n"
            f"---"
        )

        # Generate links section
        links_section = "\n\n### Connections\n" + "\n".join([f"- [[{link}]]" for link in links]) if links else ""

        full_content = f"{frontmatter}\n\n# {topic}\n\n{content}{links_section}"

        # Write the Markdown file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

        # Update the semantic index
        embedding = self.model.encode(content).tolist()
        self.index[str(filepath)] = embedding
        self._save_index()

        return str(filepath)

    def recall(self, query: str, top_k: int = 3, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Performs a semantic search over the vault using cosine similarity.
        """
        if not self.index:
            return []

        query_embedding = self.model.encode([query])[0]

        scores = []
        for path, embedding in self.index.items():
            similarity = cosine_similarity([query_embedding], [embedding])[0][0]
            if similarity >= threshold:
                scores.append((path, similarity))

        # Sort by similarity descending
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for path, score in scores[:top_k]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    results.append({
                        "topic": Path(path).stem,
                        "content": content,
                        "path": path,
                        "score": float(score)
                    })
            except Exception:
                continue

        return results

    def reindex_vault(self):
        """Re-scans the entire vault to synchronize the embeddings index."""
        self.index = {}
        for md_file in self.vault_path.rglob("*.md"):
            with open(md_file, "r", encoding="utf-8") as f:
                # Skip frontmatter for embedding
                content = f.read()
                if "---" in content:
                    content = content.split("---", 2)[-1]

                embedding = self.model.encode(content).tolist()
                self.index[str(md_file)] = embedding
        self._save_index()

if __name__ == "__main__":
    # Test Semantic Brain
    mm = MemoryManager()

    # Save some memories
    mm.remember("User Preference: Coding Style", "The user prefers a clean, functional style with heavy use of type hints.", "user")
    mm.remember("Project: Vasco", "Vasco is a Jarvis-like AI assistant for Windows with a Dynamic Island UI.", "project")
    mm.remember("Daily Routine", "The user usually starts their day with a cup of coffee and checks emails at 9 AM.", "user")

    # Test semantic recall
    print("\nSearching for 'favorite way to write code'...")
    # Note: 'favorite way to write code' does not appear in the text, but is semantically similar to 'coding style'
    matches = mm.recall("favorite way to write code")
    for m in matches:
        print(f"Found [{m['score']:.2f}] in {m['topic']}: {m['content'][:100]}...")
