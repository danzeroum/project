#!/usr/bin/env python3
"""Hook PostToolUse/Edit|Write — recusa edição de artefato gerado ou de caminho protegido.

Lookup de caminho, sem parsing e sem I/O além de um YAML pequeno: barato o bastante para rodar
a cada edição. Duas classes de alvo:

  - artefato DERIVADO (docs/metadata-graph.md): editar à mão cria uma fonte paralela que o
    --check do CI vai contradizer. Regerar é a correção.
  - protected_path: mudança que exige revisão humana começa por uma change-proposal declarada
    (ADR-004), não por uma edição direta na sessão.

Recusa com exit 2 para que a mensagem volte ao agente. Não é o gate — CODEOWNERS mais branch
protection são; este hook só evita descobrir o problema no CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

GENERATED = {
    "docs/metadata-graph.md": "python ci/generate_graph.py",
    "docs/alignment.md": "python ci/alignment_report.py",
}

# A change-proposal é o REMÉDIO prescrito para tocar um caminho protegido (ADR-004). Bloqueá-la
# por estar sob harness/ fecharia o círculo: o hook mandaria declarar a proposta e impediria de
# escrevê-la. A proposta continua protegida onde importa — schema, check_change_proposals,
# CODEOWNERS e branch protection; só não é barrada nesta camada de ergonomia.
EXEMPT_PREFIXES = ("harness/change-proposals/",)


def protected_paths() -> list[str]:
    import yaml
    doc = yaml.safe_load((REPO / "harness" / "harness.yaml").read_text(encoding="utf-8")) or {}
    return (doc.get("repository") or {}).get("protected_paths") or []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw:
        return 0
    try:
        rel = Path(raw).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return 0  # fora do repositório: não é assunto desta harness

    if rel in GENERATED:
        print(
            f"'{rel}' é artefato DERIVADO, não fonte de verdade. Editá-lo à mão cria uma fonte "
            f"paralela que o --check do CI vai contradizer.\nRegerar com: {GENERATED[rel]}",
            file=sys.stderr,
        )
        return 2

    if rel.startswith(EXEMPT_PREFIXES):
        return 0

    for p in protected_paths():
        stem = p.rstrip("/")
        if rel == stem or rel.startswith(stem + "/"):
            print(
                f"'{rel}' está sob o protected_path '{p}' de harness/harness.yaml: muda só com "
                f"revisão humana.\nDeclare a mudança em harness/change-proposals/ antes de "
                f"executá-la (ADR-004). Risco high/critical exige aval humano por trava de schema.\n"
                f"Este hook é ergonomia; o fiscal real é CODEOWNERS + branch protection.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
