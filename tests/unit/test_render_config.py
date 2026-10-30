from pathlib import Path

import yaml


def test_render_blueprint_is_free_web_only_with_secure_configuration():
    config = yaml.safe_load(Path("render.yaml").read_text())
    assert len(config["services"]) == 1
    service = config["services"][0]
    assert service["type"] == "web"
    assert service["plan"] == "free"
    assert "disk" not in service
    assert service["numInstances"] == 1
    assert "$PORT" in service["startCommand"]
    assert "uvicorn main:app" in service["startCommand"]
    assert service["healthCheckPath"] == "/api/v1/ready"
    variables = {entry["key"]: entry for entry in service["envVars"]}
    assert "REDIS_URL" not in variables
    assert variables["REGISTER_WEBHOOK"]["value"] == "false"
    python_version = variables["PYTHON_VERSION"]["value"]
    dockerfile = Path("docker/Dockerfile").read_text()
    assert dockerfile.count(f"FROM python:{python_version}-slim AS") == 2
    assert variables["TELEGRAM_WEBHOOK_SECRET"]["generateValue"] is True
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "DATABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "GROQ_API_KEY",
    ):
        assert variables[name]["sync"] is False
        assert "value" not in variables[name]
