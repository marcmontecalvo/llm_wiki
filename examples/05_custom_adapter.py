"""
Custom Adapter Example

This example demonstrates how to create a custom adapter to ingest
files in formats not supported by default.
"""

import json
from pathlib import Path

from llm_wiki.adapters.base import BaseAdapter


class JSONAdapter(BaseAdapter):
    """
    Custom adapter for JSON files containing structured wiki content.

    Expected JSON format:
    {
      "title": "Page Title",
      "summary": "Brief description",
      "tags": ["tag1", "tag2"],
      "content": "Markdown content here..."
    }
    """

    def can_parse(self, filepath: Path) -> bool:
        """Check if this adapter can parse the given file."""
        return filepath.suffix.lower() == ".json"

    def extract_metadata(self, filepath: Path) -> dict:
        """Extract metadata from JSON file."""
        try:
            data = json.loads(filepath.read_text())

            metadata = {}

            # Extract title (required)
            if "title" in data:
                metadata["title"] = data["title"]
            else:
                # Fallback to filename
                metadata["title"] = filepath.stem.replace("_", " ").replace("-", " ").title()

            # Extract optional fields
            if "summary" in data:
                metadata["summary"] = data["summary"]

            if "tags" in data and isinstance(data["tags"], list):
                metadata["tags"] = data["tags"]

            if "domain" in data:
                metadata["domain"] = data["domain"]

            if "kind" in data:
                metadata["kind"] = data["kind"]

            if "source" in data:
                metadata["source"] = data["source"]

            return metadata

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing JSON file {filepath}: {e}")
            return {}

    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        """Convert JSON content to markdown with frontmatter."""
        try:
            data = json.loads(content)

            # Get metadata
            metadata = self.extract_metadata(filepath)

            # Build frontmatter
            frontmatter_lines = ["---"]
            for key, value in metadata.items():
                if isinstance(value, list):
                    frontmatter_lines.append(f"{key}:")
                    for item in value:
                        frontmatter_lines.append(f"  - {item}")
                else:
                    frontmatter_lines.append(f"{key}: {value}")
            frontmatter_lines.append("---")
            frontmatter_lines.append("")

            # Get content
            markdown_content = str(data.get("content", ""))

            # If no content provided, create basic structure
            if not markdown_content:
                title = metadata.get("title", "Untitled")
                summary = metadata.get("summary", "")

                markdown_content = f"# {title}\n\n"
                if summary:
                    markdown_content += f"{summary}\n\n"

                # Add any additional fields as sections
                for key, value in data.items():
                    if key not in [
                        "title",
                        "summary",
                        "tags",
                        "domain",
                        "kind",
                        "source",
                        "content",
                    ]:
                        markdown_content += f"## {key.replace('_', ' ').title()}\n\n"
                        if isinstance(value, list):
                            for item in value:
                                markdown_content += f"- {item}\n"
                        else:
                            markdown_content += f"{value}\n"
                        markdown_content += "\n"

            # Combine frontmatter and content
            return "\n".join(frontmatter_lines) + markdown_content

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error normalizing JSON file {filepath}: {e}")
            return f"# Error\n\nCould not parse JSON file: {e}"


# Example usage
if __name__ == "__main__":
    # Create example JSON file
    wiki_base = Path("wiki_system")
    inbox = wiki_base / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    # Example 1: Simple JSON with content field
    example1 = {
        "title": "REST API Design",
        "summary": "Best practices for designing RESTful APIs",
        "tags": ["api", "rest", "design"],
        "domain": "tech",
        "kind": "concept",
        "content": """# REST API Design

REST (Representational State Transfer) is an architectural style for designing networked applications.

## Key Principles

- **Stateless**: Each request contains all necessary information
- **Resource-based**: URLs represent resources
- **HTTP methods**: Use GET, POST, PUT, DELETE appropriately
- **HATEOAS**: Include links to related resources

## Best Practices

1. Use nouns for resource names
2. Use plural forms (/users, not /user)
3. Return appropriate status codes
4. Version your API
5. Use JSON for data exchange

Source: https://restfulapi.net/
""",
    }

    json_file1 = inbox / "rest-api-design.json"
    json_file1.write_text(json.dumps(example1, indent=2))
    print(f"Created: {json_file1}")

    # Example 2: JSON without content field (will be generated)
    example2 = {
        "title": "Docker",
        "summary": "Containerization platform",
        "tags": ["docker", "containers", "devops"],
        "domain": "tech",
        "kind": "entity",
        "description": "Docker is a platform for developing, shipping, and running applications in containers",
        "features": ["Isolation", "Portability", "Efficiency", "Scalability"],
        "source": "https://www.docker.com/",
    }

    json_file2 = inbox / "docker.json"
    json_file2.write_text(json.dumps(example2, indent=2))
    print(f"Created: {json_file2}")

    # Test the adapter
    print("\n=== Testing JSON Adapter ===")
    adapter = JSONAdapter()

    for json_file in [json_file1, json_file2]:
        print(f"\nProcessing: {json_file.name}")

        # Check if adapter can parse
        if adapter.can_parse(json_file):
            print("  ✓ Can parse")

            # Extract metadata
            metadata = adapter.extract_metadata(json_file)
            print(f"  Metadata: {metadata}")

            # Normalize to markdown
            content = json_file.read_text()
            markdown = adapter.normalize_to_markdown(json_file, content)

            # Show result
            print("\n  Normalized markdown:")
            print("  " + "-" * 60)
            lines = markdown.split("\n")[:20]
            for line in lines:
                print(f"  {line}")
            print("  ...")
            print("  " + "-" * 60)
        else:
            print("  ✗ Cannot parse")

    # To integrate this adapter into the system:
    print("\n\n=== Integration Instructions ===")
    print("1. Save this adapter to: src/llm_wiki/adapters/json.py")
    print("2. Update InboxWatcher to include JSONAdapter:")
    print("   from llm_wiki.adapters.json import JSONAdapter")
    print("   adapters = [MarkdownAdapter(), TextAdapter(), JSONAdapter()]")
    print("3. Drop .json files in inbox/ and they'll be processed automatically")
