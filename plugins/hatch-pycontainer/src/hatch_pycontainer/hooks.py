"""Hatch build hooks for pycontainer-build."""

import logging
from pathlib import Path
from typing import Any, Dict
from hatchling.plugin import hookimpl


class ContainerBuildHook:
    """Build hook for creating container images with pycontainer-build."""

    PLUGIN_NAME = "pycontainer"

    def __init__(self, root: str, config: Dict[str, Any]):
        """Initialize the build hook.
        
        Args:
            root: Project root directory
            config: Hook configuration from pyproject.toml
        """
        self.root = Path(root)
        self.config = config

    @staticmethod
    def _configure_logging(verbose: bool) -> None:
        log_level = logging.DEBUG if verbose else logging.INFO
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        if not root_logger.handlers:
            logging.basicConfig(
                level=log_level,
                format='%(levelname)s: %(message)s' if verbose else '%(message)s',
            )

    def initialize(self, version: str, build_data: Dict[str, Any]) -> None:
        """Initialize the build process."""
        if self.config.get("skip", False):
            return

        try:
            from pycontainer.config import BuildConfig
            from pycontainer.builder import ImageBuilder
        except ImportError:
            raise RuntimeError(
                "pycontainer-build is not installed. "
                "Install it with: pip install pycontainer-build"
            )

        # Get configuration
        tag = self.config.get("tag")
        if not tag:
            # Read from pyproject.toml
            import tomllib
            pyproject_path = self.root / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    pyproject = tomllib.load(f)
                    project = pyproject.get("project", {})
                    name = project.get("name", "app")
                    tag = f"{name}:{version}"
            else:
                tag = f"app:{version}"

        base_image = self.config.get("base-image", "python:3.11-slim")
        push = self.config["push"] if "push" in self.config else False
        include_deps = self.config["include-deps"] if "include-deps" in self.config else True
        sbom = self.config.get("sbom")
        verbose = self.config["verbose"] if "verbose" in self.config else False
        env = self.config.get("env", {})
        labels = self.config.get("labels", {})
        use_cache = not self.config["no-cache"] if "no-cache" in self.config else True
        clean_output_dir = self.config.get("clean-output-dir", False)

        self._configure_logging(verbose)

        # Add build metadata to labels
        labels["org.opencontainers.image.version"] = version

        # Create build configuration
        config = BuildConfig(
            tag=tag,
            context_dir=str(self.root),
            base_image=base_image,
            include_deps=include_deps,
            env=env,
            labels=labels,
            verbose=verbose,
            use_cache=use_cache,
            clean_output_dir=clean_output_dir,
        )

        if sbom:
            config.generate_sbom = sbom

        # Build the image
        try:
            builder = ImageBuilder(config)
            builder.build()

            # Push if requested
            if push:
                builder.push()

        except Exception as e:
            raise RuntimeError(f"Container build failed: {e}")

        # Store build info in build_data
        build_data["container_image"] = {
            "tag": tag,
            "base_image": base_image,
            "pushed": push,
        }


@hookimpl
def hatch_register_build_hook():
    """Register the container build hook with Hatch."""
    return ContainerBuildHook
