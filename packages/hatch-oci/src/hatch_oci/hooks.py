"""Hatch build hooks for pyoci."""

import logging
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl


class ContainerBuildHook(BuildHookInterface):
    """Build hook for creating container images with pyoci."""

    PLUGIN_NAME = "pyoci"

    @staticmethod
    def _configure_logging(verbose: bool) -> None:
        log_level = logging.DEBUG if verbose else logging.INFO
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        if not root_logger.handlers:
            logging.basicConfig(
                level=log_level,
                format="%(levelname)s: %(message)s" if verbose else "%(message)s",
            )

    def dependencies(self) -> list[str]:
        """Install pyoci into the build environment before running."""
        return ["pyoci"]

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Initialize the build process."""
        if self.config.get("skip", False):
            return

        try:
            from pyoci.config import BuildConfig
            from pyoci.builder import ImageBuilder
        except ImportError:
            raise RuntimeError("pyoci is not installed. Install it with: pip install pyoci")

        root = Path(self.root)

        # Get configuration
        tag = self.config.get("tag")
        if not tag:
            # Read from pyproject.toml
            import tomllib

            pyproject_path = root / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    pyproject = tomllib.load(f)
                    project = pyproject.get("project", {})
                    name = project.get("name", "app")
                    tag = f"{name}:{version}"
            else:
                tag = f"app:{version}"

        base_image = self.config.get("base-image", "python:3.11-slim")
        registry = self.config.get("registry")
        push = self.config["push"] if "push" in self.config else False
        include_deps = self.config["include-deps"] if "include-deps" in self.config else True
        sbom = self.config.get("sbom")
        verbose = self.config["verbose"] if "verbose" in self.config else False
        platform = self.config.get("platform", "linux/amd64")
        env = dict(self.config.get("env", {}))
        labels = dict(self.config.get("labels", {}))
        use_cache = not self.config["no-cache"] if "no-cache" in self.config else True
        clean_output_dir = self.config.get("clean-output-dir", False)

        self._configure_logging(verbose)

        # Add build metadata to labels
        labels["org.opencontainers.image.version"] = version

        # Create build configuration
        build_config = BuildConfig(
            tag=tag,
            context_dir=str(root),
            base_image=base_image,
            include_deps=include_deps,
            env=env,
            labels=labels,
            verbose=verbose,
            platform=platform,
            use_cache=use_cache,
            clean_output_dir=clean_output_dir,
        )

        if sbom:
            build_config.generate_sbom = sbom

        # Build the image
        try:
            builder = ImageBuilder(build_config)
            builder.build()

            # Push if requested
            if push:
                builder.push(registry_url=registry)

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
