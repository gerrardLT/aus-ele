from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class LocalArtifactLake:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def write_artifact(
        self,
        *,
        layer: str,
        namespace: str,
        partition: str,
        payload,
        metadata: dict | None = None,
    ) -> dict:
        artifact_id = uuid4().hex
        partition_path = self.root_dir / layer / namespace / partition
        partition_path.mkdir(parents=True, exist_ok=True)

        payload_path = partition_path / f"{artifact_id}.json"
        metadata_path = partition_path / f"{artifact_id}.meta.json"

        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        envelope = {
            "artifact_id": artifact_id,
            "layer": layer,
            "namespace": namespace,
            "partition": partition,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **(metadata or {}),
        }
        metadata_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "artifact_id": artifact_id,
            "layer": layer,
            "namespace": namespace,
            "partition": partition,
            "organization_id": envelope.get("organization_id"),
            "workspace_id": envelope.get("workspace_id"),
            "payload_path": str(payload_path),
            "metadata_path": str(metadata_path),
        }
