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


class PoliticaAusente(Exception):
    """A política não declara o que este fiscal precisaria ler.

    Irmã da do hook, e pela mesma razão — a mordida de classe da CP-040 encontrou este arquivo
    junto com aquele. Aqui o efeito era ainda mais visível: sem as chaves, `main` imprimia
    "✓ higiene de ambiente: 0 regra(s) da denylist, nenhuma violada" e saía 0. Um tique verde
    afirmando, com todas as letras, que zero regras não foram violadas.
    """


def _exigida(politica: dict, chave: str) -> list[str]:
    """Chave que o schema marca `required`: ausência é INDETERMINAÇÃO, jamais vazio."""
    if chave not in politica:
        raise PoliticaAusente(
            f"harness/harness.yaml:env_hygiene não declara `{chave}`, que o schema exige. "
            f"Chave ausente é 'não consegui fiscalizar', jamais 'nada a proibir'.")
    return politica[chave] or []


def _exigida_flag(politica: dict, chave: str) -> bool:
    """A mesma regra para o campo booleano, e ele precisa dela tanto quanto as listas.

    `pol.get("fail_on_denied_env")` sem a chave devolve None, que é falso, que é exatamente o valor
    que DESLIGA o aborto. O idioma nem sequer é `or []` — é a mesma ausência apagada, com outra
    cara, e por isso o teste de classe não a pegaria: fica escrito aqui para o próximo leitor não
    concluir que o regex é a fronteira do problema.
    """
    if chave not in politica:
        raise PoliticaAusente(
            f"harness/harness.yaml:env_hygiene não declara `{chave}`, que o schema exige. "
            f"Ausente, ele leria como 'desligado' — o valor que dispensa o aborto.")
    return bool(politica[chave])


def _opcional(politica: dict, chave: str) -> list:
    """Chave que o schema NÃO marca `required`: ausência e vazio significam a mesma coisa.

    O nome existe para que a diferença seja declarada onde ela é decidida. `exceptions` é opcional
    no schema — um repositório sem exceção alguma é um estado legítimo e completo, e tratá-lo como
    indeterminação obrigaria a escrever `exceptions: []` para dizer o que o silêncio já diz.
    """
    return politica.get(chave) or []


def politica() -> dict:
    import yaml

    doc = yaml.safe_load((REPO / "harness" / "harness.yaml").read_text(encoding="utf-8")) or {}
    if "env_hygiene" not in doc:
        raise PoliticaAusente(
            "harness/harness.yaml não declara o bloco `env_hygiene`, que o schema exige no topo.")
    return doc["env_hygiene"] or {}


def prefixos_efetivos(pol: dict) -> list[str]:
    """Os prefixos de `harness.yaml` MAIS os declarados por cada ficha de suite (CP-041).

    DERIVAR EM VEZ DE DUPLICAR, mais uma vez. `WEBQA_` morava aqui como literal; agora nasce da
    ficha `harness/suites/qa-suite.yaml`, e `PRIVSUITE_` nasce da ficha da privacy-suite ANTES de
    a régua existir. É a lição do CP-020 aplicada à classe: a variável de uma régua nova nasce
    coberta, sem que ninguém precise lembrar de uma segunda lista.

    E É FAIL-CLOSED, que é a metade que importa. Registro ausente ou ilegível levanta
    `PoliticaAusente` — jamais devolve o que conseguiu ler. A alternativa seria devolver a lista
    curta e seguir: o guard imprimiria "nenhuma violada" com convicção, e a família inteira de
    uma régua teria saído da denylist porque um YAML ficou ilegível. Trava que se desliga sozinha
    quando o registro some não é trava.
    """
    declarados = list(_exigida(pol, "env_denylist_prefix"))

    suites = REPO / "harness" / "suites"
    if not suites.is_dir():
        raise PoliticaAusente(
            "harness/suites/ não existe, e é de lá que os prefixos das réguas derivam desde o "
            "CP-041. Registro ausente é 'não consegui fiscalizar', jamais 'nada a proibir' — a "
            "segunda leitura tira WEBQA_* e PRIVSUITE_* da denylist sem que nada acuse.")

    import yaml

    derivados: list[str] = []
    for caminho in sorted(suites.glob("*.yaml")):
        try:
            doc = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - YAML ilegível é indeterminação, não silêncio
            raise PoliticaAusente(f"ficha de suite ilegível ({caminho.name}): {exc}") from exc
        prefixo = (doc.get("suite") or {}).get("env_prefix")
        if not prefixo:
            raise PoliticaAusente(
                f"{caminho.name} não declara `suite.env_prefix`, que o schema exige. Ficha sem "
                f"prefixo é régua cujos gates fail-closed ficam alcançáveis pelo ambiente.")
        derivados.append(prefixo)

    return sorted(set(declarados) | set(derivados))


def violacoes(ambiente: dict[str, str], pol: dict, contexto: str | None = None) -> list[str]:
    """Função pura: entra ambiente e política, sai lista de violações.

    O `contexto` é o que torna a exceção honesta. Uma exceção sem contexto valeria em toda parte —
    e uma exceção que vale em toda parte é a entrada removida da lista com outro nome. Quem invoca
    o guard precisa DIZER em que contexto está, e só as exceções declaradas para aquele contexto
    são dispensadas.
    """
    isentas = {e["name"] for e in _opcional(pol, "exceptions")
               if contexto and e.get("context") == contexto}

    achados: list[str] = []
    for prefixo in prefixos_efetivos(pol):
        for nome in sorted(ambiente):
            if nome.startswith(prefixo) and nome not in isentas:
                achados.append(f"{nome} (prefixo proibido '{prefixo}*': auto-autorização — os "
                               f"gates da suíte são fail-closed por variável de ambiente)")
    for nome in _exigida(pol, "env_denylist_exact"):
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
        achados = violacoes(dict(os.environ), pol, args.context)
        n = len(_exigida(pol, "env_denylist_exact")) + len(prefixos_efetivos(pol))
        abortar = _exigida_flag(pol, "fail_on_denied_env")
    except PoliticaAusente as exc:
        print(f"✗ FISCAL_CEGO: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - política ilegível é 'não consegui fiscalizar'
        print(f"✗ higiene de ambiente: política ilegível ({exc})", file=sys.stderr)
        return 2

    if not achados:
        if not args.quiet:
            print(f"✓ higiene de ambiente: {n} regra(s) da denylist, nenhuma violada.")
        return 0

    # fail_on_denied_env: abortar, nunca filtrar em silêncio. Ignorar esconde exatamente o erro de
    # configuração que o controle existe para revelar.
    if not abortar:
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
