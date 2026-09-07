#!/usr/bin/env python3
"""Generate TypeScript interfaces from the shared JSON Schema.

The schema in ``packages/shared-schema/schemas`` is the single source of truth;
this script derives the TypeScript side so the two cannot drift.  Run it after
any schema change::

    python scripts/generate_types.py

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = REPO_ROOT / "packages" / "shared-schema" / "schemas" / "simulation.schema.json"
OUTPUT = REPO_ROOT / "apps" / "viewer" / "src" / "generated" / "schema.ts"

HEADER = """/* eslint-disable */
/**
 * GENERATED FILE - do not edit by hand.
 *
 * Source: packages/shared-schema/schemas/simulation.schema.json
 * Regenerate: python scripts/generate_types.py
 *
 * Research prototype - Not for clinical use.
 */
"""


def ts_type(schema: dict[str, Any]) -> str:
    """Map one JSON Schema node onto a TypeScript type expression."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])

    node_type = schema.get("type", "unknown")
    if isinstance(node_type, list):
        return " | ".join(ts_type({**schema, "type": single}) for single in node_type)

    if node_type == "array":
        items = schema.get("items", {})
        minimum, maximum = schema.get("minItems"), schema.get("maxItems")
        inner = ts_type(items)
        if minimum is not None and minimum == maximum:
            return f"[{', '.join([inner] * minimum)}]"
        return f"{inner}[]"
    return {
        "string": "string",
        "number": "number",
        "integer": "number",
        "boolean": "boolean",
        "null": "null",
        "object": "Record<string, unknown>",
    }.get(node_type, "unknown")


def render_interface(name: str, schema: dict[str, Any]) -> str:
    lines: list[str] = []
    description = schema.get("description")
    if description:
        lines.append("/**")
        for paragraph in description.split(". "):
            text = paragraph.strip().rstrip(".")
            if text:
                lines.append(f" * {text}.")
        lines.append(" */")
    lines.append(f"export interface {name} {{")
    required = set(schema.get("required", []))
    for key, prop in schema.get("properties", {}).items():
        unit = prop.get("x-unit")
        if unit:
            lines.append(f"  /** Unit: {unit} */")
        optional = "" if key in required else "?"
        lines.append(f"  {key}{optional}: {ts_type(prop)};")
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    version = schema.get("x-schema-version", "0.0.0")
    blocks = [HEADER, f"export const SCHEMA_VERSION = {json.dumps(version)};"]
    for name, definition in schema["$defs"].items():
        blocks.append(render_interface(name, definition))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(schema['$defs'])} interfaces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
