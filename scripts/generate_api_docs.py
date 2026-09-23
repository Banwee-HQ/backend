#!/usr/bin/env python3
"""Regenerate api.md and postman_collection.json from the live FastAPI OpenAPI schema.

This script is the authoritative generator referenced by api.md's own
"Keeping this reference current" section: it imports the real `app` object
from main.py, calls `app.openapi()`, and derives both documentation artifacts
directly from that schema so they can never drift from the actual routes.

Usage:
    python3 scripts/generate_api_docs.py

It writes api.md and postman_collection.json in the repo root (paths are
resolved relative to this file, so it can be run from any cwd).
"""
import copy
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("ENVIRONMENT", "local")

# Importing main.py builds the FastAPI `app` (routers, middleware, exception
# handlers) but does not run the lifespan/startup code, so no DB connection
# or external services are required just to read the schema.
from main import app  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from core.dependencies import require_auth, require_admin  # noqa: E402

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


# --------------------------------------------------------------------------
# Auth introspection: walk each route's real dependency graph (not a text
# heuristic) to see whether require_auth / require_admin is actually wired
# in, so the "Auth" column reflects what the code does rather than what a
# previous generation guessed.
# --------------------------------------------------------------------------
def _walk_dependant(dependant, seen=None):
    if seen is None:
        seen = set()
    calls = []
    if dependant is None:
        return calls
    if dependant.call is not None:
        calls.append(dependant.call)
    for sub in dependant.dependencies:
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        calls.extend(_walk_dependant(sub, seen))
    return calls


def build_auth_map():
    """Return {(METHOD, path): 'admin'|'auth'|'none'} from the live app.routes."""
    auth_map = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = _walk_dependant(route.dependant)
        has_admin = require_admin in calls
        has_auth = require_auth in calls
        level = "admin" if has_admin else ("auth" if has_auth else "none")
        for method in route.methods:
            if method == "HEAD":
                continue
            key = (method, route.path)
            # If duplicate route registrations disagree (they shouldn't),
            # prefer the stricter requirement rather than silently picking one.
            if key in auth_map:
                order = {"none": 0, "auth": 1, "admin": 2}
                if order[level] > order[auth_map[key]]:
                    auth_map[key] = level
            else:
                auth_map[key] = level
    return auth_map


# --------------------------------------------------------------------------
# Schema helpers
# --------------------------------------------------------------------------
def resolve_ref(schema_obj, components):
    if isinstance(schema_obj, dict) and "$ref" in schema_obj:
        ref = schema_obj["$ref"]
        name = ref.split("/")[-1]
        return name, components.get(name, {})
    return None, schema_obj


def request_body_cell(operation, components):
    """Return (schema_display_name, content_type) for the Request body column."""
    rb = operation.get("requestBody")
    if not rb:
        return None, None
    content = rb.get("content", {})
    if not content:
        return None, None
    content_type = next(iter(content.keys()))
    schema_obj = content[content_type].get("schema", {})
    ref_name, resolved = resolve_ref(schema_obj, components)
    if ref_name:
        return ref_name, content_type
    title = schema_obj.get("title")
    if title:
        return title, content_type
    return "Body", content_type


def format_parameters(operation):
    params = operation.get("parameters", []) or []
    cells = []
    for p in params:
        marker = "*" if p.get("required") else ""
        cells.append(f"{p.get('in')}:{p.get('name')}{marker}")
    return cells


def format_responses(operation):
    return [code for code in operation.get("responses", {}).keys() if code != "default"]


# --------------------------------------------------------------------------
# Example value generation for Postman request bodies
# --------------------------------------------------------------------------
_STRING_FORMAT_EXAMPLES = {
    "email": "user@example.com",
    "uuid": "00000000-0000-0000-0000-000000000000",
    "date": "2024-01-01",
    "date-time": "2024-01-01T00:00:00Z",
    "uri": "https://example.com",
    "password": "string",
    "binary": "string",
}


def _first_concrete_branch(branches):
    """Pick the first non-null branch out of an anyOf/oneOf list."""
    for b in branches:
        if b.get("type") == "null":
            continue
        return b
    return branches[0] if branches else {}


def example_for_schema(schema_obj, components, depth=0, seen_refs=None):
    if seen_refs is None:
        seen_refs = set()
    if depth > 6:
        return None
    if not isinstance(schema_obj, dict):
        return None

    if "$ref" in schema_obj:
        ref_name, resolved = resolve_ref(schema_obj, components)
        if ref_name in seen_refs:
            return {}
        return example_for_schema(resolved, components, depth + 1, seen_refs | {ref_name})

    if "example" in schema_obj:
        return schema_obj["example"]
    if schema_obj.get("default") is not None:
        return schema_obj["default"]

    if "anyOf" in schema_obj:
        branch = _first_concrete_branch(schema_obj["anyOf"])
        return example_for_schema(branch, components, depth + 1, seen_refs)
    if "oneOf" in schema_obj:
        branch = _first_concrete_branch(schema_obj["oneOf"])
        return example_for_schema(branch, components, depth + 1, seen_refs)
    if "allOf" in schema_obj:
        merged = {}
        for part in schema_obj["allOf"]:
            _, resolved = resolve_ref(part, components) if "$ref" in part else (None, part)
            if isinstance(resolved, dict):
                merged.update(resolved)
        return example_for_schema(merged, components, depth + 1, seen_refs)

    if "enum" in schema_obj and schema_obj["enum"]:
        return schema_obj["enum"][0]

    schema_type = schema_obj.get("type")

    if schema_type == "object" or "properties" in schema_obj:
        props = schema_obj.get("properties", {})
        out = {}
        for name, sub_schema in props.items():
            out[name] = example_for_schema(sub_schema, components, depth + 1, seen_refs)
        return out

    if schema_type == "array":
        items = schema_obj.get("items", {})
        item_example = example_for_schema(items, components, depth + 1, seen_refs)
        return [item_example] if item_example is not None else []

    if schema_type == "string":
        fmt = schema_obj.get("format")
        if fmt in _STRING_FORMAT_EXAMPLES:
            return _STRING_FORMAT_EXAMPLES[fmt]
        return "string"

    if schema_type == "integer":
        return 1

    if schema_type == "number":
        return 1.0

    if schema_type == "boolean":
        return True

    if schema_type is None:
        return {}

    return None


# --------------------------------------------------------------------------
# api.md generation
# --------------------------------------------------------------------------
def md_escape(text):
    if text is None:
        return ""
    return str(text).replace("|", "\\|")


def build_operations(schema, auth_map):
    components = schema.get("components", {}).get("schemas", {})
    paths = schema.get("paths", {})
    ops = []
    for path, methods in paths.items():
        for method, operation in methods.items():
            if method not in HTTP_METHODS:
                continue
            method_upper = method.upper()
            tags = operation.get("tags") or []
            tag = tags[0] if tags else "Ungrouped"
            auth_level = auth_map.get((method_upper, path), "none")
            auth_yes = auth_level in ("auth", "admin")
            body_name, body_ct = request_body_cell(operation, components)
            ops.append({
                "path": path,
                "method": method_upper,
                "tag": tag,
                "summary": operation.get("summary") or "",
                "auth_yes": auth_yes,
                "auth_level": auth_level,
                "parameters": format_parameters(operation),
                "body_name": body_name,
                "body_ct": body_ct,
                "responses": format_responses(operation),
                "operation": operation,
            })
    return ops


def render_api_md(ops, total_ops, total_paths):
    groups = {}
    for op in ops:
        groups.setdefault(op["tag"], []).append(op)
    for tag in groups:
        groups[tag].sort(key=lambda o: (o["path"], o["method"]))

    sorted_tags = sorted(groups.keys(), key=lambda t: t.lower())

    lines = []
    lines.append("# Banwee API Reference")
    lines.append("")
    lines.append(
        f"> **Source of truth:** generated from the running FastAPI application "
        f"schema (`{total_ops} operations across {total_paths} paths`).")
    lines.append("")
    lines.append("## Environments")
    lines.append("")
    lines.append("| Environment | Base URL |")
    lines.append("| --- | --- |")
    lines.append("| Local | `http://localhost:8000` |")
    lines.append("| Hosted | Set `baseUrl` to the deployed API origin |")
    lines.append("")
    lines.append(
        "All versioned endpoints use the `/v1` prefix. Interactive OpenAPI "
        "documentation is available at `/docs`; the raw schema is available "
        "at `/openapi.json`.")
    lines.append("")
    lines.append("## Authentication")
    lines.append("")
    lines.append(
        "Send the access token returned by login in the following header for "
        "protected operations:")
    lines.append("")
    lines.append("```http")
    lines.append("Authorization: Bearer <access_token>")
    lines.append("```")
    lines.append("")
    lines.append(
        "The `Auth` column below is derived from each route's actual "
        "dependencies (`require_auth` / `require_admin`), not inferred. "
        "`No` means the operation has neither dependency and can be called "
        "without a token - this includes registration, login, token refresh, "
        "password recovery, email verification, OAuth sign-in, health checks, "
        "the service root, public catalog/browsing reads (products, "
        "categories, reviews, shipping methods, tax lookups), and webhook "
        "receivers that authenticate by other means (for example the Stripe "
        "webhook validates the Stripe signature instead of a bearer token). "
        "Authorization failures return `401`; permission failures return "
        "`403`; validation failures return `422`.")
    lines.append("")
    lines.append("## Conventions")
    lines.append("")
    lines.append(
        "- JSON request and response bodies use `Content-Type: application/json` "
        "unless an operation declares another media type.")
    lines.append(
        "- Path parameters are shown in braces, for example "
        "`/v1/products/{product_id}`.")
    lines.append(
        "- Query, path, and header parameters are listed for every operation "
        "where FastAPI exposes them.")
    lines.append(
        "- Request and response model names link back to the schemas in the "
        "generated OpenAPI document available at `/openapi.json`.")
    lines.append("")

    for tag in sorted_tags:
        lines.append(f"## {tag}")
        lines.append("")
        lines.append("| Method | Path | Summary | Auth | Parameters | Request body | Responses |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for op in groups[tag]:
            params_cell = ", ".join(f"`{md_escape(p)}`" for p in op["parameters"]) or "—"
            if op["body_name"]:
                body_cell = f"`{md_escape(op['body_name'])}` ({op['body_ct']})"
            else:
                body_cell = "—"
            responses_cell = ", ".join(f"`{c}`" for c in op["responses"]) or "—"
            auth_cell = "Yes" if op["auth_yes"] else "No"
            lines.append(
                f"| `{op['method']}` | `{md_escape(op['path'])}` | "
                f"{md_escape(op['summary'])} | {auth_cell} | {params_cell} | "
                f"{body_cell} | {responses_cell} |")
        lines.append("")

    lines.append("## Error responses")
    lines.append("")
    lines.append("| Status | Meaning |")
    lines.append("| --- | --- |")
    lines.append("| `400` | Request rejected by business validation. |")
    lines.append("| `401` | Missing or invalid authentication. |")
    lines.append("| `403` | Authenticated user lacks permission. |")
    lines.append("| `404` | Resource does not exist. |")
    lines.append("| `409` | Request conflicts with current state. |")
    lines.append("| `422` | Request failed FastAPI schema validation. |")
    lines.append("| `429` | Rate limit exceeded. |")
    lines.append("| `500` | Unexpected server error; inspect structured logs and request ID. |")
    lines.append("")
    lines.append("## Keeping this reference current")
    lines.append("")
    lines.append(
        "Regenerate this file and `postman_collection.json` after changing a "
        "route, schema, or authentication rule. The generated artifacts must "
        "match `app.openapi()` before release. Run "
        "`python3 scripts/generate_api_docs.py` to regenerate both files from "
        "the live schema.")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# postman_collection.json generation
# --------------------------------------------------------------------------
def path_to_postman(path):
    """Split an OpenAPI path into Postman path segments, and templatize params."""
    segments = [seg for seg in path.split("/") if seg]
    out = []
    for seg in segments:
        if seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            out.append("{{" + name + "}}")
        else:
            out.append(seg)
    return out


def build_postman_item(op, components):
    operation = op["operation"]
    method = op["method"]
    path = op["path"]
    segments = path_to_postman(path)

    headers = []
    raw_params = operation.get("parameters", []) or []

    query_entries = []
    required_query_pairs = []
    for p in raw_params:
        if p.get("in") == "header":
            headers.append({
                "key": p["name"],
                "value": "{{" + p["name"] + "}}",
                "type": "text",
                "disabled": not p.get("required", False),
            })
        elif p.get("in") == "query":
            desc = p.get("description") or ""
            entry = {
                "key": p["name"],
                "value": "{{" + p["name"] + "}}",
                "description": desc,
                "disabled": not p.get("required", False),
            }
            query_entries.append(entry)
            if p.get("required"):
                required_query_pairs.append(f"{p['name']}={{{{{p['name']}}}}}")

    # Build raw_url directly from the original path (preserves trailing slash,
    # which is significant here since redirect_slashes=False on the app).
    raw_url = "{{baseUrl}}" + "/" + "/".join(segments)
    if path.endswith("/") and not raw_url.endswith("/"):
        raw_url += "/"
    if query_entries:
        raw_url += "?" + "&".join(required_query_pairs)

    url_obj = {
        "raw": raw_url,
        "host": ["{{baseUrl}}"],
        "path": segments,
    }
    if query_entries:
        url_obj["query"] = query_entries

    request = {
        "method": method,
        "header": headers,
        "url": url_obj,
    }

    body_name, body_ct = request_body_cell(operation, components)
    if body_name is not None:
        rb = operation["requestBody"]
        schema_obj = rb["content"][body_ct]["schema"]
        example = example_for_schema(schema_obj, components)
        if not isinstance(example, dict):
            example = {} if example is None else example
        body_json = json.dumps(example, indent=2)
        request["header"] = [{"key": "Content-Type", "value": body_ct, "type": "text"}] + headers
        request["body"] = {
            "mode": "raw",
            "raw": body_json,
            "options": {"raw": {"language": "json"}},
        }

    if op["auth_level"] == "none":
        request["auth"] = {"type": "noauth"}

    item = {
        "name": f"{method} {path}",
        "request": request,
        "response": [],
    }
    return item


def render_postman_collection(ops, existing):
    components_ref = None  # filled by caller

    groups = {}
    for op in ops:
        groups.setdefault(op["tag"], []).append(op)
    for tag in groups:
        groups[tag].sort(key=lambda o: (o["path"], o["method"]))
    sorted_tags = sorted(groups.keys(), key=lambda t: t.lower())

    collection = {
        "info": copy.deepcopy(existing["info"]),
        "variable": copy.deepcopy(existing["variable"]),
        "auth": copy.deepcopy(existing["auth"]),
        "item": [],
    }
    return collection, groups, sorted_tags


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
def extract_md_operations(md_text):
    import re
    ops = set()
    row_re = re.compile(r"^\|\s*`(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|TRACE)`\s*\|\s*`([^`]+)`\s*\|")
    for line in md_text.splitlines():
        m = row_re.match(line.strip())
        if m:
            ops.add((m.group(1), m.group(2)))
    return ops


def extract_postman_operations(collection):
    """Parse (METHOD, path) back out of each leaf item's `name` field, which is
    always written as f"{method} {path}" by build_postman_item - this avoids
    lossy reconstruction from url.path segments (which drop trailing slashes)."""
    ops = []

    def walk(items):
        for it in items:
            if "item" in it:
                walk(it["item"])
            else:
                name = it["name"]
                method, path = name.split(" ", 1)
                ops.append((method, path, name))

    walk(collection["item"])
    return ops


def main():
    schema = app.openapi()
    total_paths = len(schema.get("paths", {}))
    total_ops = sum(
        1 for methods in schema["paths"].values()
        for m in methods if m in HTTP_METHODS
    )
    print(f"Live schema: {total_ops} operations across {total_paths} paths.")

    auth_map = build_auth_map()
    ops = build_operations(schema, auth_map)
    components = schema.get("components", {}).get("schemas", {})

    # --- api.md ---
    md_text = render_api_md(ops, total_ops, total_paths)
    (REPO_ROOT / "api.md").write_text(md_text, encoding="utf-8")
    print("Wrote api.md")

    # --- postman_collection.json ---
    existing = json.loads((REPO_ROOT / "postman_collection.json").read_text(encoding="utf-8"))
    collection, groups, sorted_tags = render_postman_collection(ops, existing)
    for tag in sorted_tags:
        folder = {"name": tag, "item": []}
        for op in groups[tag]:
            folder["item"].append(build_postman_item(op, components))
        collection["item"].append(folder)

    (REPO_ROOT / "postman_collection.json").write_text(
        json.dumps(collection, indent=2) + "\n", encoding="utf-8")
    print("Wrote postman_collection.json")

    # --- self-check ---
    schema_keys = set()
    for path, methods in schema["paths"].items():
        for m in methods:
            if m in HTTP_METHODS:
                schema_keys.add((m.upper(), path))

    md_keys = extract_md_operations(md_text)
    missing_md = schema_keys - md_keys
    extra_md = md_keys - schema_keys
    if missing_md or extra_md:
        print("MISMATCH in api.md: missing=%s extra=%s" % (missing_md, extra_md))
    else:
        print(f"api.md OK: {len(md_keys)} operations, matches schema exactly.")

    pm_ops = extract_postman_operations(collection)
    pm_keys = [(m, p) for m, p, _ in pm_ops]
    from collections import Counter
    pm_counter = Counter(pm_keys)
    dupes = {k: v for k, v in pm_counter.items() if v > 1}
    pm_key_set = set(pm_keys)
    missing_pm = schema_keys - pm_key_set
    extra_pm = pm_key_set - schema_keys
    if missing_pm or extra_pm or dupes:
        print("MISMATCH in postman_collection.json: missing=%s extra=%s dupes=%s" % (
            missing_pm, extra_pm, dupes))
    else:
        print(f"postman_collection.json OK: {len(pm_key_set)} unique operations, matches schema exactly.")

    return 0 if not (missing_md or extra_md or missing_pm or extra_pm or dupes) else 1


if __name__ == "__main__":
    sys.exit(main())
