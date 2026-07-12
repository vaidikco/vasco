import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

class MemoryManager:
    """
    Implements a 'Visual Brain' using Obsidian-style Markdown files.
    Memories are stored as .md files with YAML frontmatter and [[WikiLinks]].
    """
    def __init__(self, vault_path: str = "E:\\ai\\memory"):
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """Convert a topic name into a safe filename."""
        return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").lower()

    def remember(self, topic: str, content: str, category: str = "general", links: List[str] = None):
        """
        Saves a memory as a Markdown file in the Obsidian vault.
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

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

        return str(filepath)

    def recall(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches the vault for memories related to the query.
        Returns a list of matching memory fragments.
        """
        results = []
        query = query.lower()

        # Simple keyword search across all .md files in the vault
        for md_file in self.vault_path.rglob("*.md"):
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
                if query in content.lower():
                    results.append({
                        "topic": md_file.stem,
                        "content": content,
                        "path": str(md_file)
                    })

        return results

    def get_all_memories(self) -> List[str]:
        """Returns a list of all memory topics found in the vault."""
        return [f.stem for f in self.vault_path.rglob("*.md")]

if __name__ == "__main__":
    # Test the Visual Brain
    mm = MemoryManager()

    # Remember a user preference
    mm.remember(
        topic="User Preference: Coding Style",
        content="The user prefers a clean, functional style with heavy use of type hints.",
        category="user",
        links=["Python", "Coding Standards"]
    )

    # Remember a project detail
    mm.remember(
        topic="Project: Vasco",
        content="Vasco is a Jarvis-like AI assistant for Windows with a Dynamic Island UI.",
        category="project",
        links=["Python", "PyQt6", "Windows API"]
    )

    # Recall
    print("Recalling 'coding style'...")
    matches = mm.recall("coding style")
    for m in matches:
        print(f"Found in {m['topic']}: {m['content'][:100]}...")
