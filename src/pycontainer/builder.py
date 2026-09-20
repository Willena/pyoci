import hashlib, json, tarfile, shutil, logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from .config import BuildConfig

def parse_platform(platform: str) -> Tuple[str, str]:
    """Parse platform string (e.g., 'linux/amd64') into (os, arch)."""
    parts=platform.split('/')
    if len(parts)!=2:
        raise ValueError(f"Invalid platform format: {platform}. Expected 'os/arch' (e.g., 'linux/amd64')")
    return parts[0], parts[1]
from .oci import OCILayer, build_config_json, build_manifest_json, build_oci_layout, build_index_json
from .project import detect_entrypoint, default_include_paths, find_dependencies
from .framework import apply_framework_defaults
from .fs_utils import ensure_dir, iter_files
from .registry_client import RegistryClient, parse_image_reference
from .auth import RegistryAuth, get_auth_for_registry
from .cache import LayerCache
from .sbom import generate_sbom

logger=logging.getLogger(__name__)

class ImageBuilder:
    def __init__(self, config: BuildConfig): 
        self.config=apply_framework_defaults(config, Path(config.context_dir))
        self.cache=LayerCache(
            cache_dir=Path(config.cache_dir) if config.cache_dir else None,
            max_size_mb=config.max_cache_size_mb
        ) if config.use_cache else None
        self.verbose=getattr(config, 'verbose', False)
        self.dry_run=getattr(config, 'dry_run', False)

    def build(self):
        if self.dry_run:
            logger.info("DRY RUN: Would build image %s", self.config.tag)
            self._show_build_plan()
            return self.config.tag
        
        output_path=Path(self.config.output_dir)
        logger.info("Building image %s", self.config.tag)
        if self.config.clean_output_dir and output_path.exists():
            logger.info("Cleaning output directory %s", output_path)
            shutil.rmtree(output_path)

        output=ensure_dir(self.config.output_dir)
        blobs=ensure_dir(output/'blobs')
        layers_dir=ensure_dir(blobs/'sha256')
        refs_dir=ensure_dir(output/'refs'/'tags')

        os_name, arch = parse_platform(self.config.platform)
        logger.info("Using base image %s for %s/%s", self.config.base_image, os_name, arch)
        base_layers, base_config = self._pull_base_image(layers_dir, os_name, arch)
        
        entry = self.config.entrypoint or detect_entrypoint(self.config.context_dir)
        include = self.config.include_paths or default_include_paths(self.config.context_dir)

        app_layers=[]
        app_diff_ids=[]
        app_history=[]
        if self.config.include_deps:
            deps_layer=self._create_deps_layer(layers_dir)
            if deps_layer:
                app_layers.append(deps_layer)
                app_diff_ids.append(deps_layer.digest)
                app_history.append({"created_by":"pycontainer add dependency files"})
        
        app_layer=self._create_app_layer(layers_dir, include)
        app_layers.append(app_layer)
        app_diff_ids.append(app_layer.digest)
        app_history.append({"created_by":"pycontainer add application files"})
        
        all_layers=base_layers+app_layers

        cfg = build_config_json(arch,os_name,self.config.env,self.config.workdir,entry,self.config.exposed_ports,
                                labels=self.config.labels,user=self.config.user,cmd=self.config.cmd,base_config=base_config,
                                diff_ids=app_diff_ids,history=app_history)
        diff_ids=cfg.get("rootfs",{}).get("diff_ids",[])
        if len(diff_ids)!=len(all_layers):
            raise RuntimeError(
                f"Invalid OCI config: manifest has {len(all_layers)} layers but config has {len(diff_ids)} diff_ids"
            )
        cfg_bytes=json.dumps(cfg,separators=(',',':')).encode()
        cfg_digest="sha256:"+hashlib.sha256(cfg_bytes).hexdigest()
        cfg_path=layers_dir/cfg_digest.split(":",1)[1]
        cfg_path.write_bytes(cfg_bytes)

        manifest=build_manifest_json(cfg_digest,len(cfg_bytes),all_layers)
        manifest_bytes=json.dumps(manifest,separators=(',',':')).encode()
        manifest_digest="sha256:"+hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path=layers_dir/manifest_digest.split(":",1)[1]
        manifest_path.write_bytes(manifest_bytes)

        oci_layout=build_oci_layout()
        (output/'oci-layout').write_bytes(json.dumps(oci_layout,separators=(',',':')).encode())

        index=build_index_json(manifest_digest,len(manifest_bytes),self.config.tag,arch,os_name)
        (output/'index.json').write_bytes(json.dumps(index,separators=(',',':')).encode())

        _, _, tag_name=parse_image_reference(self.config.tag)
        (refs_dir/tag_name).write_text(manifest_digest)

        self.manifest_digest=manifest_digest
        self.config_digest=cfg_digest
        self.layers=all_layers
        logger.info("Image layout written to %s", output)
        
        if getattr(self.config, 'generate_sbom', False):
            sbom_path=output/'sbom.json'
            logger.info("Generating SBOM...")
            generate_sbom(Path(self.config.context_dir), sbom_path)
            logger.info(f"✓ SBOM saved to {sbom_path}")
        
        logger.info("Built image %s with %d layer(s)", self.config.tag, len(all_layers))
        return self.config.tag
    
    def _pull_base_image(self, layers_dir: Path, os_name: str, arch: str) -> Tuple[List[OCILayer], Optional[Dict]]:
        """Pull base image from registry, return (base_layers, base_config)."""
        registry, repo, tag=parse_image_reference(self.config.base_image)
        auth=get_auth_for_registry(registry)
        client=RegistryClient(registry, repo, auth=auth)
        
        logger.info("Pulling base image %s for %s/%s...", self.config.base_image, os_name, arch)
        manifest, _=client.pull_manifest(tag)
        
        if manifest.get('mediaType')=='application/vnd.oci.image.index.v1+json':
            for m in manifest.get('manifests',[]):
                plat=m.get('platform',{})
                if plat.get('architecture')==arch and plat.get('os')==os_name:
                    manifest, _=client.pull_manifest(m['digest'])
                    break
        
        config_desc=manifest.get('config',{})
        config_digest=config_desc.get('digest')
        config_path=layers_dir/config_digest.split(':',1)[1]
        if not config_path.exists():
            client.pull_blob(config_digest, config_path)
        base_config=json.loads(config_path.read_bytes())
        
        base_layers=[]
        for i, layer_desc in enumerate(manifest.get('layers',[]), 1):
            layer_digest=layer_desc['digest']
            layer_size=layer_desc['size']
            layer_path=layers_dir/layer_digest.split(':',1)[1]
            if not layer_path.exists():
                logger.info("  Pulling layer %d/%d (%s...)", i, len(manifest['layers']), layer_digest[:19])
                client.pull_blob(layer_digest, layer_path)
            base_layers.append(OCILayer(layer_desc['mediaType'], layer_digest, layer_size, str(layer_path)))
        
        logger.info("Base image pulled (%d layers)", len(base_layers))
        return base_layers, base_config
    
    def push(self, registry_url: Optional[str]=None, auth: Optional[RegistryAuth]=None, show_progress: bool=True):
        """Push built image to registry."""
        if not hasattr(self, 'manifest_digest'):
            raise RuntimeError("Must call build() before push()")
        
        target=registry_url or self.config.tag
        registry, repo, tag=parse_image_reference(target)

        auth=auth or get_auth_for_registry(registry)
        client=RegistryClient(registry, repo, auth=auth)
        output=Path(self.config.output_dir)
        layers_dir=output/'blobs'/'sha256'
        
        if show_progress:
            logger.info("Pushing to %s/%s:%s", registry, repo, tag)
        
        for i, layer in enumerate(self.layers, 1):
            if show_progress:
                logger.info("  Pushing layer %d/%d (%s...)", i, len(self.layers), layer.digest[:19])
            blob_path=layers_dir/layer.digest.split(":",1)[1]
            skipped=not client.push_blob(layer.digest, blob_path, check_exists=True)
            if show_progress and skipped:
                logger.info("    Layer exists, skipped")
        
        if show_progress:
            logger.info("  Pushing config (%s...)", self.config_digest[:19])
        cfg_path=layers_dir/self.config_digest.split(":",1)[1]
        client.push_blob(self.config_digest, cfg_path, check_exists=True)
        
        if show_progress:
            logger.info("  Pushing manifest (%s...)", self.manifest_digest[:19])
        manifest_path=layers_dir/self.manifest_digest.split(":",1)[1]
        manifest_data=manifest_path.read_bytes()
        client.push_manifest(tag, manifest_data)
        
        if show_progress:
            logger.info("Pushed %s/%s:%s", registry, repo, tag)
        return f"{registry}/{repo}:{tag}"
    
    def _show_build_plan(self):
        """Display build plan for dry-run mode."""
        logger.info("Build Plan for %s:", self.config.tag)
        logger.info("  Base Image: %s", self.config.base_image)
        logger.info("  Context: %s", self.config.context_dir)
        logger.info("  Working Dir: %s", self.config.workdir)
        logger.info("  Entrypoint: %s", ' '.join(self.config.entrypoint or ['<auto-detect>']))
        if self.config.exposed_ports:
            logger.info("  Exposed Ports: %s", ', '.join(map(str, self.config.exposed_ports)))
        if self.config.env:
            logger.info("  Environment: %s", ', '.join(f'{k}={v}' for k,v in self.config.env.items()))
        if self.config.labels:
            logger.info("  Labels: %s", ', '.join(f'{k}={v}' for k,v in self.config.labels.items()))
        logger.info("  Include Dependencies: %s", self.config.include_deps)
        logger.info("  Use Cache: %s", self.config.use_cache)

    def _create_deps_layer(self, layers_dir: Path) -> Optional[OCILayer]:
        """Create dependency layer from venv or requirements.txt."""
        ctx=Path(self.config.context_dir)
        deps_paths=find_dependencies(ctx, self.config.requirements_file)
        if not deps_paths:
            return None
        
        logger.info("Creating dependency layer (%d files)", len(deps_paths))
        tmp=layers_dir/'deps-layer.tar'
        with tarfile.open(tmp,'w') as tar:
            for abs_path, rel in deps_paths:
                arc=f"{self.config.workdir.lstrip('/')}/{rel.as_posix()}"
                tar.add(abs_path,arcname=arc)
        data=tmp.read_bytes()
        digest="sha256:"+hashlib.sha256(data).hexdigest()
        final=layers_dir/digest.split(":",1)[1]
        tmp.rename(final)
        logger.info("Dependency layer created (%s...)", digest[:19])
        return OCILayer("application/vnd.oci.image.layer.v1.tar",digest,len(data),str(final))

    def _create_app_layer(self, layers_dir, include_paths):
        ctx=Path(self.config.context_dir)
        files=list(iter_files(ctx, include_paths))
        
        if self.cache:
            cached=self.cache.get_layer(files)
            if cached:
                digest, cache_path=cached
                final=layers_dir/digest.split(":",1)[1]
                if not final.exists():
                    shutil.copy2(cache_path, final)
                logger.info("Reusing cached application layer (%d files)", len(files))
                return OCILayer("application/vnd.oci.image.layer.v1.tar",digest,cache_path.stat().st_size,str(final))
        
        logger.info("Creating application layer (%d files)", len(files))
        tmp=layers_dir/'app-layer.tar'
        files_sorted=sorted(files, key=lambda x: x[1].as_posix()) if self.config.reproducible else files
        
        with tarfile.open(tmp,'w') as tar:
            for abs_path, rel in files_sorted:
                arc=f"{self.config.workdir.lstrip('/')}/{rel.as_posix()}"
                if self.config.reproducible:
                    tarinfo=tar.gettarinfo(abs_path, arcname=arc)
                    tarinfo.mtime=0
                    tarinfo.uid=0
                    tarinfo.gid=0
                    tarinfo.uname="root"
                    tarinfo.gname="root"
                    if tarinfo.isfile():
                        with open(abs_path, 'rb') as f:
                            tar.addfile(tarinfo, f)
                    else:
                        tar.addfile(tarinfo)
                else:
                    tar.add(abs_path,arcname=arc)
        data=tmp.read_bytes()
        digest="sha256:"+hashlib.sha256(data).hexdigest()
        final=layers_dir/digest.split(":",1)[1]
        tmp.rename(final)
        
        if self.cache:
            self.cache.store_layer(files, digest, final)
        
        return OCILayer("application/vnd.oci.image.layer.v1.tar",digest,len(data),str(final))
