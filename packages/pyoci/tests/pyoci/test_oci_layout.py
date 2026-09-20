"""Tests for OCI Image Layout structure validation."""
import json, tempfile
import logging
from pathlib import Path
from unittest.mock import patch
from pyoci.builder import ImageBuilder
from pyoci.config import BuildConfig


def _mock_base_image():
    return (
        [],
        {"architecture": "amd64", "os": "linux", "config": {"Env": [], "WorkingDir": "/"}}
    )


def _create_test_context(tmpdir: str) -> Path:
    ctx=Path(tmpdir)/"context"
    ctx.mkdir()
    (ctx/"app.py").write_text("print('hello')")
    (ctx/"pyproject.toml").write_text('[project]\nname="test"\nversion="0.1"')
    return ctx

def test_oci_layout_structure():
    """Verify complete OCI layout structure is created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx=_create_test_context(tmpdir)
        output=Path(tmpdir)/"test-image"
        cfg=BuildConfig(tag="test:v1",output_dir=str(output),context_dir=str(ctx),use_cache=False)
        with patch("pyoci.builder.ImageBuilder._pull_base_image", return_value=_mock_base_image()):
            builder=ImageBuilder(cfg)
            builder.build()
        
        assert (output/"oci-layout").exists(),"oci-layout file missing"
        assert (output/"index.json").exists(),"index.json missing"
        assert (output/"blobs"/"sha256").exists(),"blobs/sha256/ directory missing"
        assert (output/"refs"/"tags").exists(),"refs/tags/ directory missing"
        
        layout=json.loads((output/"oci-layout").read_text())
        assert layout["imageLayoutVersion"]=="1.0.0","Invalid oci-layout version"
        
        index=json.loads((output/"index.json").read_text())
        assert index["schemaVersion"]==2,"Invalid index schema version"
        assert index["mediaType"]=="application/vnd.oci.image.index.v1+json"
        assert len(index["manifests"])==1,"Expected 1 manifest"
        assert index["annotations"]["org.opencontainers.image.ref.name"]=="test:v1"
        
        manifest_desc=index["manifests"][0]
        assert manifest_desc["platform"]["architecture"]=="amd64"
        assert manifest_desc["platform"]["os"]=="linux"
        
        tag_ref=(output/"refs"/"tags"/"v1").read_text().strip()
        assert tag_ref==manifest_desc["digest"],"Tag reference doesn't match manifest digest"
        
        manifest_blob=output/"blobs"/"sha256"/manifest_desc["digest"].split(":",1)[1]
        assert manifest_blob.exists(),"Manifest blob not found"
        
        manifest=json.loads(manifest_blob.read_text())
        assert manifest["mediaType"]=="application/vnd.oci.image.manifest.v1+json"
        assert len(manifest["layers"])>=1,"Expected at least 1 layer"

def test_tag_extraction():
    """Verify tag name is correctly extracted for refs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx=_create_test_context(tmpdir)
        output=Path(tmpdir)/"test-image"
        cfg=BuildConfig(tag="myapp:v2.1.0",output_dir=str(output),context_dir=str(ctx),use_cache=False)
        with patch("pyoci.builder.ImageBuilder._pull_base_image", return_value=_mock_base_image()):
            builder=ImageBuilder(cfg)
            builder.build()
        
        assert (output/"refs"/"tags"/"v2.1.0").exists(),"Tag file not created with correct name"
        
        cfg2=BuildConfig(tag="latest",output_dir=str(output)+"2",context_dir=str(ctx),use_cache=False)
        with patch("pyoci.builder.ImageBuilder._pull_base_image", return_value=_mock_base_image()):
            builder2=ImageBuilder(cfg2)
            builder2.build()
        assert (Path(output).parent/"test-image2"/"refs"/"tags"/"latest").exists()


def test_output_dir_is_preserved_by_default():
    """Verify existing output files are preserved unless cleanup is enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx=_create_test_context(tmpdir)

        output=Path(tmpdir)/"test-image"
        output.mkdir()
        stale_file=output/"stale.txt"
        stale_file.write_text("keep me")

        cfg=BuildConfig(
            tag="test:v1",
            output_dir=str(output),
            context_dir=str(ctx),
            use_cache=False,
        )

        with patch("pyoci.builder.ImageBuilder._pull_base_image", return_value=_mock_base_image()):
            builder=ImageBuilder(cfg)
            builder.build()

        assert stale_file.exists(), "Existing files should not be deleted by default"


def test_output_dir_can_be_cleaned_before_build():
    """Verify existing output files are removed when cleanup is enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx=_create_test_context(tmpdir)

        output=Path(tmpdir)/"test-image"
        output.mkdir()
        stale_file=output/"stale.txt"
        stale_file.write_text("remove me")

        cfg=BuildConfig(
            tag="test:v1",
            output_dir=str(output),
            context_dir=str(ctx),
            clean_output_dir=True,
            use_cache=False,
        )

        with patch("pyoci.builder.ImageBuilder._pull_base_image", return_value=_mock_base_image()):
            builder=ImageBuilder(cfg)
            builder.build()

        assert not stale_file.exists(), "Cleanup should delete stale files from the output directory"
        assert (output/"index.json").exists(), "Build output should still be recreated after cleanup"


def test_build_emits_phase_logs(caplog):
    """Verify the build emits minimal high-signal progress logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx=_create_test_context(tmpdir)
        output=Path(tmpdir)/"test-image"
        cfg=BuildConfig(tag="test:v1",output_dir=str(output),context_dir=str(ctx),use_cache=False)

        with caplog.at_level(logging.INFO), patch("pyoci.builder.ImageBuilder._pull_base_image", return_value=_mock_base_image()):
            builder=ImageBuilder(cfg)
            builder.build()

        messages=[record.getMessage() for record in caplog.records]
        assert "Building image test:v1" in messages
        assert "Using base image python:3.11-slim for linux/amd64" in messages
        assert any(msg.startswith("Creating application layer (") for msg in messages)
        assert f"Image layout written to {output}" in messages
        assert "Built image test:v1 with 1 layer(s)" in messages

if __name__=="__main__":
    test_oci_layout_structure()
    test_tag_extraction()
    print("✅ All OCI layout tests passed")
