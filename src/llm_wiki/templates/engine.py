"""Template engine for wiki page generation."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.models.page import create_frontmatter
from llm_wiki.utils.frontmatter import write_with_validation


class TemplateError(Exception):
    """Raised when template operations fail."""

    pass


class TemplateEngine:
    """Simple template engine for wiki pages."""

    def __init__(self, template_dir: Path | str = "templates"):
        """Initialize template engine.

        Args:
            template_dir: Directory containing template files
        """
        self.template_dir = Path(template_dir)
        if not self.template_dir.exists():
            raise TemplateError(f"Template directory does not exist: {self.template_dir}")

    def _load_template(self, template_name: str) -> str:
        """Load a template file.

        Args:
            template_name: Name of template file (e.g., 'page.md')

        Returns:
            Template content

        Raises:
            TemplateError: If template file doesn't exist
        """
        template_path = self.template_dir / template_name

        if not template_path.exists():
            raise TemplateError(f"Template file not found: {template_path}")

        try:
            return template_path.read_text(encoding="utf-8")
        except OSError as e:
            raise TemplateError(f"Failed to read template {template_path}: {e}") from e

    def _substitute_placeholders(self, template: str, data: dict[str, Any]) -> str:
        """Substitute PLACEHOLDER with actual values.

        Args:
            template: Template content
            data: Data dictionary for substitution

        Returns:
            Template with substitutions made
        """
        # For now, simple string replacement
        # Future: Could use Jinja2 or other templating if needed
        result = template

        # Replace frontmatter placeholders
        if "id" in data:
            result = result.replace("id: PLACEHOLDER", f"id: {data['id']}")
        if "title" in data:
            result = result.replace("title: PLACEHOLDER", f"title: {data['title']}")
            result = result.replace("# PLACEHOLDER", f"# {data['title']}")
        if "domain" in data:
            result = result.replace("domain: PLACEHOLDER", f"domain: {data['domain']}")
        if "kind" in data:
            result = result.replace("kind: PLACEHOLDER", f"kind: {data['kind']}")
        if "entity_type" in data:
            result = result.replace(
                "entity_type: PLACEHOLDER", f"entity_type: {data['entity_type']}"
            )
        if "source_type" in data:
            result = result.replace(
                "source_type: PLACEHOLDER", f"source_type: {data['source_type']}"
            )
        if "source_path" in data:
            result = result.replace(
                "source_path: PLACEHOLDER", f"source_path: {data['source_path']}"
            )
        if "updated_at" in data:
            result = result.replace("updated_at: PLACEHOLDER", f"updated_at: {data['updated_at']}")
        if "ingested_at" in data:
            result = result.replace(
                "ingested_at: PLACEHOLDER", f"ingested_at: {data['ingested_at']}"
            )

        return result

    def render(self, template_name: str, **data: Any) -> str:
        """Render a template with data.

        Args:
            template_name: Name of template file (e.g., 'page.md')
            **data: Data for template substitution

        Returns:
            Rendered template content

        Raises:
            TemplateError: If template rendering fails
        """
        template = self._load_template(template_name)
        return self._substitute_placeholders(template, data)

    def render_page(self, kind: str, **data: Any) -> str:
        """Render a page using kind-specific template.

        Args:
            kind: Page kind (page, entity, concept, source)
            **data: Data for page creation (must include required fields)

        Returns:
            Rendered page content with frontmatter

        Raises:
            TemplateError: If rendering fails
        """
        # Ensure required fields have defaults
        if "updated_at" not in data:
            data["updated_at"] = datetime.now(UTC).isoformat()

        # Add kind to data
        data["kind"] = kind

        # Create validated frontmatter object
        try:
            frontmatter_obj = create_frontmatter(**data)
        except Exception as e:
            raise TemplateError(f"Failed to create frontmatter: {e}") from e

        # Determine template file
        template_files = {
            "page": "page.md",
            "entity": "entity.md",
            "concept": "concept.md",
            "source": "source.md",
        }

        if kind not in template_files:
            raise TemplateError(f"Unknown page kind: {kind}")

        template_name = template_files[kind]

        # Render template
        template = self._load_template(template_name)
        body = self._substitute_placeholders(template.split("---")[-1], data)

        # Write with validated frontmatter
        return write_with_validation(frontmatter_obj, body)


def render_page_from_template(
    kind: str, template_dir: Path | str = "templates", **data: Any
) -> str:
    """Convenience function to render a page from template.

    Args:
        kind: Page kind (page, entity, concept, source)
        template_dir: Directory containing templates
        **data: Page data

    Returns:
        Rendered page content

    Raises:
        TemplateError: If rendering fails
    """
    engine = TemplateEngine(template_dir)
    return engine.render_page(kind, **data)
