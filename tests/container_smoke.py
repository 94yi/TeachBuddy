"""Verify the built Linux image with isolated temporary storage and a random port."""
import io
import json
import os
import secrets
import subprocess
import time
import zipfile
import httpx

name = "teachbuddy-smoke-" + secrets.token_hex(5)
env = os.environ.copy()
env.update(TEACHBUDDY_ENV="production", TEACHBUDDY_PASSWORD=secrets.token_urlsafe(24),
           TEACHBUDDY_SECRET=secrets.token_urlsafe(48), TEACHBUDDY_SECURE_COOKIE="false",
           TEACHBUDDY_DATA_DIR="/srv/data")
def docker(*args):
    return subprocess.check_output(["docker", *args], env=env, text=True, encoding="utf-8").strip()

started = False
try:
    docker("run", "-d", "--rm", "--name", name, "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=128M",
           "--tmpfs", "/srv/data:uid=10001,gid=10001,mode=0700,size=128M",
           "-p", "127.0.0.1::8000",
           "-e", "TEACHBUDDY_ENV", "-e", "TEACHBUDDY_PASSWORD", "-e", "TEACHBUDDY_SECRET",
           "-e", "TEACHBUDDY_SECURE_COOKIE", "-e", "TEACHBUDDY_DATA_DIR", "teachbuddy-web:local")
    started = True
    port = docker("port", name, "8000/tcp").split(":")[-1]
    with httpx.Client(base_url="http://127.0.0.1:" + port, timeout=10, trust_env=False) as client:
        for _ in range(60):
            try:
                if client.get("/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("Container failed to become healthy")
        assert client.get("/api/history").status_code == 401
        client.headers["X-TeachBuddy-Request"] = "1"
        assert client.post("/api/login", json={"password": env["TEACHBUDDY_PASSWORD"]}).status_code == 200
        templates = client.get("/api/templates").json()["templates"]
        assert len(templates) == 3
        lesson = client.post("/api/lesson/generate", json={
            "template_id": templates[0]["id"], "title": "Container lesson", "mode": "offline"}).json()
        assert "Container lesson" in lesson["body"]
        response = client.post("/api/export", json={"title": lesson["title"], "body": lesson["body"], "format": "docx"})
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert "word/document.xml" in archive.namelist()
        assert len(client.get("/api/history").json()["items"]) == 1
        assert docker("exec", name, "id", "-u") == "10001"
        assert client.get("/").status_code == 200
        print(json.dumps({"container_checks": "passed", "python": "3.12", "user": 10001,
                          "checks": ["health", "auth", "templates", "generation", "Word export", "history", "static page", "read-only non-root"]}))
finally:
    if started:
        docker("stop", "--time", "5", name)