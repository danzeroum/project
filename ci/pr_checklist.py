#!/usr/bin/env python3
"""Checklist de compliance do PR, DERIVADO de harness/stages.yaml.

ERGONOMIA DECLARADA, NÃO TRAVA. Ele não reprova nada e não entra em validate_all.py — um
checklist que reprovasse viraria o nono fiscal, sem política e sem teste de mordida. Quem reprova
continua sendo a validação total.

O valor está em derivar: para os caminhos que o PR toca, ele diz quais etapas foram acionadas,
quais fiscais vão rodar, e qual pergunta de privacidade aquela etapa faz. Nada disso está escrito
aqui — vem de stages.yaml, pela mesma razão de sempre: uma segunda descrição do repositório
deriva da primeira em silêncio.

Uso:  python ci/pr_checklist.py <caminho>…        (ou sem argumentos: lê o diff de origin/main)
Saída: sempre 0.
"""

from __future__ import annotations

import subprocess
import sys

import harness_lib as hl
from harness_lib import HarnessError


def _tocados(argv: list[str]) -> list[str]:
    if argv:
        return argv
    try:
        r = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"],
                           cwd=hl.REPO, capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return []
    return [l for l in r.stdout.splitlines() if l.strip()]


def main(argv: list[str] | None = None) -> int:
    import orient

    caminhos = _tocados(list(argv or []))
    if not caminhos:
        print("• nenhum caminho modificado detectado — nada a checar.")
        return 0

    try:
        itens = orient.tocar(caminhos)
    except HarnessError as exc:
        print(f"• não deu para montar o checklist: {exc}")
        return 0

    etapas: dict[str, dict] = {}
    protegidos: set[str] = set()
    for item in itens:
        if item.get("protegido_por"):
            protegidos.add(item["caminho"])
        for etapa in item["etapas"]:
            etapas.setdefault(etapa["id"], etapa)

    print("## Checklist de compliance (derivado de harness/stages.yaml)\n")
    if protegidos:
        print("- [ ] **Caminho protegido tocado** — a mudança está declarada em uma "
              "change-proposal? (ADR-004)")
        for p in sorted(protegidos):
            print(f"      - `{p}`")
    for sid, etapa in sorted(etapas.items()):
        print(f"- [ ] **{sid}** — {etapa['nome']}")
        for fiscal in etapa["fiscais"]:
            print(f"      - fiscal que vai rodar: `{fiscal}`")
        if etapa.get("pergunta_de_privacidade"):
            print(f"      - lente de privacidade: {etapa['pergunta_de_privacidade']}")
    print("\n- [ ] `python ci/validate_all.py` sai 0")
    print("- [ ] toda trava nova nasceu com o par de testes de mordida")
    print("\n> Este checklist é ergonomia, não gate. O gate é `ci/validate_all.py`.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
