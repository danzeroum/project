"""Mordidas do fiscal do aval humano (CP-048).

A trava que este arquivo protege é sobre uma distinção fina: existe diferença entre uma exigência
ESCRITA e uma exigência no CAMINHO QUE BLOQUEIA. O repositório tinha a primeira e não tinha a
segunda, e nada apontava para isso porque tudo estava verde.

O diagnóstico levou duas hipóteses erradas antes de fechar, e as duas eram plausíveis:

  "a exigência não existe"        — falsa: o schema torna inexpressável risco alto sem
                                    `human_approval_required`.
  "o fiscal não está no workflow" — falsa: verify_approval.py é passo bloqueante do governance.yml.

A causa real é mais estreita: `verify_approval.py` só verifica propostas `executed`, e `executed`
é uma transição MANUAL posterior ao merge. No instante do merge a proposta está `approved`, e
nesse estado ninguém a confere. A exigência é cobrada de um estado que só existe quando já é tarde.
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

RISCO = "RISK-APPROVAL-001"


@pytest.fixture(autouse=True)
def _restaura_repo():
    yield
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


def _achados(repo_copy: Path, run_auditor) -> list[dict]:
    code, findings = run_auditor("audit_governance", repo_copy)
    return [f for f in findings if f["origin"] == "approval_gate"]


def test_a_lacuna_APARECE_mesmo_com_tudo_verde(repo_copy, run_auditor):
    """O estado de hoje: propostas exigindo aval, mergeáveis sem que ninguém o resolva.

    Este é o teste que dá sentido ao resto. A lacuna existia há 21 propostas e não produzia sinal
    nenhum — o repositório inteiro verde, com uma exigência declarada que nada cobrava.
    """
    achados = _achados(repo_copy, run_auditor)
    assert achados, "a lacuna precisa aparecer, mesmo quando nada mais está vermelho"
    assert achados[0]["risk"] == RISCO


def test_com_risco_DATADO_o_achado_nao_bloqueia(repo_copy, run_auditor):
    """`info`, e a escolha é deliberada — não é brandura.

    Ninguém neste repositório consegue satisfazer a condição por PR: `required_pull_request_reviews`
    é configuração de admin. Bloquear produziria vermelho PERMANENTE, e vermelho permanente é
    exatamente como um fiscal aprende a ser ignorado. O que se recusa não é a lacuna — é o silêncio
    sobre ela.
    """
    code, findings = run_auditor("audit_governance", repo_copy)
    achados = [f for f in findings if f["origin"] == "approval_gate"]
    assert achados[0]["severity"] == "info", achados[0]
    bloqueantes = [f for f in findings if f["severity"] != "info"]
    assert not bloqueantes, bloqueantes


def test_risco_SEM_data_BLOQUEIA(repo_copy, run_auditor):
    """Risco aceito sem data é risco esquecido (princípio (g)).

    É a trava que impede esta proposta de virar a desculpa permanente que ela poderia ser: aceitar
    a lacuna custa uma data a alguém, e sem a data o achado volta a bloquear.
    """
    alvo = repo_copy / "governance/risk-register.yaml"
    texto = alvo.read_text(encoding="utf-8")
    assert '    due: "2026-11-03"\n    owner: security_owner' in texto
    alvo.write_text(texto.replace('    due: "2026-11-03"\n    owner: security_owner',
                                  "    owner: security_owner", 1), encoding="utf-8")

    achados = _achados(repo_copy, run_auditor)
    assert achados, "sem data, a lacuna tem de voltar a bloquear"
    assert achados[0]["severity"] == "high", achados[0]


def test_risco_AUSENTE_BLOQUEIA(repo_copy, run_auditor):
    """Apagar o risco não apaga a lacuna — e essa é a diferença entre suprimir e resolver.

    Sem esta mordida, a correção mais barata para o achado seria remover o risco do registro, e o
    repositório voltaria ao estado exato de antes desta proposta: lacuna real, tudo verde.
    """
    alvo = repo_copy / "governance/risk-register.yaml"
    texto = alvo.read_text(encoding="utf-8")
    inicio = texto.index(f"  - id: {RISCO}")
    fim = texto.index("\nrisk_exemptions:")
    alvo.write_text(texto[:inicio] + texto[fim + 1:], encoding="utf-8")

    achados = _achados(repo_copy, run_auditor)
    assert achados, "risco removido não pode fazer a lacuna sumir"
    assert achados[0]["severity"] == "high", achados[0]


def test_sem_proposta_exigindo_aval_nao_ha_achado(repo_copy, run_auditor):
    """O outro lado: o fiscal fala da lacuna REAL, não da possibilidade dela.

    Um repositório sem proposta pendente de aval não tem esta exposição, e acusá-lo mesmo assim
    tornaria o achado ruído constante — que é como se ensina a ignorá-lo.
    """
    d = repo_copy / "harness/change-proposals"
    import yaml
    for p in d.glob("*.yaml"):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        prop = doc.get("proposal") or {}
        if prop.get("human_approval_required") and prop.get("status") in ("draft", "approved"):
            prop["human_approval_required"] = False
            p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    assert not _achados(repo_copy, run_auditor)
