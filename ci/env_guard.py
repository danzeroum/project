#!/usr/bin/env python3
"""Higiene de ambiente — a denylist de harness.yaml aplicada ao ambiente REAL do processo.

A lista mora em `harness/harness.yaml` e é LIDA daqui. O workflow não a repete, e essa é a decisão
que mais importa neste arquivo: uma segunda cópia derivaria em silêncio, e a primeira coisa a
divergir seria exatamente a entrada que alguém removeu. Derivar em vez de duplicar é o que faz uma
variável nova nascer coberta — a lição do CP-020 atravessando o plano inteiro.

Duas famílias, com ameaças diferentes:

  - PREFIXO (`WEBQA_*`): auto-autorização. Os gates da suíte são fail-closed por variável de
    ambiente, e um agente que consegue defini-las se autoriza a sondar.
  - NOME EXATO (proxies, índices de pacote, PYTHONPATH…): sequestro. Nenhuma delas ataca o fiscal;
    elas trocam o que o fiscal LÊ — de onde vem o pacote, de onde vem o módulo, para onde vai a
    requisição. Fiscal enganado reporta verde com convicção, e verde com convicção encerra a
    investigação.

ONDE ELE VALE. O guard inspeciona o ambiente HERDADO, e por isso é invocado pelos jobs de CI, onde
a linha de base é limpa. Numa máquina de desenvolvimento atrás de proxy corporativo ele vai acusar
— e a resposta certa não é remover a entrada da lista, é declarar a exceção com o contexto daquele
ambiente em `harness.yaml:env_hygiene.exceptions`. Ele deliberadamente NÃO entra em
`validate_all.py`: a validação total precisa rodar igual em qualquer máquina, e um fiscal que
depende do ambiente de quem o roda não tem lugar ali.

Uso:  python ci/env_guard.py [--context NOME] [--quiet]
Saída: 0 ambiente limpo · 10 DENIED_ENV (mesmo código do guard da suíte) · 2 não pôde verificar.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("HARNESS_REPO_ROOT") or Path(__file__).resolve().parent.parent).resolve()

DENIED_ENV = 10


def politica() -> dict:
    import yaml

    doc = yaml.safe_load((REPO / "harness" / "harness.yaml").read_text(encoding="utf-8")) or {}
    return doc.get("env_hygiene") or {}


def violacoes(ambiente: dict[str, str], pol: dict, contexto: str | None = None) -> list[str]:
    """Função pura: entra ambiente e política, sai lista de violações.

    O `contexto` é o que torna a exceção honesta. Uma exceção sem contexto valeria em toda parte —
    e uma exceção que vale em toda parte é a entrada removida da lista com outro nome. Quem invoca
    o guard precisa DIZER em que contexto está, e só as exceções declaradas para aquele contexto
    são dispensadas.
    """
    isentas = {e["name"] for e in (pol.get("exceptions") or [])
               if contexto and e.get("context") == contexto}

    achados: list[str] = []
    for prefixo in pol.get("env_denylist_prefix") or []:
        for nome in sorted(ambiente):
            if nome.startswith(prefixo) and nome not in isentas:
                achados.append(f"{nome} (prefixo proibido '{prefixo}*': auto-autorização — os "
                               f"gates da suíte são fail-closed por variável de ambiente)")
    for nome in pol.get("env_denylist_exact") or []:
        if nome in ambiente and nome not in isentas:
            achados.append(f"{nome} (nome proibido: sequestro de rede, de índice de pacote ou de "
                           f"import — troca o que o fiscal lê, sem tocar no fiscal)")
    return achados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Higiene de ambiente (denylist de harness.yaml).")
    parser.add_argument("--context", help="contexto declarado, para as exceções de harness.yaml")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        pol = politica()
    except Exception as exc:  # noqa: BLE001 - política ilegível é 'não consegui fiscalizar'
        print(f"✗ higiene de ambiente: política ilegível ({exc})", file=sys.stderr)
        return 2

    achados = violacoes(dict(os.environ), pol, args.context)
    if not achados:
        if not args.quiet:
            n = len(pol.get("env_denylist_exact") or []) + len(pol.get("env_denylist_prefix") or [])
            print(f"✓ higiene de ambiente: {n} regra(s) da denylist, nenhuma violada.")
        return 0

    # fail_on_denied_env: abortar, nunca filtrar em silêncio. Ignorar esconde exatamente o erro de
    # configuração que o controle existe para revelar.
    if not pol.get("fail_on_denied_env"):
        print("::warning::variáveis negadas presentes e fail_on_denied_env está desligado.",
              file=sys.stderr)
        return 0

    print(f"✗ DENIED_ENV: {len(achados)} variável(is) negada(s) no ambiente:", file=sys.stderr)
    for a in achados:
        print(f"  - {a}", file=sys.stderr)
    print("Ver harness/policies/env-hygiene.md. Exceção legítima se declara em "
          "harness.yaml:env_hygiene.exceptions, com contexto e justificativa — nunca removendo a "
          "entrada da lista.", file=sys.stderr)
    return DENIED_ENV


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
