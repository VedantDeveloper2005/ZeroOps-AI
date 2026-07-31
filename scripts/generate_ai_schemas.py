"""Generate runtime and Microsoft Foundry-safe AI response schemas.

The Pydantic contracts remain authoritative. Runtime schemas retain rich
validation keywords, while Foundry schemas are reduced to the strict structured
output subset and are always revalidated by Pydantic after inference.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.contracts.ai import RepositoryAssessment, TerraformBundle


SPEC_ROOT = REPOSITORY_ROOT / "ai-specs"
SCHEMAS = (
    (
        RepositoryAssessment,
        SPEC_ROOT / "repository-analysis" / "response.schema.json",
        SPEC_ROOT / "repository-analysis" / "response.foundry.schema.json",
    ),
    (
        TerraformBundle,
        SPEC_ROOT / "terraform-generation" / "response.schema.json",
        SPEC_ROOT / "terraform-generation" / "response.foundry.schema.json",
    ),
)

_UNSUPPORTED_FOUNDRY_KEYWORDS = {
    "$schema",
    "$defs",
    "$ref",
    "default",
    "format",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minContains",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "pattern",
    "patternProperties",
    "propertyNames",
    "title",
    "unevaluatedItems",
    "unevaluatedProperties",
    "uniqueItems",
}


def _dereference(value: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_dereference(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        reference = value["$ref"]
        prefix = "#/$defs/"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise ValueError(f"Unsupported schema reference: {reference!r}")
        name = reference.removeprefix(prefix)
        if name not in definitions:
            raise ValueError(f"Unknown schema definition: {name}")
        merged = copy.deepcopy(definitions[name])
        merged.update({key: item for key, item in value.items() if key != "$ref"})
        return _dereference(merged, definitions)
    return {
        key: _dereference(item, definitions)
        for key, item in value.items()
        if key != "$defs"
    }


def _foundry_subset(value: Any, *, property_map: bool = False) -> Any:
    if isinstance(value, list):
        return [_foundry_subset(item) for item in value]
    if not isinstance(value, dict):
        return value
    if property_map:
        return {
            str(field_name): _foundry_subset(field_schema)
            for field_name, field_schema in value.items()
        }

    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in _UNSUPPORTED_FOUNDRY_KEYWORDS:
            continue
        if key == "const":
            result["enum"] = [item]
            continue
        if key == "description":
            result[key] = str(item)[:1_024]
            continue
        result[key] = _foundry_subset(item, property_map=key == "properties")

    if result.get("type") == "object":
        properties = result.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("Foundry object schemas require explicit properties.")
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


def runtime_schema(contract: type) -> dict[str, Any]:
    return contract.model_json_schema()


def foundry_schema(contract: type) -> dict[str, Any]:
    rich = runtime_schema(contract)
    definitions = rich.get("$defs", {})
    dereferenced = _dereference(rich, definitions)
    return _foundry_subset(dereferenced)


def _serialized(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def generate(*, check: bool) -> list[Path]:
    changed: list[Path] = []
    for contract, runtime_path, foundry_path in SCHEMAS:
        expected = {
            runtime_path: _serialized(runtime_schema(contract)),
            foundry_path: _serialized(foundry_schema(contract)),
        }
        for path, content in expected.items():
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current == content:
                continue
            changed.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if checked-in schemas differ from the canonical contracts.",
    )
    arguments = parser.parse_args()
    changed = generate(check=arguments.check)
    if arguments.check and changed:
        for path in changed:
            print(path.relative_to(REPOSITORY_ROOT))
        return 1
    for path in changed:
        print(path.relative_to(REPOSITORY_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
