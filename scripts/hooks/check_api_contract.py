#!/usr/bin/env python3
"""API contract sync verification script.

Compares Pydantic models in api/schemas.py with TypeScript interfaces in
frontend/src/types/index.ts to detect contract drift.
"""

import json
import re
from pathlib import Path
from typing import Any

# Type mapping from Python to TypeScript
PYTHON_TO_TS_TYPES = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "list": "Array",
    "dict": "Record",
    "datetime": "string",
    "Any": "unknown",
    "None": "null",
}


def extract_pydantic_models(content: str) -> dict[str, dict[str, str]]:
    """Extract Pydantic model class names and their field names with types.

    Args:
        content: The content of schemas.py

    Returns:
        Dict mapping model name to dict of field names and their types
    """
    models: dict[str, dict[str, str]] = {}

    # Find all class definitions that inherit from BaseModel
    # Pattern: class ClassName(BaseModel): or class ClassName(..., BaseModel):
    class_pattern = re.compile(r"^class\s+(\w+)\s*\([^)]*BaseModel[^)]*\)\s*:", re.MULTILINE)

    for match in class_pattern.finditer(content):
        class_name = match.group(1)
        class_start = match.end()

        # Find the end of the class (next class definition or end of file)
        next_class_match = class_pattern.search(content, class_start)
        if next_class_match:
            class_end = next_class_match.start()
        else:
            class_end = len(content)

        class_body = content[class_start:class_end]

        # Extract field definitions
        # Pattern: field_name: type or field_name: type = Field(...) or field_name: type = None
        _default = r"(?:Field\([^)]*\)|None|True|False|\[.*?\]|\{.*?\}|\"[^\"]*\"|'[^']*')"
        field_pattern = re.compile(
            rf"^(\w+)\s*:\s*([^=#\n]+?)(?:\s*=\s*(?:{_default}))?\s*(?:#.*)?$",
            re.MULTILINE,
        )

        fields: dict[str, str] = {}
        for field_match in field_pattern.finditer(class_body):
            field_name = field_match.group(1)
            field_type = field_match.group(2).strip()

            # Clean up the type annotation
            # Remove generics for simple comparison
            simple_type = field_type
            for generic in ["list[", "dict[", "tuple["]:
                if generic in simple_type:
                    simple_type = simple_type.split("[")[0]

            # Handle Optional types
            if " | None" in simple_type or " | None" in field_type:
                simple_type = simple_type.replace(" | None", "").strip()

            # Handle old-style Optional
            if simple_type.startswith("Optional["):
                simple_type = simple_type[9:-1]

            fields[field_name] = simple_type

        if fields:
            models[class_name] = fields

    return models


def extract_typescript_interfaces(content: str) -> dict[str, dict[str, str]]:
    """Extract TypeScript interface/type names and their field names with types.

    Args:
        content: The content of index.ts

    Returns:
        Dict mapping interface name to dict of field names and their types
    """
    interfaces: dict[str, dict[str, str]] = {}

    # Find all interface and type definitions
    # Pattern: export interface InterfaceName { or export type TypeName = {
    interface_pattern = re.compile(r"^export\s+(?:interface|type)\s+(\w+)\s*(?:extends\s+\w+\s*)?{", re.MULTILINE)

    for match in interface_pattern.finditer(content):
        interface_name = match.group(1)
        interface_start = match.end()

        # Find the matching closing brace
        brace_count = 1
        i = interface_start
        while i < len(content) and brace_count > 0:
            if content[i] == "{":
                brace_count += 1
            elif content[i] == "}":
                brace_count -= 1
            i += 1

        interface_end = i - 1
        interface_body = content[interface_start:interface_end]

        # Extract field definitions
        # Pattern: field_name: type or field_name?: type (optional)
        field_pattern = re.compile(r"^(\w+)\s*(\?)?:\s*([^,{\n]+?)(?:\s*=\s*[^,{\n]+)?\s*(?:#.*)?$", re.MULTILINE)

        fields: dict[str, str] = {}
        for field_match in field_pattern.finditer(interface_body):
            field_name = field_match.group(1)
            field_type = field_match.group(3).strip()

            # Clean up the type annotation
            # Remove array brackets for simple comparison
            simple_type = field_type
            if simple_type.endswith("[]"):
                simple_type = "Array"
            elif "<" in simple_type and ">" in simple_type:
                # Extract the generic type name (e.g., Record<string, unknown> -> Record)
                simple_type = simple_type.split("<")[0]

            # Handle union types - take the first non-null type
            if " | " in simple_type:
                types = [t.strip() for t in simple_type.split(" | ")]
                non_null_types = [t for t in types if t != "null"]
                if non_null_types:
                    simple_type = non_null_types[0]

            # Remove trailing optional markers
            simple_type = simple_type.rstrip("?")

            fields[field_name] = simple_type

        if fields:
            interfaces[interface_name] = fields

    return interfaces


def normalize_model_name(name: str) -> str:
    """Normalize a model/interface name for comparison.

    Removes common suffixes like 'Schema', 'Response', 'Request', etc.
    """
    suffixes_to_remove = ["Schema", "Response", "Request", "Create", "Update", "ListItem"]
    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def find_matching_pairs(
    pydantic_models: dict[str, dict[str, str]],
    ts_interfaces: dict[str, dict[str, str]]
) -> list[tuple[str, str, dict[str, str], dict[str, str]]]:
    """Find matching Pydantic model and TypeScript interface pairs.

    Returns:
        List of tuples (pydantic_name, ts_name, pydantic_fields, ts_fields)
    """
    pairs = []

    for py_name, py_fields in pydantic_models.items():
        # Normalize the name for comparison
        normalized_py_name = normalize_model_name(py_name)

        # Find matching TypeScript interface
        for ts_name, ts_fields in ts_interfaces.items():
            normalized_ts_name = normalize_model_name(ts_name)

            if normalized_py_name.lower() == normalized_ts_name.lower():
                pairs.append((py_name, ts_name, py_fields, ts_fields))
                break

    return pairs


def compare_types(python_type: str, ts_type: str) -> bool:
    """Compare Python type with TypeScript type.

    Returns True if types are compatible.
    """
    # Normalize Python type
    py_type = python_type.strip()

    # Handle generic types
    if "[" in py_type:
        py_type = py_type.split("[")[0]

    # Normalize TS type
    ts_normalized = ts_type.strip()

    # Direct mapping
    if py_type in PYTHON_TO_TS_TYPES:
        return PYTHON_TO_TS_TYPES[py_type] == ts_normalized

    # Check for name match (e.g., custom types, enums)
    return py_type.lower() == ts_normalized.lower()


def check_contract_drift(
    pydantic_models: dict[str, dict[str, str]],
    ts_interfaces: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Check for contract drift between Pydantic models and TypeScript interfaces.

    Returns:
        Dict with status and drifts list
    """
    drifts = []

    pairs = find_matching_pairs(pydantic_models, ts_interfaces)

    for py_name, ts_name, py_fields, ts_fields in pairs:
        # Check for fields in backend but missing from frontend
        backend_only = set(py_fields.keys()) - set(ts_fields.keys())
        if backend_only:
            drifts.append({
                "model": py_name,
                "interface": ts_name,
                "type": "backend_only_fields",
                "fields": list(backend_only),
                "message": f"Fields in {py_name} but missing from {ts_name}"
            })

        # Check for fields in frontend but missing from backend
        frontend_only = set(ts_fields.keys()) - set(py_fields.keys())
        if frontend_only:
            drifts.append({
                "model": py_name,
                "interface": ts_name,
                "type": "frontend_only_fields",
                "fields": list(frontend_only),
                "message": f"Fields in {ts_name} but missing from {py_name}"
            })

        # Check for type mismatches on common fields
        common_fields = set(py_fields.keys()) & set(ts_fields.keys())
        for field in common_fields:
            py_type = py_fields[field]
            ts_type = ts_fields[field]

            if not compare_types(py_type, ts_type):
                drifts.append({
                    "model": py_name,
                    "interface": ts_name,
                    "type": "type_mismatch",
                    "field": field,
                    "backend_type": py_type,
                    "frontend_type": ts_type,
                    "message": f"Field '{field}' type mismatch: {py_type} (Python) vs {ts_type} (TypeScript)"
                })

    # Check for unpaired models (no matching interface found)
    py_names_normalized = {normalize_model_name(name): name for name in pydantic_models.keys()}
    ts_names_normalized = {normalize_model_name(name): name for name in ts_interfaces.keys()}

    unpaired_backend = set(py_names_normalized.keys()) - set(ts_names_normalized.keys())
    if unpaired_backend:
        for normalized_name in unpaired_backend:
            original_name = py_names_normalized[normalized_name]
            drifts.append({
                "model": original_name,
                "type": "unpaired_backend_model",
                "message": f"Pydantic model '{original_name}' has no matching TypeScript interface"
            })

    unpaired_frontend = set(ts_names_normalized.keys()) - set(py_names_normalized.keys())
    if unpaired_frontend:
        for normalized_name in unpaired_frontend:
            original_name = ts_names_normalized[normalized_name]
            drifts.append({
                "interface": original_name,
                "type": "unpaired_frontend_interface",
                "message": f"TypeScript interface '{original_name}' has no matching Pydantic model"
            })

    return {
        "status": "pass" if not drifts else "drift",
        "drifts": drifts
    }


def main() -> None:
    """Main entry point."""
    repo_root = Path(__file__).parent.parent.parent
    schemas_path = repo_root / "api" / "schemas.py"
    types_path = repo_root / "frontend" / "src" / "types" / "index.ts"

    # Read files
    try:
        schemas_content = schemas_path.read_text()
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "message": f"Could not find schemas.py at {schemas_path}"
        }))
        return

    try:
        types_content = types_path.read_text()
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "message": f"Could not find index.ts at {types_path}"
        }))
        return

    # Extract models and interfaces
    pydantic_models = extract_pydantic_models(schemas_content)
    ts_interfaces = extract_typescript_interfaces(types_content)

    # Check for drift
    result = check_contract_drift(pydantic_models, ts_interfaces)

    # Output JSON to stdout
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
