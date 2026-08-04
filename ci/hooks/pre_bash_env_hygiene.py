#!/usr/bin/env python3
"""Hook PreToolUse/Bash — aplica env_hygiene ao agente LOCAL.

harness/policies/env-hygiene.md admite em texto que "um agente com shell pode exportar qualquer
uma delas": a denylist WEBQA_* mordia no CI e não mordia na sessão. Este hook fecha esse vão.

Lê a denylist de harness/harness.yaml — a política continua declarada num lugar só. Recusa o
comando (exit 2) em vez de apenas ignorar a variável: erro vira evento auditável, que é a
diferença entre `fail_on_denied_env: true` e um filtro silencioso.

Não substitui o CI. É ergonomia e feedback rápido; o gate é .github/workflows/governance.yml.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def denied_prefixes() -> list[str]:
    import yaml
    doc = yaml.safe_load((REPO / "harness" / "harness.yaml").read_text(encoding="utf-8")) or {}
    return (doc.get("env_hygiene") or {}).get("env_denylist_prefix") or ["WEBQA_"]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # sem payload não há o que inspecionar; não é motivo para bloquear

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        return 0

    for prefix in denied_prefixes():
        p = re.escape(prefix)
        # Cobre `export WEBQA_X=1`, `WEBQA_X=1 cmd`, `env WEBQA_X=1` e `set WEBQA_X`.
        if re.search(rf"(?:^|[;&|]|\bexport\s+|\benv\s+|\bset\s+)\s*{p}[A-Z0-9_]*\s*=", command) \
           or re.search(rf"\bexport\s+{p}[A-Z0-9_]*\b", command):
            print(
                f"DENIED_ENV: o comando define uma variável '{prefix}*', que a denylist de "
                f"harness/harness.yaml proíbe no runner de um agente.\n"
                f"Os gates da suíte são fail-closed por variável de ambiente: um agente que "
                f"consegue defini-las se autoriza a sondar. Modos pesados são human_only, em job "
                f"segregado do CI.\nVer harness/policies/env-hygiene.md.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
