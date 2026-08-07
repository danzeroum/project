"""Mordidas do fiscal de fonte única da cadência (CP-047).

O que este fiscal previne, medido e não suposto: `25h` chegou a aparecer em doze arquivos. Quando
a CP-046 afrouxou a cadência, onze passaram a descrever errado o comportamento vivo — sem nenhum
vermelho, porque prosa não morde. O décimo segundo, um teste, fez pior: recusou o atestado legítimo
e travou o repositório num impasse circular.

Mas o cuidado central deste arquivo é o OUTRO lado. Um fiscal que proíbe a MENÇÃO em vez do FATO
obriga a apagar a explicação no lugar exato onde o próximo leitor procura o porquê — a família
âncora-na-menção que `harness/policies/conformance.md` registra com nove ocorrências, a última
nascida dentro do fiscal escrito para vigiar as anteriores.

Este fiscal quase foi a décima, duas vezes: a primeira versão acusou o comentário do repositório
sobre retenção de evidência (`os artifacts expiram em 90 dias`, que é outro assunto) e o próprio
comentário que descreve esta regra. Metade dos testes abaixo existe para provar que ele não
reincide.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

from conftest import REPO

CI = REPO / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))


@pytest.fixture(autouse=True)
def _restaura_repo():
    yield
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


def _achados(repo_copy: Path, run_auditor) -> list[dict]:
    code, findings = run_auditor("audit_governance", repo_copy)
    return [f for f in findings if f["origin"] == "cadence_single_source"]


# --------------------------------------------------------------------------------------
# O FATO: afirmar a duração num arquivo que descreve o agora
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("alvo,linha", [
    ("ci/automerge_gate.py", "# O atestado vale 25h e por isso o portão existe.\n"),
    ("harness/policies/trava-externa.md", "\nO atestado vale 25h.\n"),
    ("harness/harness.yaml", "\n# O carimbo tem validade de 30 horas.\n"),
    (".github/workflows/governance.yml", "\n# O atestado expira em 12 dias.\n"),
])
def test_afirmar_a_duracao_em_arquivo_VIVO_acusa(repo_copy, run_auditor, alvo, linha):
    """Código, política, configuração e workflow descrevem o AGORA — número aqui é afirmação.

    Os quatro tipos de arquivo entram na mesma parametrização de propósito: a regra é sobre a
    NATUREZA do arquivo, não sobre a linguagem dele, e testar só `.py` deixaria a política e o
    workflow — que é onde a prosa envelhece mais rápido — sem cobertura.
    """
    caminho = repo_copy / alvo
    caminho.write_text(caminho.read_text(encoding="utf-8") + linha, encoding="utf-8")

    achados = _achados(repo_copy, run_auditor)
    assert achados, f"{alvo}: afirmação de duração passou sem achado"
    assert any(alvo in f["location"] for f in achados), [f["location"] for f in achados]


def test_a_arvore_limpa_NAO_acusa(repo_copy, run_auditor):
    """O estado depois da CP-047: nenhum arquivo vivo afirma a duração.

    Sem este teste, um fiscal quebrado que nunca acusa nada passaria como 'tudo conforme' — e a
    versão anterior deste repositório passou dias exatamente assim.
    """
    assert not _achados(repo_copy, run_auditor)


# --------------------------------------------------------------------------------------
# A MENÇÃO: o que o fiscal NÃO pode acusar — e por que cada caso existe
# --------------------------------------------------------------------------------------

def test_registro_HISTORICO_nao_acusa(repo_copy, run_auditor):
    """ADR e proposta descrevem o dia em que foram escritos, e isso continua verdadeiro.

    "Decidi 25h então" é um fato; "faço 25h agora" é a mentira. Apagar o primeiro para evitar o
    segundo falsificaria o registro que permite entender por que as coisas ficaram como estão.
    """
    adr = repo_copy / "architecture/adr/ADR-028-a-autoridade-externa-ligada.md"
    adr.write_text(adr.read_text(encoding="utf-8")
                   + "\nNa época desta decisão o atestado valia 25h.\n", encoding="utf-8")
    cp = repo_copy / "harness/change-proposals/CP-036-ligar-a-autoridade-externa.yaml"
    cp.write_text(cp.read_text(encoding="utf-8")
                  + "\n# Naquele dia o atestado valia 25h.\n", encoding="utf-8")

    assert not _achados(repo_copy, run_auditor)


def test_prazo_de_OUTRO_assunto_nao_acusa(repo_copy, run_auditor):
    """O falso positivo que a primeira versão produziu, virado teste.

    `os artifacts expiram em 90 dias` é retenção de evidência — decisão da CP-026, assunto
    diferente. Ancorar no verbo de duração sem ancorar no SUJEITO dele acusa qualquer prazo do
    repositório, e um fiscal que acusa tudo é indistinguível de um que não acusa nada.
    """
    alvo = repo_copy / "ci/automerge_gate.py"
    alvo.write_text(alvo.read_text(encoding="utf-8")
                    + "\n# Os artifacts expiram em 90 dias; o token vale 8 horas.\n",
                    encoding="utf-8")

    assert not _achados(repo_copy, run_auditor)


def test_explicar_a_regra_entre_crases_nao_acusa(repo_copy, run_auditor):
    """O segundo falso positivo, e o mais instrutivo: o fiscal acusou o comentário que o descreve.

    Entre crases é CITAÇÃO. Um fiscal que não distingue citar de afirmar torna impossível explicar
    a própria regra — e foi assim que a nona ocorrência desta família nasceu dentro do fiscal
    escrito para vigiar as oito anteriores. Duas vezes seguidas é padrão, não azar.
    """
    alvo = repo_copy / "ci/automerge_gate.py"
    alvo.write_text(alvo.read_text(encoding="utf-8")
                    + "\n# Sobre o atestado: escrever `vale 25h` aqui seria restatar a cadência.\n",
                    encoding="utf-8")

    assert not _achados(repo_copy, run_auditor)


def test_o_proprio_fiscal_nao_se_acusa(repo_copy, run_auditor):
    """A trava sobre a reincidência, dita como teste.

    `ci/audit_governance.py` é arquivo VIVO e contém a explicação da regra. Se o fiscal se
    acusasse, a única correção disponível seria apagar a explicação — que é exatamente o preço que
    esta família de defeito cobra, e a razão de ela ter reincidido nove vezes.
    """
    achados = _achados(repo_copy, run_auditor)
    assert not any("audit_governance" in f["location"] for f in achados), achados
