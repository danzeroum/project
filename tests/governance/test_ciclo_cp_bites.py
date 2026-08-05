"""Mordidas do ciclo de vida da CP e da cadeia de decisão (CP-022 / CP-023, ADR-016 / ADR-017).

Um teste por modo de fraude. A lista de modos não é decorativa: quem lê um verificador de aprovação
não consegue ver a checagem que ninguém escreveu, então cada fraude tem um teste que falharia se a
checagem sumisse. É a única forma de a ausência ficar visível.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import audit_friction as af  # noqa: E402
import harness_lib as hl  # noqa: E402
import verify_approval as va  # noqa: E402

AUTOR = "danzeroum"
REVISOR = "outra-pessoa"
HEAD = "a" * 40
MERGE = "b" * 40
ANTIGO = "c" * 40


def _proposta(**over) -> dict:
    p = {
        "id": "CP-999",
        "status": "executed",
        "risk_assessment": {"level": "high", "rationale": "x"},
        "executed_in": {"pr_number": 7, "merge_commit_sha": MERGE},
        "approved_by": {"login": REVISOR, "review_id": 100, "pr_number": 7,
                        "approved_at": "2026-08-05T12:00:00Z"},
    }
    p.update(over)
    return p


def _pr(**over) -> dict:
    d = {"user": {"login": AUTOR}, "head": {"sha": HEAD}, "merge_commit_sha": MERGE}
    d.update(over)
    return d


def _review(**over) -> dict:
    r = {"id": 100, "state": "APPROVED", "user": {"login": REVISOR}, "commit_id": HEAD}
    r.update(over)
    return r


# --------------------------------------------------------------------------------------
# O par positivo primeiro. Sem ele, um verificador que reprovasse tudo passaria em todos os
# testes negativos deste arquivo.
# --------------------------------------------------------------------------------------

def test_review_aprovado_no_head_integrado_passa():
    assert va.verify_approval(proposal=_proposta(), pr=_pr(), reviews=[_review()]) == []


def test_cp_high_com_aprovador_declarado_sem_review_real_reprova():
    """Fraude 1: citar um review que não existe. Qualquer checagem textual deixaria passar."""
    v = va.verify_approval(proposal=_proposta(), pr=_pr(), reviews=[])
    assert any("não existe no PR" in m for m in v), v


def test_review_que_nao_aprova_reprova():
    """Fraude 2: um COMMENTED não é um aval."""
    v = va.verify_approval(proposal=_proposta(), pr=_pr(), reviews=[_review(state="COMMENTED")])
    assert any("não 'APPROVED'" in m for m in v), v


def test_autoaprovacao_reprova():
    """Fraude 3: auto-aprovação com um passo a mais continua sendo auto-aprovação."""
    v = va.verify_approval(
        proposal=_proposta(approved_by={"login": AUTOR, "review_id": 100, "pr_number": 7,
                                        "approved_at": "2026-08-05T12:00:00Z"}),
        pr=_pr(), reviews=[_review(user={"login": AUTOR})])
    assert any("auto-aprovação" in m for m in v), v


def test_review_aprovado_antes_do_ultimo_push_reprova():
    """Fraude 4, a que motiva o endurecimento desta rodada.

    Conforme a configuração de dismissal, o estado APPROVED SOBREVIVE a pushes novos: aprova-se o
    diff A, empurra-se o diff B, e a API segue respondendo APPROVED. Sem esta checagem, o aval
    humano vira carimbo que se obtém uma vez e se reusa.
    """
    v = va.verify_approval(proposal=_proposta(), pr=_pr(), reviews=[_review(commit_id=ANTIGO)])
    assert any("anterior ao último push" in m for m in v), v


def test_aval_de_outro_pr_reprova():
    """Fraude 5: apontar o aval para um PR e a execução para outro."""
    v = va.verify_approval(
        proposal=_proposta(approved_by={"login": REVISOR, "review_id": 100, "pr_number": 99,
                                        "approved_at": "2026-08-05T12:00:00Z"}),
        pr=_pr(), reviews=[_review()])
    assert any("precisa ser DESTE merge" in m for m in v), v


def test_cp_high_sem_aprovador_reprovada():
    v = va.verify_approval(proposal=_proposta(approved_by=None), pr=_pr(), reviews=[_review()])
    assert any("não é 'aval houve'" in m for m in v), v


# --------------------------------------------------------------------------------------
# Travas de schema — o que o verificador não precisa checar porque é estruturalmente impossível
# --------------------------------------------------------------------------------------

def _cp_doc(**over) -> dict:
    proposal = {
        "id": "CP-999", "title": "t", "author_kind": "agent",
        "created_at": "2026-08-05T12:00:00Z", "capabilities_affected": [],
        "components_affected": [], "paths_affected": ["ci/x.py"],
        "risk_assessment": {"level": "high", "rationale": "x"},
        "required_gates": ["unit-tests"], "tests_required": [],
        "human_approval_required": True, "change_mode": "pull_request",
        "status": "approved",
    }
    proposal.update(over)
    return {"schema_version": "1.1", "metadata_version": "1.0", "source_of_truth": True,
            "generated_from": None, "proposal": proposal}


def test_cp_executada_sem_pr_reprovada():
    doc = _cp_doc(status="executed")
    erros = hl.schema_errors("cp.yaml", "change-proposal.schema.json", doc)
    assert any("executed_in" in e for e in erros), erros


def test_cp_executada_high_sem_aprovador_reprovada_pelo_schema():
    doc = _cp_doc(status="executed", executed_in={"pr_number": 7, "merge_commit_sha": MERGE})
    erros = hl.schema_errors("cp.yaml", "change-proposal.schema.json", doc)
    assert any("approved_by" in e for e in erros), erros


def test_cp_high_executada_so_com_numero_de_pr_reprova():
    """Número de PR é ponteiro para uma conversa; merge commit é o conteúdo."""
    doc = _cp_doc(status="executed", executed_in={"pr_number": 7},
                  approved_by={"login": REVISOR, "review_id": 1, "pr_number": 7,
                               "approved_at": "2026-08-05T12:00:00Z"})
    erros = hl.schema_errors("cp.yaml", "change-proposal.schema.json", doc)
    assert any("merge_commit_sha" in e for e in erros), erros


def test_cp_10_continua_valida_sem_campos_de_ciclo():
    """A não-retroatividade é parte da decisão: registro que se reescreve deixa de ser registro."""
    doc = _cp_doc()
    doc["schema_version"] = "1.0"
    for campo in ("status", "paths_affected"):
        doc["proposal"].pop(campo, None)
    assert hl.schema_errors("cp.yaml", "change-proposal.schema.json", doc) == []


def test_cp_11_sem_status_reprova():
    doc = _cp_doc()
    doc["proposal"].pop("status")
    erros = hl.schema_errors("cp.yaml", "change-proposal.schema.json", doc)
    assert any("status" in e for e in erros), erros


# --------------------------------------------------------------------------------------
# Ciclo de vida — o fiscal sem rede
# --------------------------------------------------------------------------------------

def _escrever_cp(root: Path, nome: str, doc: dict) -> None:
    (root / "harness/change-proposals" / nome).write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_cp_executada_declarando_pr_de_outro_aval_reprova(repo_copy: Path, run_auditor):
    doc = _cp_doc(status="executed",
                  executed_in={"pr_number": 7, "merge_commit_sha": MERGE},
                  approved_by={"login": REVISOR, "review_id": 1, "pr_number": 8,
                               "approved_at": "2026-08-05T12:00:00Z"})
    _escrever_cp(repo_copy, "CP-999-teste.yaml", doc)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("APROVACAO-DE-OUTRO-PR") for f in findings), [f["id"] for f in findings]


def test_cp_aprovada_com_merge_declarado_reprova(repo_copy: Path, run_auditor):
    """Ou a proposta foi executada e o status mente, ou o campo foi preenchido antes do fato."""
    doc = _cp_doc(status="approved", executed_in={"pr_number": 7, "merge_commit_sha": MERGE})
    _escrever_cp(repo_copy, "CP-998-teste.yaml", doc)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("NAO-EXECUTADA-COM-MERGE") for f in findings), [f["id"] for f in findings]


# --------------------------------------------------------------------------------------
# Cadeia de decisão (CP-023)
# --------------------------------------------------------------------------------------

def test_parecer_nao_consumido_reprova(repo_copy: Path, run_auditor):
    """Achado encaminhado sem destino: indistinguível de achado tratado, e é como um achado morre."""
    caminho = repo_copy / "governance/conformance-review.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    for achado in doc["review"]["findings"]:
        if achado["disposition"] == "risk_entry":
            achado.pop("consumed_by", None)
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["origin"] == "decision_chain" for f in findings), [f["id"] for f in findings]


def test_parecer_consumido_por_artefato_inexistente_reprova(repo_copy: Path, run_auditor):
    """Destino que não resolve é trava quebrada, não satisfeita — a lógica do ADR-006."""
    caminho = repo_copy / "governance/conformance-review.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    for achado in doc["review"]["findings"]:
        if achado["disposition"] == "risk_entry":
            achado["consumed_by"] = {"kind": "risk", "ref": "RISK-QUE-NAO-EXISTE"}
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any("não existe entre os" in f["summary"] for f in findings), [f["summary"] for f in findings]


def test_achado_encaminhado_sem_consumo_reprova_no_schema():
    doc = {
        "schema_version": "1.0", "metadata_version": "1.0", "source_of_truth": True,
        "generated_from": None,
        "review": {"produced_by": "agent", "agent": "conformance",
                   "scope_fingerprint": "sha256:" + "0" * 64,
                   "findings": [{"id": "CONF-900", "severity": "low",
                                 "summary": "um achado qualquer aqui",
                                 "disposition": "change_proposal"}],
                   "not_assessed": ["nada"]},
    }
    erros = hl.schema_errors("cr.yaml", "conformance-review.schema.json", doc)
    assert any("consumed_by" in e for e in erros), erros


# --------------------------------------------------------------------------------------
# Fiscal de atrito — informativo, e a prova de que ele NÃO reprova é parte do contrato
# --------------------------------------------------------------------------------------

def test_audit_friction_detecta_drift_pelo_criterio():
    """Mesmo risco + mesmo path + menos de 7 dias. Os três, não dois."""
    a = {"id": "CP-A", "risk_assessment": {"level": "high"}, "paths_affected": ["ci/x.py"],
         "created_at": "2026-08-01T00:00:00Z"}
    b = {"id": "CP-B", "risk_assessment": {"level": "high"}, "paths_affected": ["ci/x.py"],
         "created_at": "2026-08-03T00:00:00Z"}
    sinais = af.detectar_drift([a, b])
    assert len(sinais) == 1 and sinais[0]["proposals"] == ["CP-A", "CP-B"]


@pytest.mark.parametrize("mudanca,motivo", [
    ({"created_at": "2026-09-30T00:00:00Z"}, "fora da janela de 7 dias"),
    ({"paths_affected": ["ci/outro.py"]}, "caminho diferente"),
    ({"risk_assessment": {"level": "low"}}, "risco diferente"),
])
def test_audit_friction_nao_inventa_drift(mudanca, motivo):
    """Os três critérios são conjunção. Um medidor que disparasse com dois viraria ruído, e ruído
    é como um sinal de atrito é aprendido a ignorar."""
    a = {"id": "CP-A", "risk_assessment": {"level": "high"}, "paths_affected": ["ci/x.py"],
         "created_at": "2026-08-01T00:00:00Z"}
    b = {**a, "id": "CP-B", "created_at": "2026-08-03T00:00:00Z", **mudanca}
    assert af.detectar_drift([a, b]) == [], motivo


def test_audit_friction_nunca_reprova(repo_copy: Path, monkeypatch):
    """O contrato do fiscal de atrito. Se ele virasse gate, criaria o incentivo de não declarar
    propostas para manter o número baixo — destruindo o registro de onde ele tira o sinal."""
    import importlib

    monkeypatch.setenv("HARNESS_REPO_ROOT", str(repo_copy))
    importlib.reload(hl)
    modulo = importlib.reload(af)
    assert modulo.main(["--quiet", "--snapshot"]) == 0
    assert (repo_copy / "harness/reports/friction-audit.json").exists()


def test_captura_vermelho_transitorio_associa_a_cp_aberta():
    """Adendo A2: o vermelho de uma cascata sob CP aberta hoje escapa de todo registro."""
    propostas = [{"id": "CP-A", "status": "approved", "risk_assessment": {"level": "high"}}]
    achados = [{"location": "business/capabilities.yaml"}, {"location": "architecture/adr"}]
    sinais = af.capturar_vermelho_transitorio(propostas, achados)
    assert len(sinais) == 1
    assert sinais[0]["under_proposals"] == ["CP-A"]
    assert sinais[0]["breaking_points"] == ["architecture/adr", "business/capabilities.yaml"]


def test_sem_cp_aberta_nao_ha_vermelho_transitorio():
    propostas = [{"id": "CP-A", "status": "executed", "risk_assessment": {"level": "high"}}]
    assert af.capturar_vermelho_transitorio(propostas, [{"location": "x"}]) == []


# --------------------------------------------------------------------------------------
# A lacuna do aval independente (CP-035 / ADR-027)
# --------------------------------------------------------------------------------------

def _cp_do_disco(nome: str) -> dict:
    caminho = REPO / "harness/change-proposals" / nome
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def test_o_dono_aprovando_o_proprio_pr_e_recusado():
    """A borda que decidiu o desfecho: não há revisor independente, e o fiscal recusa o aval de
    quem propôs. Recusaria mesmo que a API o permitisse — e a API também recusa."""
    v = va.verify_approval(
        proposal={"id": "CP-T", "executed_in": {"pr_number": 9, "merge_commit_sha": MERGE},
                  "approved_by": {"login": AUTOR, "review_id": 1, "pr_number": 9,
                                  "approved_at": "2026-08-05T18:00:00Z"}},
        pr={"user": {"login": AUTOR}, "head": {"sha": HEAD}, "merge_commit_sha": MERGE},
        reviews=[{"id": 1, "state": "APPROVED", "user": {"login": AUTOR}, "commit_id": HEAD}])
    assert any("é o autor do PR" in m for m in v)


def test_aval_em_um_pr_e_execucao_em_outro_e_recusado():
    """O caminho consolidado que se cogitou: aval no PR de fechamento, execução no PR original."""
    v = va.verify_approval(
        proposal={"id": "CP-T", "executed_in": {"pr_number": 9, "merge_commit_sha": MERGE},
                  "approved_by": {"login": REVISOR, "review_id": 1, "pr_number": 46,
                                  "approved_at": "2026-08-05T18:00:00Z"}},
        pr={"user": {"login": AUTOR}, "head": {"sha": HEAD}, "merge_commit_sha": MERGE},
        reviews=[{"id": 1, "state": "APPROVED", "user": {"login": REVISOR}, "commit_id": HEAD}])
    assert any("o aval precisa ser DESTE merge" in m for m in v)


def test_as_doze_cps_fechaveis_seguem_approved():
    """O estado VERDADEIRO: integradas, com aval declarado como necessário e nunca prestado.

    Se alguma virar `executed`, este teste cai — e cair é o ponto: o fechamento tem de ser uma
    decisão visível, com o review real por trás, não um campo que apareceu num commit qualquer.
    """
    fechaveis = ["CP-022-ciclo-de-vida-da-cp.yaml",
                 "CP-023-consumo-obrigatorio-de-pareceres.yaml"]
    fechaveis += [p.name for p in sorted((REPO / "harness/change-proposals").glob("CP-0[23]*.yaml"))
                  if "CP-025" <= p.name[:6] <= "CP-034"]
    assert len(fechaveis) == 12, fechaveis
    for nome in fechaveis:
        assert _cp_do_disco(nome)["proposal"]["status"] == "approved", nome


def test_cp_021_nao_e_promovida_a_1_1():
    """Os campos de ciclo existem a partir de 1.1, e a não-retroatividade é PARTE da decisão da
    CP-022. Promovê-la para caber num fechamento seria reescrever registro histórico."""
    doc = _cp_do_disco("CP-021-ancoragem-verificavel-do-molde.yaml")
    assert doc["schema_version"] == "1.0"
    assert "status" not in doc["proposal"]


def test_cp_024_continua_deferred():
    """Sua camada externa não foi implementada — RISK-EXT-001 segue aberto. `executed` seria falso."""
    assert _cp_do_disco("CP-024-trava-externa-em-duas-camadas.yaml")["proposal"]["status"] == "deferred"


def test_a_lacuna_do_aval_e_risco_aberto_com_data():
    """Princípio (g): risco aceito TEM data. O schema recusa `open` sem `due`, então isto é trava."""
    reg = yaml.safe_load((REPO / "governance/risk-register.yaml").read_text(encoding="utf-8"))
    risco = next(r for r in reg["risks"] if r["id"] == "RISK-CHANGE-002")
    assert risco["status"] == "open"
    assert risco["treatment"] == "accept"
    assert risco["due"]


def test_a_recusa_de_auto_aprovacao_continua_no_codigo():
    """A asserção que mais importa, em forma de teste: quando doze propostas `approved` parecerem
    trabalho inacabado, a tentação não será conseguir o revisor que falta — será apagar a checagem
    que o exige."""
    fonte = (REPO / "ci/verify_approval.py").read_text(encoding="utf-8")
    assert "é o autor do PR" in fonte
    assert "aprovador == autor_pr" in fonte.replace("aprovador and autor_pr and aprovador == autor_pr",
                                                    "aprovador == autor_pr")
