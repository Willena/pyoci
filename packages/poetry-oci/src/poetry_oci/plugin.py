"""Poetry plugin implementation for pyoci."""

import logging

from cleo.helpers import option
from poetry.console.commands.command import Command
from poetry.plugins.application_plugin import ApplicationPlugin


class ContainerBuildCommand(Command):
    """Build a container image from the Poetry project."""

    name = "build-container"
    description = "Build an OCI container image using pyoci"

    options = [
        option("tag", "t", "Container image tag", flag=False, default=None),
        option("base-image", "b", "Base container image", flag=False, default=None),
        option("registry", "r", "Container registry URL", flag=False, default=None),
        option("push", "p", "Push image to registry", flag=True),
        option("include-deps", "d", "Include Poetry dependencies", flag=True),
        option("sbom", "s", "Generate SBOM (spdx or cyclonedx)", flag=False, default=None),
        option("verbose", "v", "Verbose output", flag=True),
        option("dry-run", None, "Show what would be built without building", flag=True),
        option("no-cache", None, "Disable layer caching", flag=True),
    ]

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

    def handle(self) -> int:
        """Handle the build-container command."""
        try:
            # Import pyoci
            from pyoci.config import BuildConfig
            from pyoci.builder import ImageBuilder
        except ImportError:
            self.line_error(
                "<error>pyoci is not installed. Install it with: pip install pyoci</error>"
            )
            return 1

        # Get Poetry project
        poetry = self.poetry
        package = poetry.package

        # Read configuration from pyproject.toml [tool.pyoci]
        pyproject = poetry.pyproject
        tool_config = pyproject.data.get("tool", {}).get("pyoci", {})

        # Determine tag
        tag = self.option("tag")
        if not tag:
            tag = tool_config.get("tag")
        if not tag:
            name = package.name
            version = str(package.version)
            tag = f"{name}:{version}"

        # Build configuration
        if self.io.input.has_parameter_option("--base-image"):
            base_image = self.option("base-image")
        else:
            base_image = tool_config.get("base_image", "python:3.11-slim")
        registry = self.option("registry") or tool_config.get("registry")
        if self.io.input.has_parameter_option("--push"):
            push = self.option("push")
        else:
            push = tool_config.get("push", False)
        if self.io.input.has_parameter_option("--include-deps"):
            include_deps = self.option("include-deps")
        else:
            include_deps = tool_config.get("include_deps", True)
        sbom = self.option("sbom") or tool_config.get("sbom")
        if self.io.input.has_parameter_option("--verbose"):
            verbose = self.option("verbose")
        else:
            verbose = tool_config.get("verbose", False)
        if self.io.input.has_parameter_option("--dry-run"):
            dry_run = self.option("dry-run")
        else:
            dry_run = tool_config.get("dry_run", False)
        if self.io.input.has_parameter_option("--no-cache"):
            no_cache = self.option("no-cache")
        else:
            no_cache = tool_config.get("no_cache", False)
        clean_output_dir = tool_config.get("clean_output_dir", False)

        self._configure_logging(verbose)

        # Get environment variables from config
        env = tool_config.get("env", {})
        labels = tool_config.get("labels", {})

        # Add Poetry metadata to labels
        labels.update(
            {
                "org.opencontainers.image.title": package.name,
                "org.opencontainers.image.version": str(package.version),
                "org.opencontainers.image.description": package.description or "",
            }
        )
        if package.authors:
            authors = ", ".join(str(a) for a in package.authors)
            labels["org.opencontainers.image.authors"] = authors

        # Get project path
        project_path = poetry.file.path.parent

        # Create build configuration
        config = BuildConfig(
            tag=tag,
            context_dir=str(project_path),
            base_image=base_image,
            include_deps=include_deps,
            env=env,
            labels=labels,
            verbose=verbose,
            dry_run=dry_run,
            use_cache=not no_cache,
            clean_output_dir=clean_output_dir,
        )

        # Generate SBOM if requested
        if sbom:
            config.generate_sbom = sbom

        # Build the image
        try:
            builder = ImageBuilder(config)
            builder.build()

            # Push if requested
            if push:
                builder.push(registry_url=registry)

            return 0

        except Exception as e:
            self.line_error(f"<error>Build failed: {e}</error>")
            if verbose:
                import traceback

                self.line_error(traceback.format_exc())
            return 1


class PyociPlugin(ApplicationPlugin):
    """Poetry plugin for pyoci integration."""

    def activate(self, application):
        """Activate the plugin by registering commands."""
        application.command_loader.register_factory("build-container", ContainerBuildCommand)
