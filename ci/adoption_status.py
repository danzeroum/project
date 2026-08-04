#!/usr/bin/env python3
"""Responde a pergunta do primeiro turno: este repositório é molde ou derivado, e o que falta.

Não é fiscal. Não reprova nada, não escreve nada, e sai 0 mesmo achando o repositório incompleto —
quem reprova é ci/validate_all.py. Este script existe para que quem clonou não precise adivinhar
o próximo passo, e é o que o hook SessionStart imprime.

Roda ANTES de as dependências dos fiscais existirem, e por isso trata a falta delas como estado
conhecido a reportar, não como falha: um clone fresco não tem pyyaml (ele vive no extra [dev] do
pyproject.toml), e um script de orientação que quebra justamente quando o repositório está mais
cru é inútil na única hora em que seria necessário.

Uso:  python ci/adoption_status.py [--quiet]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("HARNESS_REPO_ROOT") or Path(__file__).resolve().parent.parent).resolve()


def _sem_dependencias() -> int:
    print("• Dependências dos fiscais ausentes neste ambiente (pyyaml/jsonschema).")
    print("  Próximo passo:  /bootstrap   (ou: pip install -e \".[dev]\")")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estado de adoção do repositório.")
    parser.add_argument("--quiet", action="store_true", help="não imprime o cabeçalho")
    args = parser.parse_args(argv)

    try:
        import yaml
    except ImportError:
        return _sem_dependencias()

    def ler(rel: str) -> dict:
        path = REPO / rel
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return {}

    projeto = ler("project.yaml")
    lock = ler("target.lock")
    kind = (projeto.get("project") or {}).get("kind")

    if not args.quiet:
        print(f"• Papel declarado: {kind or '(ausente — project.yaml não migrou para kind)'}")

    if kind == "mold":
        print("• Molde: não governa alvo algum, e é isso que o torna reaproveitável.")
        print("  Próximo passo:  /adotar <url-do-alvo>")
        return 0

    if kind == "derived":
        alvo = projeto.get("target") or {}
        sha = lock.get("target_sha")
        print(f"• Derivado de {alvo.get('repo', '(alvo não declarado)')}"
              f" @ {alvo.get('ref', '?')} — SHA {(sha or '(não ancorado)')[:12]}")
        roots = alvo.get("code_roots") or []
        materializado = (REPO / "workspace" / "target").exists()
        print(f"• Workspace do alvo: {'materializado' if materializado else 'AUSENTE'}"
              f" · raízes de código declaradas: {', '.join(roots) or '(nenhuma)'}")
        print("  Próximo passo:  "
              + ("python ci/validate_all.py" if materializado else "/bootstrap"))
        return 0

    print("• Papel indefinido: project.yaml:project.kind precisa ser 'mold' ou 'derived'.")
    print("  Próximo passo:  ler BOOTSTRAP.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
