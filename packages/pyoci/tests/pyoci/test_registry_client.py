"""Tests for registry client functionality."""
import io
import json
import urllib.error
from unittest.mock import patch
from pyoci.registry_client import parse_image_reference, RegistryClient
from pyoci.auth import RegistryAuth

def test_parse_image_reference():
    """Test parsing various image reference formats."""
    assert parse_image_reference("ghcr.io/user/app:v1")==("ghcr.io","user/app","v1")
    assert parse_image_reference("docker.io/library/python:3.11")==("docker.io","library/python","3.11")
    assert parse_image_reference("localhost:5000/test:latest")==("localhost:5000","test","latest")
    assert parse_image_reference("myapp:v2")==("docker.io","library/myapp","v2")
    assert parse_image_reference("user/app:tag")==("docker.io","user/app","tag")
    assert parse_image_reference("localhost:5000/test")==("localhost:5000","test","latest")
    assert parse_image_reference("alpine")==("docker.io","library/alpine","latest")

def test_registry_client_construction():
    """Test RegistryClient initialization."""
    client=RegistryClient("ghcr.io","user/repo")
    assert client.registry=="ghcr.io"
    assert client.repository=="user/repo"
    assert client.base_url=="https://ghcr.io/v2"
    assert client.auth is None
    
    client_auth=RegistryClient("localhost:5000","test",auth=RegistryAuth.bearer("token123"))
    assert client_auth.auth==RegistryAuth.bearer("token123")

    client_basic=RegistryClient("ghcr.io","user/repo",auth=RegistryAuth.basic("alice","secret"))
    assert client_basic.auth==RegistryAuth.basic("alice","secret")

    client_bearer=RegistryClient("ghcr.io","user/repo",auth=RegistryAuth.bearer("token456"))
    assert client_bearer.auth==RegistryAuth.bearer("token456")
    
    # Test docker.io translation to registry-1.docker.io
    client_dockerhub=RegistryClient("docker.io","library/python")
    assert client_dockerhub.registry=="registry-1.docker.io"
    assert client_dockerhub.base_url=="https://registry-1.docker.io/v2"

def test_registry_url_construction():
    """Test URL construction for registry operations."""
    client=RegistryClient("ghcr.io","user/app")
    
    blob_url=f"{client.base_url}/{client.repository}/blobs/sha256:abc123"
    assert blob_url=="https://ghcr.io/v2/user/app/blobs/sha256:abc123"
    
    manifest_url=f"{client.base_url}/{client.repository}/manifests/v1.0"
    assert manifest_url=="https://ghcr.io/v2/user/app/manifests/v1.0"
    
    upload_url=f"{client.base_url}/{client.repository}/blobs/uploads/"
    assert upload_url=="https://ghcr.io/v2/user/app/blobs/uploads/"

class MockHTTPResponse:
    def __init__(self, status, body=b"", headers=None):
        self.status=status
        self._body=body
        self.headers=headers or {}
    
    def read(self):
        return self._body
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc, tb):
        return False

def make_http_error(req, status, headers=None, body=b""):
    return urllib.error.HTTPError(req.full_url, status, "error", headers or {}, io.BytesIO(body))

def test_push_blob_refreshes_bearer_token_after_pull_scoped_exists_check(tmp_path):
    blob_path=tmp_path/"layer.tar"
    blob_path.write_bytes(b"layer-data")
    client=RegistryClient("ghcr.io","user/app",auth=RegistryAuth.basic("user","pass"))
    requests=[]
    
    def fake_urlopen(req):
        auth=req.get_header("Authorization")
        requests.append((req.get_method(), req.full_url, auth))
        
        if req.full_url=="https://auth.example/token?service=ghcr.io&scope=repository%3Auser%2Fapp%3Apull":
            return MockHTTPResponse(200, json.dumps({"token":"pull-token"}).encode())
        
        if req.full_url=="https://auth.example/token?service=ghcr.io&scope=repository%3Auser%2Fapp%3Apull%2Cpush":
            return MockHTTPResponse(200, json.dumps({"token":"push-token"}).encode())
        
        if req.full_url=="https://ghcr.io/v2/user/app/blobs/sha256:abc123":
            if auth=="Bearer pull-token":
                raise make_http_error(req, 404)
            raise make_http_error(
                req,
                401,
                {"Www-Authenticate":'Bearer realm="https://auth.example/token",service="ghcr.io",scope="repository:user/app:pull"'},
            )
        
        if req.full_url=="https://ghcr.io/v2/user/app/blobs/uploads/":
            if auth=="Bearer push-token":
                return MockHTTPResponse(202, headers={"Location":"/upload?state=1"})
            raise make_http_error(
                req,
                401,
                {"Www-Authenticate":'Bearer realm="https://auth.example/token",service="ghcr.io",scope="repository:user/app:pull,push"'},
            )
        
        if req.full_url=="https://ghcr.io/upload?state=1&digest=sha256:abc123":
            assert auth=="Bearer push-token"
            return MockHTTPResponse(201)
        
        raise AssertionError(f"Unexpected request: {req.get_method()} {req.full_url}")
    
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        pushed=client.push_blob("sha256:abc123", blob_path, check_exists=True)
    
    assert pushed is True
    assert client._bearer_tokens[("https://auth.example/token","ghcr.io","repository:user/app:pull")]=="pull-token"
    assert client._bearer_tokens[("https://auth.example/token","ghcr.io","repository:user/app:pull,push")]=="push-token"
    assert ("POST","https://ghcr.io/v2/user/app/blobs/uploads/","Bearer pull-token") in requests
    assert ("POST","https://ghcr.io/v2/user/app/blobs/uploads/","Bearer push-token") in requests

def test_basic_auth_from_typed_auth_is_sent_on_first_request():
    requests=[]
    client=RegistryClient("registry.example.com","team/app",auth=RegistryAuth.basic("user","pass"))

    def fake_urlopen(req):
        requests.append((req.get_method(), req.full_url, req.get_header("Authorization")))
        return MockHTTPResponse(200)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        exists=client.blob_exists("sha256:abc123")

    assert exists is True
    assert requests==[
        ("HEAD", "https://registry.example.com/v2/team/app/blobs/sha256:abc123", "Basic dXNlcjpwYXNz")
    ]

if __name__=="__main__":
    test_parse_image_reference()
    test_registry_client_construction()
    test_registry_url_construction()
    print("✅ All registry client tests passed")
