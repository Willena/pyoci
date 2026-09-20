"""Authentication providers for container registries."""
import base64
import json
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional


@dataclass(frozen=True)
class RegistryAuth:
    """Typed registry authentication details."""

    kind: Literal['basic', 'bearer']
    secret: str
    username: Optional[str] = None

    @classmethod
    def from_user_pass_or_token(
        cls,
        password_or_token: Optional[str]=None,
        username: Optional[str]=None
    ) -> Optional['RegistryAuth']:
        """
        Convert username and password into RegistryAuth object.
        If only the password is defined, it will be considered as a bearer token.
        If both username and password are defined it will be considered as basic auth.
        In other cases return None.
        """
        if username and password_or_token:
            return cls.basic(username, password_or_token)
        if password_or_token:
            return cls.bearer(password_or_token)
        return None

    @classmethod
    def basic(cls, username: str, password: str) -> 'RegistryAuth':
        return cls(kind='basic', username=username, secret=password)

    @classmethod
    def bearer(cls, token: str) -> 'RegistryAuth':
        return cls(kind='bearer', secret=token)

    @property
    def password(self) -> Optional[str]:
        return self.secret if self.kind == 'basic' else None

    @property
    def token(self) -> Optional[str]:
        return self.secret if self.kind == 'bearer' else None


class AuthProvider(ABC):
    """Base authentication provider interface."""

    @abstractmethod
    def get_auth(self, registry: str) -> Optional[RegistryAuth]:
        """Return typed credentials for registry, or None."""
        pass


class EnvironmentAuthProvider(AuthProvider):
    """Read credentials from environment variables."""

    def get_auth(self, registry: str) -> Optional[RegistryAuth]:
        user = os.getenv('REGISTRY_USERNAME')
        pwd = os.getenv('REGISTRY_PASSWORD')
        if user and pwd: return RegistryAuth.basic(user, pwd)

        if 'ghcr.io' in registry:
            token = os.getenv('GITHUB_TOKEN')
            if token: return RegistryAuth.bearer(token)

        token = os.getenv('REGISTRY_TOKEN')
        if token: return RegistryAuth.bearer(token)

        return None


class DockerConfigAuthProvider(AuthProvider):
    """Read credentials from ~/.docker/config.json."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / '.docker' / 'config.json'

    def _load_config(self) -> Optional[Dict]:
        if not self.config_path.exists(): return None
        try:
            return json.loads(self.config_path.read_text())
        except:
            return None

    def _decode_auth(self, auth_str: str) -> tuple[str, str]:
        """Decode base64 auth string to (username, password)."""
        decoded = base64.b64decode(auth_str).decode('utf-8')
        if ':' in decoded:
            user, pwd = decoded.split(':', 1)
            return (user, pwd)
        return ('', decoded)

    def _lookup_auth_data(self, registry: str) -> Optional[Dict]:
        cfg = self._load_config()
        if not cfg: return None

        auths = cfg.get('auths', {})

        # Docker Hub special cases
        docker_hub_keys = ['https://index.docker.io/v1/', 'index.docker.io', 'docker.io']
        if registry in docker_hub_keys or registry == 'docker.io':
            for key in docker_hub_keys:
                if key in auths:
                    return auths[key]

        # Try various registry URL formats
        for reg_key in [registry, f'https://{registry}', f'https://{registry}/v2/', f'{registry}/v2/']:
            if reg_key in auths:
                return auths[reg_key]

        return None

    def get_auth(self, registry: str) -> Optional[RegistryAuth]:
        auth_data = self._lookup_auth_data(registry)
        if not auth_data: return None

        if 'identitytoken' in auth_data:
            return RegistryAuth.bearer(auth_data['identitytoken'])
        if 'auth' in auth_data:
            user, pwd = self._decode_auth(auth_data['auth'])
            return RegistryAuth.basic(user, pwd)
        if 'username' in auth_data and 'password' in auth_data:
            return RegistryAuth.basic(auth_data['username'], auth_data['password'])

        return None


class AzureCLIAuthProvider(AuthProvider):
    """Get credentials from Azure CLI for ACR."""

    def get_auth(self, registry: str) -> Optional[RegistryAuth]:
        if 'azurecr.io' not in registry: return None

        try:
            result = subprocess.run(
                ['az', 'acr', 'login', '--name', registry.split('.')[0], '--expose-token', '--output', 'json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return RegistryAuth.basic('00000000-0000-0000-0000-000000000000', data['accessToken'])
        except:
            pass

        return None


class ChainAuthProvider(AuthProvider):
    """Try multiple auth providers in sequence."""

    def __init__(self, providers: list):
        self.providers = providers

    def get_auth(self, registry: str) -> Optional[RegistryAuth]:
        for provider in self.providers:
            auth = provider.get_auth(registry)
            if auth:
                return auth
        return None


def get_default_auth_provider() -> AuthProvider:
    """Return default auth provider chain."""
    return ChainAuthProvider([
        EnvironmentAuthProvider(),
        DockerConfigAuthProvider(),
        AzureCLIAuthProvider()
    ])


def get_auth_for_registry(
        registry: str,
        username: Optional[str] = None,
        password_or_token: Optional[str] = None,
) -> Optional[RegistryAuth]:
    """Get typed auth for registry, trying explicit values and provider chain."""

    if username or password_or_token:
        return RegistryAuth.from_user_pass_or_token(username=username, password_or_token=password_or_token)

    provider = get_default_auth_provider()
    return provider.get_auth(registry)
