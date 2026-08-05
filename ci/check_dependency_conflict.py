#!/usr/bin/env python3
"""Complemento §10 — o mesmo pacote declarado com versões que se contradizem.

Três arquivos declaram dependência neste repositório, e cada um responde a uma pergunta
diferente: `pyproject.toml` o que o pacote de negócio precisa; `requirements-qa.txt` qual é a
RÉGUA; `requirements-ci.txt` o fecho resolvido do ambiente dos fiscais.

Três fontes com a mesma resposta são redundância barata. Três fontes com respostas DIFERENTES são
uma pergunta sem resposta — e o que se instala passa a depender de qual arquivo o comando leu.
O modo de falha é característico: o CI instala uma coisa, o local instala outra, e a divergência
aparece como um teste que "às vezes falha".

Normalizado para audit-report.schema.json como todo fiscal desta casa: o laudo é comparável, e
quem lê não precisa aprender um formato novo por ferramenta.

Uso:  python ci/check_dependency_conflict.py [--quiet] [--json] [--report PATH]
Saída: 0 sem conflito · 1 conflito · 2 não foi possível fiscalizar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

import harness_lib as hl
from harness_lib import Errors, Findings, HarnessError

AUDITOR_VERSION = "1.0"
REPORT_PATH = "harness/reports/dependency-conflict.json"

FONTES = ["pyproject.toml", "requirements-qa.txt", "requirements-ci.txt"]

# `pacote==1.2.3`, `"pacote>=4"`, `pacote ~= 2.0` — a forma que interessa é nome + operador + versão.
_REQ = re.compile(r'^[\s"\']*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(==|>=|<=|~=|!=|<|>)\s*([0-9][^\s"\',\\]*)')


def declaracoes() -> dict[str, list[tuple[str, str, str]]]:
    """pacote -> [(arquivo, operador, versão)]. Lê o DECLARADO, nunca o instalado.

    Conferir contra o site-packages local faria o fiscal passar ou reprovar conforme a máquina de
    quem roda — o oposto de fiscalizável.
    """
    achadas: dict[str, list[tuple[str, str, str]]] = {}
    for fonte in FONTES:
        if not hl.rel_exists(fonte):
            continue
        for linha in hl.read_text(fonte).splitlines():
            if linha.lstrip().startswith("#"):
                continue
            m = _REQ.match(linha)
            if m:
                nome = m.group(1).lower().replace("_", "-")
                achadas.setdefault(nome, []).append((fonte, m.group(2), m.group(3)))
    return achadas


def conflitos(decl: dict[str, list[tuple[str, str, str]]]) -> list[dict]:
    """Função pura. Um pacote conflita quando duas fontes fixam versões EXATAS diferentes.

    Só `==` contra `==` conta como conflito. Um `>=8` no pyproject e um `==9.1.1` no lock não se
    contradizem — o segundo é uma resolução válida do primeiro, e acusar isso seria o fiscal
    reprovando o funcionamento normal de um lockfile.
    """
    out = []
    for pacote, ocorrencias in sorted(decl.items()):
        exatas = {(f, v) for f, op, v in ocorrencias if op == "=="}
        versoes = {v for _, v in exatas}
        if len(versoes) > 1:
            out.append({
                "pacote": pacote,
                "declaracoes": sorted(f"{f}: =={v}" for f, v in exatas),
            })
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conflito de versão entre declarações.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", default=REPORT_PATH)
    args = parser.parse_args(argv)

    findings, errors = Findings(), Errors()
    try:
        decl = declaracoes()
    except HarnessError as exc:
        print(f"✗ dependências: {exc}", file=sys.stderr)
        return 2

    for c in conflitos(decl):
        findings.add(
            key=f"DEP-CONFLICT-{c['pacote']}", origin="dependency_conflict", severity="high",
            risk="RISK-DEP-001", location=", ".join(c["declaracoes"]),
            summary=f"'{c['pacote']}' está fixado com versões diferentes em mais de uma fonte "
                    f"({'; '.join(c['declaracoes'])}) — o que se instala passa a depender de qual "
                    f"arquivo o comando leu.",
            remediation="Igualar as versões, ou deixar UMA fonte fixar e as outras referenciarem "
                        "— a mesma regra da versão da régua (ADR-003).",
        )

    report = hl.build_report(
        auditor="ci/check_dependency_conflict.py", auditor_version=AUDITOR_VERSION,
        findings=findings, stages_covered=["STAGE-SECURITY"],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    try:
        hl.emit_report(args.report, report)
    except HarnessError as exc:
        print(f"✗ dependências: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        hl.print_summary("conflito de dependências", findings, errors, quiet=args.quiet)
    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
