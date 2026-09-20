from __future__ import annotations

import sys
import types
from builtins import __import__ as builtin_import
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hatch_oci.hooks import ContainerBuildHook, hatch_register_build_hook


class FakeBuildConfig:
    instances: list["FakeBuildConfig"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.generate_sbom = None
        type(self).instances.append(self)


class FakeImageBuilder:
    instances: list["FakeImageBuilder"] = []
    build_error: Exception | None = None

    def __init__(self, config):
        self.config = config
        self.build_calls = 0
        self.push_calls = 0
        type(self).instances.append(self)

    def build(self):
        self.build_calls += 1
        if type(self).build_error is not None:
            raise type(self).build_error

    def push(self):
        self.push_calls += 1


@pytest.fixture(autouse=True)
def reset_fakes():
    FakeBuildConfig.instances.clear()
    FakeImageBuilder.instances.clear()
    FakeImageBuilder.build_error = None


@pytest.fixture
def fake_pycontainer(monkeypatch):
    package = types.ModuleType("pyoci")
    package.__path__ = []

    config_module = types.ModuleType("pyoci.config")
    config_module.BuildConfig = FakeBuildConfig

    builder_module = types.ModuleType("pyoci.builder")
    builder_module.ImageBuilder = FakeImageBuilder

    monkeypatch.setitem(sys.modules, "pyoci", package)
    monkeypatch.setitem(sys.modules, "pyoci.config", config_module)
    monkeypatch.setitem(sys.modules, "pyoci.builder", builder_module)


def make_hook(tmp_path: Path, config: dict | None = None) -> ContainerBuildHook:
    return ContainerBuildHook(
        root=str(tmp_path),
        config=config or {},
        build_config={},
        metadata=object(),
        directory=str(tmp_path / "dist"),
        target_name="wheel",
    )


def test_dependencies_are_installed_in_build_env(tmp_path):
    hook = make_hook(tmp_path)
    assert hook.dependencies() == ["pyoci"]


def test_initialize_skips_build_when_skip_enabled(tmp_path):
    hook = make_hook(tmp_path, {"skip": True})
    build_data = {"existing": True}

    hook.initialize("1.2.3", build_data)

    assert build_data == {"existing": True}


def test_initialize_builds_image_with_explicit_config(tmp_path, fake_pycontainer):
    hook = make_hook(
        tmp_path,
        {
            "tag": "acme/demo:1.2.3",
            "base-image": "python:3.12-alpine",
            "push": True,
            "include-deps": False,
            "sbom": "spdx",
            "verbose": True,
            "env": {"APP_ENV": "prod"},
            "labels": {"maintainer": "team@example.com"},
            "no-cache": True,
            "clean-output-dir": True,
        },
    )
    build_data = {}

    hook.initialize("1.2.3", build_data)

    assert len(FakeBuildConfig.instances) == 1
    build_config = FakeBuildConfig.instances[0]
    assert build_config.kwargs == {
        "tag": "acme/demo:1.2.3",
        "context_dir": str(tmp_path),
        "base_image": "python:3.12-alpine",
        "include_deps": False,
        "env": {"APP_ENV": "prod"},
        "labels": {
            "maintainer": "team@example.com",
            "org.opencontainers.image.version": "1.2.3",
        },
        "verbose": True,
        "use_cache": False,
        "clean_output_dir": True,
    }
    assert build_config.generate_sbom == "spdx"

    assert len(FakeImageBuilder.instances) == 1
    builder = FakeImageBuilder.instances[0]
    assert builder.config is build_config
    assert builder.build_calls == 1
    assert builder.push_calls == 1

    assert build_data == {
        "container_image": {
            "tag": "acme/demo:1.2.3",
            "base_image": "python:3.12-alpine",
            "pushed": True,
        }
    }


def test_initialize_derives_default_tag_from_pyproject(tmp_path, fake_pycontainer):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo-service"
""".strip()
    )
    hook = make_hook(tmp_path)

    hook.initialize("2.0.0", {})

    build_config = FakeBuildConfig.instances[0]
    assert build_config.kwargs["tag"] == "demo-service:2.0.0"
    assert build_config.kwargs["base_image"] == "python:3.11-slim"
    assert build_config.kwargs["include_deps"] is True
    assert build_config.kwargs["use_cache"] is True


def test_initialize_uses_app_tag_without_pyproject(tmp_path, fake_pycontainer):
    hook = make_hook(tmp_path)

    hook.initialize("3.4.5", {})

    assert FakeBuildConfig.instances[0].kwargs["tag"] == "app:3.4.5"


def test_initialize_reports_missing_dependency(tmp_path, monkeypatch):
    def fail_pycontainer_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"pyoci.config", "pyoci.builder"}:
            raise ImportError("missing test dependency")
        return builtin_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fail_pycontainer_import)
    hook = make_hook(tmp_path)

    with pytest.raises(RuntimeError, match="pyoci is not installed"):
        hook.initialize("1.0.0", {})


def test_initialize_wraps_builder_failures(tmp_path, fake_pycontainer):
    FakeImageBuilder.build_error = ValueError("boom")
    hook = make_hook(tmp_path, {"push": True})

    with pytest.raises(RuntimeError, match="Container build failed: boom"):
        hook.initialize("1.0.0", {})

    builder = FakeImageBuilder.instances[0]
    assert builder.build_calls == 1
    assert builder.push_calls == 0


def test_register_build_hook_returns_hook_class():
    assert hatch_register_build_hook() is ContainerBuildHook
