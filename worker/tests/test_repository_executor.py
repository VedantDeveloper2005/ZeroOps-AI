import json

import pytest

from backend.services.repository_checks import RepositoryIsolationRequest, verify_isolation_attestation
from worker.repository_executor import DockerRepositoryCheckExecutor


IMAGE = "registry.azurecr.io/checks@sha256:" + "a" * 64


def request():
    return RepositoryIsolationRequest(stage="build", source_revision="b" * 40, source_digest="c" * 64)


def fake_docker(monkeypatch, *, wrong_source=False, unsafe=False):
    calls = []

    def docker(args, **_):
        calls.append(args)
        if args[:2] == ["image", "inspect"]:
            return json.dumps([{"Config": {"Labels": {
                "io.zeroops.source.revision": "d" * 40 if wrong_source else "b" * 40,
                "io.zeroops.source.digest": "c" * 64,
            }}}])
        if args[0] == "inspect":
            return json.dumps([{"HostConfig": {"NetworkMode": "host" if unsafe else "none",
                "ReadonlyRootfs": True, "Privileged": False, "Binds": None,
                "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"]},
                "Config": {"User": "10001:10001"}, "State": {"Running": True}, "Mounts": []}])
        return ""

    monkeypatch.setattr(DockerRepositoryCheckExecutor, "_docker", staticmethod(docker))
    return calls


def test_source_bound_verified_docker_isolation(monkeypatch):
    calls = fake_docker(monkeypatch)
    executor = DockerRepositoryCheckExecutor(IMAGE)
    attestation = executor.attest(request())
    assert verify_isolation_attestation(attestation, request()).valid
    create = next(args for args in calls if args[0] == "create")
    assert create[create.index("--network") + 1] == "none"
    assert "--read-only" in create and "--cap-drop" in create
    assert not any(arg in create for arg in ["--privileged", "--volume", "-v", "--env-file"])
    executor.close()
    assert calls[-1] == ["rm", "--force", attestation.isolation_id]


def test_wrong_source_never_starts_container(monkeypatch):
    calls = fake_docker(monkeypatch, wrong_source=True)
    with pytest.raises(ValueError, match="approved source"):
        DockerRepositoryCheckExecutor(IMAGE).attest(request())
    assert len(calls) == 1


def test_failed_network_enforcement_removes_container(monkeypatch):
    calls = fake_docker(monkeypatch, unsafe=True)
    with pytest.raises(RuntimeError, match="isolation"):
        DockerRepositoryCheckExecutor(IMAGE).attest(request())
    assert calls[-1][:2] == ["rm", "--force"]


def test_unpinned_image_rejected():
    with pytest.raises(ValueError):
        DockerRepositoryCheckExecutor("node:latest")


@pytest.mark.parametrize("cwd", ["../escape", "/etc", "a/../../etc", "a\\b"])
def test_host_paths_cannot_be_executed(monkeypatch, cwd):
    fake_docker(monkeypatch)
    executor = DockerRepositoryCheckExecutor(IMAGE)
    attestation = executor.attest(request())
    with pytest.raises(ValueError, match="working directory"):
        executor.execute(["node", "test.js"], relative_cwd=cwd, timeout_seconds=10, attestation=attestation)
