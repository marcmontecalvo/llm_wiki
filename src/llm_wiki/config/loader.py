"""Configuration loader for wiki system."""

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from llm_wiki.models.config import DaemonYAML, DomainsYAML, ModelsYAML, RoutingYAML, WikiConfig


class ConfigLoadError(Exception):
    """Raised when configuration loading fails."""

    pass


class ConfigLoader:
    """Load and validate wiki configuration from YAML files."""

    def __init__(self, config_dir: Path | str = "config"):
        """Initialize config loader.

        Args:
            config_dir: Path to directory containing config YAML files
        """
        self.config_dir = Path(config_dir)
        if not self.config_dir.exists():
            raise ConfigLoadError(f"Config directory does not exist: {self.config_dir}")
        if not self.config_dir.is_dir():
            raise ConfigLoadError(f"Config path is not a directory: {self.config_dir}")

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML file from config directory.

        Args:
            filename: Name of YAML file (e.g., 'domains.yaml')

        Returns:
            Parsed YAML content as dict

        Raises:
            ConfigLoadError: If file doesn't exist or YAML is invalid
        """
        filepath = self.config_dir / filename

        if not filepath.exists():
            raise ConfigLoadError(f"Config file not found: {filepath}")

        try:
            with filepath.open("r") as f:
                data = yaml.safe_load(f)
                if data is None:
                    raise ConfigLoadError(f"Config file is empty: {filepath}")
                return cast(dict[str, Any], data)
        except yaml.YAMLError as e:
            raise ConfigLoadError(f"Invalid YAML in {filepath}: {e}") from e
        except OSError as e:
            raise ConfigLoadError(f"Failed to read {filepath}: {e}") from e

    def load_domains(self) -> DomainsYAML:
        """Load and validate domains.yaml.

        Returns:
            Validated DomainsYAML configuration

        Raises:
            ConfigLoadError: If loading or validation fails
        """
        data = self._load_yaml("domains.yaml")
        try:
            return DomainsYAML(**data)
        except ValidationError as e:
            raise ConfigLoadError(f"Invalid domains.yaml: {e}") from e

    def load_daemon(self) -> DaemonYAML:
        """Load and validate daemon.yaml.

        Returns:
            Validated DaemonYAML configuration

        Raises:
            ConfigLoadError: If loading or validation fails
        """
        data = self._load_yaml("daemon.yaml")
        try:
            return DaemonYAML(**data)
        except ValidationError as e:
            raise ConfigLoadError(f"Invalid daemon.yaml: {e}") from e

    def load_routing(self) -> RoutingYAML:
        """Load and validate routing.yaml.

        Returns:
            Validated RoutingYAML configuration

        Raises:
            ConfigLoadError: If loading or validation fails
        """
        data = self._load_yaml("routing.yaml")
        try:
            return RoutingYAML(**data)
        except ValidationError as e:
            raise ConfigLoadError(f"Invalid routing.yaml: {e}") from e

    def load_models(self) -> ModelsYAML:
        """Load and validate models.yaml.

        Returns:
            Validated ModelsYAML configuration

        Raises:
            ConfigLoadError: If loading or validation fails
        """
        data = self._load_yaml("models.yaml")
        try:
            return ModelsYAML(**data)
        except ValidationError as e:
            raise ConfigLoadError(f"Invalid models.yaml: {e}") from e

    def load_all(self) -> WikiConfig:
        """Load and validate all configuration files.

        Returns:
            Complete WikiConfig with all configurations

        Raises:
            ConfigLoadError: If any config file fails to load or validate
        """
        return WikiConfig(
            domains=self.load_domains(),
            daemon=self.load_daemon(),
            routing=self.load_routing(),
            models=self.load_models(),
        )


def load_config(config_dir: Path | str = "config") -> WikiConfig:
    """Convenience function to load all wiki configuration.

    Args:
        config_dir: Path to directory containing config YAML files

    Returns:
        Complete WikiConfig

    Raises:
        ConfigLoadError: If loading or validation fails
    """
    loader = ConfigLoader(config_dir)
    return loader.load_all()
