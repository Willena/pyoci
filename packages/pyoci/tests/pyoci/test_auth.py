"""Tests for authentication providers."""
import json, tempfile, os
from pathlib import Path
from pyoci.auth import (
    RegistryAuth,
    EnvironmentAuthProvider,
    DockerConfigAuthProvider,
    AzureCLIAuthProvider,
    ChainAuthProvider,
    get_auth_for_registry
)

def test_environment_auth_provider():
    """Test reading credentials from environment variables."""
    os.environ['REGISTRY_USERNAME']='testuser'
    os.environ['REGISTRY_PASSWORD']='testpass'
    
    provider=EnvironmentAuthProvider()
    auth=provider.get_auth('docker.io')
    assert auth==RegistryAuth.basic('testuser', 'testpass')
    
    del os.environ['REGISTRY_USERNAME']
    del os.environ['REGISTRY_PASSWORD']

def test_github_token_env():
    """Test GitHub token from environment."""
    os.environ['GITHUB_TOKEN']='ghp_test123'
    
    provider=EnvironmentAuthProvider()
    auth=provider.get_auth('ghcr.io')
    assert auth==RegistryAuth.bearer('ghp_test123')
    
    del os.environ['GITHUB_TOKEN']

def test_docker_config_auth_provider():
    """Test reading Docker config.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path=Path(tmpdir)/'config.json'
        
        config={
            "auths":{
                "ghcr.io":{
                    "auth":"dGVzdHVzZXI6dGVzdHBhc3M="
                },
                "https://index.docker.io/v1/":{
                    "username":"dockeruser",
                    "password":"dockerpass"
                }
            }
        }
        config_path.write_text(json.dumps(config))
        
        provider=DockerConfigAuthProvider(config_path)
        
        auth=provider.get_auth('ghcr.io')
        assert auth==RegistryAuth.basic('testuser','testpass')
        
        auth=provider.get_auth('index.docker.io')
        assert auth==RegistryAuth.basic('dockeruser','dockerpass')
        
        auth=provider.get_auth('unknown.registry')
        assert auth is None

def test_docker_config_base64_decode():
    """Test base64 auth string decoding."""
    import base64
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path=Path(tmpdir)/'config.json'
        
        auth_str=base64.b64encode(b'user:pass').decode()
        config={"auths":{"test.io":{"auth":auth_str}}}
        config_path.write_text(json.dumps(config))
        
        provider=DockerConfigAuthProvider(config_path)
        auth=provider.get_auth('test.io')
        assert auth==RegistryAuth.basic('user', 'pass')

def test_chain_auth_provider():
    """Test chaining multiple auth providers."""
    os.environ['REGISTRY_TOKEN']='env_token'
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path=Path(tmpdir)/'config.json'
        config={"auths":{"docker.io":{"auth":"ZG9ja2VyOnBhc3M="}}}
        config_path.write_text(json.dumps(config))
        
        chain=ChainAuthProvider([
            EnvironmentAuthProvider(),
            DockerConfigAuthProvider(config_path)
        ])
        
        auth=chain.get_auth('any.registry')
        assert auth==RegistryAuth.bearer('env_token')

        auth=chain.get_auth('docker.io')
        assert auth==RegistryAuth.bearer('env_token')
    
    del os.environ['REGISTRY_TOKEN']

def test_get_auth_for_registry():
    """Test high-level auth resolution."""
    os.environ['GITHUB_TOKEN']='ghp_mytoken'
    
    auth=get_auth_for_registry('ghcr.io')
    assert auth==RegistryAuth.bearer('ghp_mytoken')
    
    auth=get_auth_for_registry('ghcr.io', password_or_token='override_token')
    assert auth==RegistryAuth.bearer('override_token')

    auth=get_auth_for_registry('ghcr.io', username='user', password_or_token='override_pass')
    assert auth==RegistryAuth.basic('user', 'override_pass')
    
    del os.environ['GITHUB_TOKEN']

def test_docker_config_identity_token():
    """Test Docker config identity token remains bearer auth."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path=Path(tmpdir)/'config.json'
        config={"auths":{"registry.example.com":{"identitytoken":"token123"}}}
        config_path.write_text(json.dumps(config))

        provider=DockerConfigAuthProvider(config_path)
        auth=provider.get_auth('registry.example.com')
        assert auth==RegistryAuth.bearer('token123')

def test_registry_auth_from_user_pass_or_token():
    assert RegistryAuth.from_user_pass_or_token() is None
    assert RegistryAuth.from_user_pass_or_token(password_or_token='token123')==RegistryAuth.bearer('token123')
    assert RegistryAuth.from_user_pass_or_token(username='user', password_or_token='pass')==RegistryAuth.basic('user', 'pass')

def test_missing_docker_config():
    """Test handling of missing Docker config."""
    provider=DockerConfigAuthProvider(Path('/nonexistent/config.json'))
    auth=provider.get_auth('any.registry')
    assert auth is None

def test_azure_cli_provider_non_acr():
    """Test Azure CLI provider skips non-ACR registries."""
    provider=AzureCLIAuthProvider()
    auth=provider.get_auth('docker.io')
    assert auth is None
    
    auth=provider.get_auth('ghcr.io')
    assert auth is None

if __name__=="__main__":
    test_environment_auth_provider()
    test_github_token_env()
    test_docker_config_auth_provider()
    test_docker_config_base64_decode()
    test_chain_auth_provider()
    test_get_auth_for_registry()
    test_missing_docker_config()
    test_azure_cli_provider_non_acr()
    print("✅ All authentication tests passed")
