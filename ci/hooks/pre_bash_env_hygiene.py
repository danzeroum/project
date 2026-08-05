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


def _politica() -> dict:
    import yaml
    doc = yaml.safe_load((REPO / "harness" / "harness.yaml").read_text(encoding="utf-8")) or {}
    return (doc.get("env_hygiene") or {})


def denied_prefixes() -> list[str]:
    return _politica().get("env_denylist_prefix") or ["WEBQA_"]


def denied_exact() -> list[str]:
    """CP-025 — a família que não autoriza nada e por isso é pior: ela redireciona.

    O hook cobre o agente pelo mesmo motivo que cobria WEBQA_*: a trava que só existe no CI não
    protege a sessão, e é na sessão que o agente tem shell. Um `PYTHONPATH=/tmp/meu python
    ci/validate_all.py` digitado numa sessão produziria um verde que ninguém saberia questionar.
    """
    return _politica().get("env_denylist_exact") or []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # sem payload não há o que inspecionar; não é motivo para bloquear

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        return 0

    def recusar(alvo: str, porque: str) -> int:
        print(
            f"DENIED_ENV: o comando define '{alvo}', que a denylist de harness/harness.yaml "
            f"proíbe no runner de um agente.\n{porque}\n"
            f"Exceção legítima se declara em harness.yaml:env_hygiene.exceptions, com contexto e "
            f"justificativa — nunca removendo a entrada da lista.\n"
            f"Ver harness/policies/env-hygiene.md.",
            file=sys.stderr,
        )
        return 2

    for prefix in denied_prefixes():
        p = re.escape(prefix)
        # Cobre `export WEBQA_X=1`, `WEBQA_X=1 cmd`, `env WEBQA_X=1` e `set WEBQA_X`.
        if re.search(rf"(?:^|[;&|]|\bexport\s+|\benv\s+|\bset\s+)\s*{p}[A-Z0-9_]*\s*=", command) \
           or re.search(rf"\bexport\s+{p}[A-Z0-9_]*\b", command):
            return recusar(
                f"{prefix}*",
                "Os gates da suíte são fail-closed por variável de ambiente: um agente que "
                "consegue defini-las se autoriza a sondar. Modos pesados são human_only, em job "
                "segregado do CI.")

    for nome in denied_exact():
        n = re.escape(nome)
        if re.search(rf"(?:^|[;&|]|\bexport\s+|\benv\s+|\bset\s+)\s*{n}\s*=", command) \
           or re.search(rf"\bexport\s+{n}\b", command):
            return recusar(
                nome,
                "Esta variável não autoriza nada — ela redireciona. Proxy, índice de pacote e "
                "caminho de import trocam o que o processo LÊ: de onde vem o pacote, de onde vem "
                "o módulo, para onde vai a requisição. Um fiscal enganado reporta verde com "
                "convicção, e verde com convicção encerra a investigação.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
