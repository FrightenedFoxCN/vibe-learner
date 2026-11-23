"""Generate docs/api-reference.md from the FastAPI OpenAPI schema.

Run from anywhere:

    cd services/ai && uv run python ../../scripts/gen_api_reference.py
    npm run gen:api-reference

`--check` renders in memory and fails when the file on disk differs, which is how
CI keeps the reference from rotting.

The generated file is the endpoint inventory only. Contract semantics, versioning
and compatibility notes stay hand-written in ``docs/api-contracts.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AI_ROOT = REPO_ROOT / "services" / "ai"
OUTPUT = REPO_ROOT / "docs" / "api-reference.md"

METHODS = ("get", "post", "put", "patch", "delete")


def load_schema() -> dict:
    sys.path.insert(0, str(AI_ROOT))
    from app.app_factory import create_app  # noqa: PLC0415

    return create_app().openapi()


def schema_name(ref: str | None) -> str:
    if not ref:
        return ""
    return ref.rsplit("/", 1)[-1]


def operation_summary(op: dict) -> str:
    text = op.get("summary") or op.get("description") or ""
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first.replace("|", "\\|")[:160]


def render(schema: dict) -> str:
    paths: dict[str, dict] = schema.get("paths", {})
    groups: dict[str, list[tuple[str, str, dict]]] = {}
    for path, item in paths.items():
        for method in METHODS:
            if method in item:
                key = path.strip("/").split("/")[0] or "root"
                groups.setdefault(key, []).append((path, method, item[method]))

    total = sum(len(v) for v in groups.values())
    lines = [
        "# API Reference（生成文件）",
        "",
        "> 由 `scripts/gen_api_reference.py` 从 FastAPI OpenAPI 生成，**请勿手改**。",
        "> 契约语义、版本与兼容说明见 [api-contracts.md](api-contracts.md)；",
        "> 改动路由后运行 `npm run gen:api-reference` 重新生成。",
        "",
        f"共 {len(groups)} 个分组、{total} 个操作。",
        "",
    ]

    for group in sorted(groups):
        lines.append(f"## {group}")
        lines.append("")
        for path, method, op in sorted(groups[group], key=lambda row: (row[0], row[1])):
            lines.append(f"### `{method.upper()} {path}`")
            lines.append("")
            summary = operation_summary(op)
            if summary:
                lines.append(summary)
                lines.append("")
            params = op.get("parameters") or []
            if params:
                rendered = []
                for param in params:
                    location = param.get("in", "?")
                    required = "必填" if param.get("required") else "可选"
                    schema_type = (param.get("schema") or {}).get("type", "")
                    name = param.get("name", "?")
                    suffix = f": {schema_type}" if schema_type else ""
                    rendered.append(f"`{name}`（{location}，{required}{suffix}）")
                lines.append("参数：" + "、".join(rendered))
                lines.append("")
            body = (op.get("requestBody") or {}).get("content") or {}
            for media, spec in body.items():
                model = schema_name(spec.get("schema", {}).get("$ref"))
                if model:
                    lines.append(f"请求体（`{media}`）：`{model}`")
                    lines.append("")
                    break
            responses = op.get("responses") or {}
            rendered = []
            for code in sorted(responses):
                spec = (responses[code].get("content") or {}).get(
                    "application/json"
                ) or {}
                model = schema_name((spec.get("schema") or {}).get("$ref"))
                rendered.append(f"{code}" + (f" `{model}`" if model else ""))
            if rendered:
                lines.append("响应：" + "、".join(rendered))
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    content = render(load_schema())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print(
                "docs/api-reference.md is stale; run `npm run gen:api-reference`.",
                file=sys.stderr,
            )
            return 1
        print("docs/api-reference.md is up to date")
        return 0

    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
