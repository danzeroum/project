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


class PoliticaAusente(Exception):
    """A política não declara o que este hook precisaria ler.

    Exceção e não valor de retorno, porque um valor de retorno seria interpretado — e a única
    interpretação barata de uma lista vazia é "nada a proibir", que é o oposto da verdade.
    """


def _politica() -> dict:
    import yaml
    doc = yaml.safe_load((REPO / "harness" / "harness.yaml").read_text(encoding="utf-8")) or {}
    if "env_hygiene" not in doc:
        raise PoliticaAusente(
            "harness/harness.yaml não declara o bloco `env_hygiene`. O schema o exige no topo — "
            "e um hook que lesse dicionário vazio aqui concluiria 'nada a proibir' sobre um "
            "documento que nunca disse isso.")
    return doc["env_hygiene"] or {}


def _exigida(politica: dict, chave: str) -> list[str]:
    """Chave que o schema marca `required`: ausência é INDETERMINAÇÃO, jamais vazio.

    O default embutido é tão proibido quanto a lista vazia, e por um motivo a mais: `or ["WEBQA_"]`
    — que era o que estava escrito aqui — não só deixava a chave sumir sem ruído como criava uma
    SEGUNDA fonte da denylist dentro do código, que deriva da primeira no dia em que alguém
    acrescenta um prefixo ao harness.yaml e não a este arquivo.
    """
    if chave not in politica:
        raise PoliticaAusente(
            f"harness/harness.yaml:env_hygiene não declara `{chave}`. O schema a exige "
            f"(required + minItems 1) — mas o schema fiscaliza o DOCUMENTO, e este hook lê o "
            f"documento sem passar por ele. Chave ausente é 'não consegui fiscalizar', jamais "
            f"'nada a proibir'.")
    return politica[chave] or []


def denied_prefixes(politica: dict) -> list[str]:
    """Os prefixos de harness.yaml MAIS os derivados das fichas de suite (CP-041).

    O hook deriva pela mesma razão que `ci/env_guard.py` deriva, e a simetria é obrigatória: se
    só o guard do CI soubesse dos prefixos das réguas, a sessão do agente — onde ele tem shell —
    ficaria justamente com o vão que a trava existe para fechar. Duas denylists diferentes é a
    segunda cópia com outro nome.

    FAIL-CLOSED como as demais leituras deste arquivo: registro ausente ou ficha ilegível levanta
    `PoliticaAusente`, que o chamador traduz em exit 2. Devolver o que conseguiu ler faria o hook
    liberar `WEBQA_*` em silêncio no dia em que um YAML quebrasse.
    """
    declarados = list(_exigida(politica, "env_denylist_prefix"))

    suites = REPO / "harness" / "suites"
    if not suites.is_dir():
        raise PoliticaAusente(
            "harness/suites/ não existe, e é de lá que os prefixos das réguas derivam desde o "
            "CP-041. Registro ausente é 'não consegui fiscalizar', jamais 'nada a proibir'.")

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
                f"{caminho.name} não declara `suite.env_prefix`, que o schema exige.")
        derivados.append(prefixo)

    return sorted(set(declarados) | set(derivados))


def denied_exact(politica: dict) -> list[str]:
    """CP-025 — a família que não autoriza nada e por isso é pior: ela redireciona.

    O hook cobre o agente pelo mesmo motivo que cobria WEBQA_*: a trava que só existe no CI não
    protege a sessão, e é na sessão que o agente tem shell. Um `PYTHONPATH=/tmp/meu python
    ci/validate_all.py` digitado numa sessão produziria um verde que ninguém saberia questionar.

    TRÊS ESTADOS, e não dois — corrigido pela CP-040. Isto era `.get(...) or []`, e aquele idioma
    transforma "não declarado" em "declarado vazio". Num fiscal, essa é a distância entre
    INDETERMINAÇÃO e PERMISSÃO: sem a chave no harness.yaml o hook rodava, lia lista vazia e
    deixava passar — fail-open silencioso, no fiscal cuja razão de existir é fechar um vão.

    Medido no primeiro derivado real: a chave faltava lá desde o transplante da carcaça, a trava
    estava aberta, e a evidência de que ela funcionava vinha de OUTRO repositório — o hook resolve
    a raiz subindo do diretório corrente, e nas sessões em que ele recusou um `PYTHONPATH` a raiz
    resolvida era a do molde.

    Levanta em vez de devolver lista: quem chama decide a reação, e a reação certa para "não
    consegui fiscalizar" é exit 2, nunca exit 0.
    """
    return _exigida(politica, "env_denylist_exact")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # sem payload não há o que inspecionar; não é motivo para bloquear

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        return 0

    # A POLÍTICA INTEIRA É LIDA ANTES DE QUALQUER VEREDITO, e a ordem é a decisão (CP-040).
    # Ler chave por chave, mordendo pelo caminho, produziria um `DENIED_ENV` sobre uma política
    # incompleta — e `DENIED_ENV` afirma "olhei o que havia para olhar e foi isto que achei".
    # Com metade da política ausente essa frase é falsa mesmo quando o bloqueio está certo.
    try:
        politica = _politica()
        prefixos, exatos = denied_prefixes(politica), denied_exact(politica)
    except PoliticaAusente as exc:
        # Exit 2 é o mesmo código da recusa, e é deliberado: para quem digitou o comando, "a
        # política sumiu" e "a política proíbe isto" pedem a mesma coisa — parar e olhar. O que
        # não pode acontecer é o comando seguir porque o fiscal não sabia o que perguntar.
        print(f"FISCAL_CEGO: {exc}", file=sys.stderr)
        return 2

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

    for prefix in prefixos:
        p = re.escape(prefix)
        # Cobre `export WEBQA_X=1`, `WEBQA_X=1 cmd`, `env WEBQA_X=1` e `set WEBQA_X`.
        if re.search(rf"(?:^|[;&|]|\bexport\s+|\benv\s+|\bset\s+)\s*{p}[A-Z0-9_]*\s*=", command) \
           or re.search(rf"\bexport\s+{p}[A-Z0-9_]*\b", command):
            return recusar(
                f"{prefix}*",
                "Os gates da suíte são fail-closed por variável de ambiente: um agente que "
                "consegue defini-las se autoriza a sondar. Modos pesados são human_only, em job "
                "segregado do CI.")

    for nome in exatos:
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
