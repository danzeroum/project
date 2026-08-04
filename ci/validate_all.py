#!/usr/bin/env python3
"""Validação total do projeto — um comando, um significado de "validado".

Roda os quatro fiscais IN-PROCESS, nesta ordem (a ordem importa: sem metadado coerente, os
fiscais de comportamento reportariam ruído derivado do primeiro erro):

  1. ci/validate_metadata.py  — schema, IDs, I11, versão em fonte única
  2. ci/generate_graph.py     — artefato derivado em dia (--check)
  3. ci/audit_governance.py   — asserções de ADR + cobertura de etapas
  4. ci/audit_lgpd.py         — invariantes de LGPD + frescor do julgamento

Não faz curto-circuito: roda os quatro e agrega, para o PR mostrar tudo de uma vez — mesma
filosofia do acumulador err() do fiscal de metadados. In-process porque o hook Stop do agente
roda isto a cada turno: paga-se o startup do Python uma vez, e harness_lib memoiza os schemas.

Saída: 0 tudo conforme · 1 divergências · 2 algum fiscal não conseguiu fiscalizar.
Com --hook, 1 e 2 viram 2 (o código bloqueante do Claude Code).
"""

from __future__ import annotations

import argparse
import sys

import audit_governance
import audit_lgpd
import generate_graph
import validate_metadata

STEPS = [
    ("metadados", validate_metadata.main, []),
    ("grafo", generate_graph.main, ["--check"]),
    ("conformidade", audit_governance.main, []),
    ("lgpd", audit_lgpd.main, []),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validação total do projeto.")
    parser.add_argument("--quiet", action="store_true", help="só imprime em caso de falha")
    parser.add_argument("--summary", action="store_true",
                        help="não bloqueia: sempre sai 0 (para SessionStart)")
    parser.add_argument("--hook", action="store_true",
                        help="mapeia qualquer falha para exit 2 (bloqueante no Claude Code)")
    args = parser.parse_args(argv)

    codes: dict[str, int] = {}
    for name, fn, extra in STEPS:
        step_argv = list(extra)
        if args.quiet or args.summary:
            # generate_graph não conhece --quiet; os demais sim.
            if fn is not generate_graph.main:
                step_argv.append("--quiet")
        try:
            codes[name] = fn(step_argv)
        except SystemExit as exc:  # generate_graph usa sys.exit em alguns caminhos
            codes[name] = int(exc.code or 0)

    worst = 2 if 2 in codes.values() else (1 if 1 in codes.values() else 0)

    if worst == 0:
        if not args.quiet and not args.summary:
            print("\n✓ validação total: metadados, grafo, conformidade e LGPD conformes.")
    else:
        falhas = ", ".join(f"{n}({c})" for n, c in codes.items() if c)
        print(f"\n✗ validação total falhou em: {falhas}", file=sys.stderr)

    if args.summary:
        return 0
    if args.hook:
        return 2 if worst else 0
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
