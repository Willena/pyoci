import argparse, logging
from pathlib import Path
from .config import BuildConfig
from .builder import ImageBuilder
from .config_loader import config_from_file
from .project import detect_python_version
from .auth import RegistryAuth


def _parse_key_value_pairs(values, option_name):
    parsed = {}
    for value in values or []:
        if "=" not in value:
            raise argparse.ArgumentTypeError(
                f"{option_name} expects KEY=VALUE entries, got {value!r}"
            )
        key, raw_value = value.split("=", 1)
        if not key:
            raise argparse.ArgumentTypeError(
                f"{option_name} expects a non-empty KEY in KEY=VALUE entries"
            )
        parsed[key] = raw_value
    return parsed


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    clean_output_group = b.add_mutually_exclusive_group()
    b.add_argument("--config", "-c", help="Path to pyoci.toml config file")
    b.add_argument("--tag")
    b.add_argument(
        "--base-image",
        help="Base image to layer on (auto-detected from requires-python if not specified)",
    )
    b.add_argument("--context", default=".")
    b.add_argument("--workdir", help="Working directory inside the image (default: /app)")
    b.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Set an environment variable in the image (repeatable)",
    )
    b.add_argument(
        "--label",
        action="append",
        metavar="KEY=VALUE",
        help="Set an OCI label on the image (repeatable)",
    )
    b.add_argument("--push", action="store_true", help="Push image to registry after build")
    b.add_argument("--registry", help="Override registry from tag (e.g., ghcr.io/user/repo:v1)")
    b.add_argument("--username", help="Registry username")
    b.add_argument("--password", help="Registry password or token")
    b.add_argument("--no-progress", action="store_true", help="Suppress progress output")
    b.add_argument(
        "--no-cache", action="store_true", help="Disable layer caching, force full rebuild"
    )
    b.add_argument("--cache-dir", help="Custom cache directory (default: ~/.pyoci/cache)")
    b.add_argument(
        "--include-deps",
        action="store_true",
        help="Include dependencies from venv or requirements.txt",
    )
    b.add_argument(
        "--requirements", default="requirements.txt", help="Requirements file for dependency layer"
    )
    b.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output with detailed logging"
    )
    b.add_argument("--dry-run", action="store_true", help="Show build plan without building")
    b.add_argument(
        "--platform", default="linux/amd64", help="Target platform (e.g., linux/amd64, linux/arm64)"
    )
    b.add_argument("--no-reproducible", action="store_true", help="Disable reproducible builds")
    b.add_argument(
        "--sbom",
        nargs="?",
        const="spdx",
        choices=["spdx", "cyclonedx"],
        help="Generate SBOM (default: spdx)",
    )
    clean_output_group.add_argument(
        "--clean-output-dir",
        dest="clean_output_dir",
        action="store_true",
        default=None,
        help="Delete the output directory before building",
    )
    clean_output_group.add_argument(
        "--no-clean-output-dir",
        dest="clean_output_dir",
        action="store_false",
        help="Preserve existing files in the output directory before building",
    )
    args = parser.parse_args()
    env = _parse_key_value_pairs(args.env, "--env")
    labels = _parse_key_value_pairs(args.label, "--label")

    log_level = logging.DEBUG if args.verbose else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        logging.basicConfig(
            level=log_level, format="%(levelname)s: %(message)s" if args.verbose else "%(message)s"
        )

    if args.config:
        cli_overrides = {
            "tag": args.tag,
            "base_image": args.base_image,
            "context_dir": args.context,
            "workdir": args.workdir,
            "env": env or None,
            "labels": labels or None,
            "use_cache": not args.no_cache if args.no_cache else None,
            "cache_dir": args.cache_dir,
            "include_deps": args.include_deps,
            "requirements_file": args.requirements,
            "verbose": args.verbose,
            "dry_run": args.dry_run,
            "platform": args.platform,
            "reproducible": not args.no_reproducible if args.no_reproducible else None,
            "generate_sbom": args.sbom,
            "clean_output_dir": args.clean_output_dir,
        }
        cli_overrides = {k: v for k, v in cli_overrides.items() if v is not None}
        cfg = config_from_file(Path(args.config), cli_overrides)
    else:
        tag = args.tag or "local/test:latest"
        base_img = args.base_image
        if not base_img:
            py_ver = detect_python_version(args.context)
            base_img = f"python:{py_ver}-slim"
        cfg = BuildConfig(
            tag=tag,
            base_image=base_img,
            context_dir=args.context,
            workdir=args.workdir or "/app",
            env=env,
            labels=labels or None,
            use_cache=not args.no_cache,
            cache_dir=args.cache_dir,
            include_deps=args.include_deps,
            requirements_file=args.requirements,
            verbose=args.verbose,
            dry_run=args.dry_run,
            platform=args.platform,
            reproducible=not args.no_reproducible,
            clean_output_dir=bool(args.clean_output_dir),
        )
        cfg.generate_sbom = args.sbom
    builder = ImageBuilder(cfg)
    out = builder.build()
    logging.getLogger(__name__).info("Built: %s", out)

    if args.push:
        auth = RegistryAuth.from_user_pass_or_token(
            username=args.username, password_or_token=args.password
        )
        builder.push(registry_url=args.registry, auth=auth, show_progress=not args.no_progress)


if __name__ == "__main__":
    main()
