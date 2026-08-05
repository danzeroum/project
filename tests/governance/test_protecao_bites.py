"""Mordidas da trava externa em duas camadas (CP-024 / ADR-020).

A pergunta que estes testes protegem é a frase que abre o CLAUDE.md: *uma trava que o vigiado pode
desligar em silêncio não é uma trava.* Ela era parcialmente falsa aqui, e continua parcialmente
falsa — a diferença é que agora a parte falsa está declarada, datada e barulhenta.

`verify_protection` recebe a resposta da API como argumento. O motivo é o de sempre nesta casa:
"a proteção está desligada" e "não consegui perguntar" pedem reações opostas, e um verificador que
faz a chamada dentro de si mesmo não consegue manter os dois separados.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import verify_protection as vp  # noqa: E402

PROTEGIDOS = ["ci/", "harness/", ".github/"]
CODEOWNERS_OK = ["/ci/ @dono", "/harness/ @dono", "/.github/ @dono"]

PROTECAO_OK = {
    "required_pull_request_reviews": {"require_code_owner_reviews": True},
    "allow_force_pushes": {"enabled": False},
}


def test_protecao_ligada_e_caminhos_com_dono_passa():
    """O par positivo. Sem ele, um verificador que reprovasse tudo passaria em todos os negativos."""
    assert vp.verify_protection(protection=PROTECAO_OK, codeowners=CODEOWNERS_OK,
                                protected_paths=PROTEGIDOS) == []


def test_protecao_ausente_reprova():
    v = vp.verify_protection(protection={}, codeowners=CODEOWNERS_OK, protected_paths=PROTEGIDOS)
    assert any("não tem proteção alguma" in m for m in v), v


def test_review_sem_code_owner_reprova():
    """É o elo que faz protected_paths significar alguma coisa.

    Sem ele, qualquer aprovador serve para mudar um fiscal — e "o fiscal só muda com revisão de
    quem é dono dele" vira "o fiscal muda com revisão de qualquer um".
    """
    protecao = {**PROTECAO_OK,
                "required_pull_request_reviews": {"require_code_owner_reviews": False}}
    v = vp.verify_protection(protection=protecao, codeowners=CODEOWNERS_OK,
                             protected_paths=PROTEGIDOS)
    assert any("review de CODE OWNER" in m for m in v), v


def test_force_push_permitido_reprova():
    """Histórico reescrevível torna TODA âncora por commit uma afirmação sobre conteúdo mutável.

    target.lock, mold_release.commit_sha, executed_in.merge_commit_sha — as três dependem de o
    commit citado continuar sendo o que era.
    """
    protecao = {**PROTECAO_OK, "allow_force_pushes": {"enabled": True}}
    v = vp.verify_protection(protection=protecao, codeowners=CODEOWNERS_OK,
                             protected_paths=PROTEGIDOS)
    assert any("force push" in m for m in v), v


def test_caminho_protegido_sem_dono_reprova():
    v = vp.verify_protection(protection=PROTECAO_OK, codeowners=["/ci/ @dono"],
                             protected_paths=PROTEGIDOS)
    assert any("harness/" in m for m in v), v


def test_indeterminacao_nao_vira_violacao():
    """Princípio (h), e aqui ele tem um motivo bem concreto.

    A API responde 404 tanto para "sem proteção" quanto para "sem permissão de ver". Os dois são
    indistinguíveis de fora — escolher a conclusão mais grave produziria alarme de fraude toda vez
    que o token não tivesse escopo, e alarme que dispara sem fraude é alarme que se desliga.
    """
    assert vp.verify_protection(protection=None, codeowners=[], protected_paths=PROTEGIDOS) == []


# --------------------------------------------------------------------------------------
# O estado declarado da camada externa
# --------------------------------------------------------------------------------------

def test_auditoria_externa_desligada_aparece_no_laudo(repo_copy: Path, run_auditor):
    """O desligado é DECLARADO, não omitido: a lacuna aparece a cada execução."""
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 0
    externos = [f for f in findings if f["origin"] == "external_audit"]
    assert externos, [f["origin"] for f in findings]
    assert externos[0]["severity"] == "info", externos


def test_desligada_sem_risco_declarado_reprova(repo_copy: Path, run_auditor):
    """Desligar a camada externa tem que CUSTAR um risco datado a alguém."""
    caminho = repo_copy / "harness/harness.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["external_audit"]["accepted_risk"] = "RISK-QUE-NAO-EXISTE"
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("RISCO-AUSENTE") for f in findings), [f["id"] for f in findings]


def test_risco_aceito_sem_data_reprova(repo_copy: Path, run_auditor):
    """Princípio (g): risco aceito sem data é risco esquecido."""
    caminho = repo_copy / "governance/risk-register.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    for risco in doc["risks"]:
        if risco["id"] == "RISK-EXT-001":
            risco.pop("due", None)
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("RISCO-SEM-DATA") for f in findings), [f["id"] for f in findings]


def test_workflow_sem_auditoria_externa_reprova(repo_copy: Path, run_auditor):
    """Remover o passo de verificação é o gesto exato de quem quer desligar a trava."""
    wf = repo_copy / ".github/workflows/governance.yml"
    wf.write_text(wf.read_text(encoding="utf-8").replace(
        "python ci/verify_protection.py", "true # removido"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f.get("assertion") == "ADR-020-A2" for f in findings), [f["id"] for f in findings]


# --------------------------------------------------------------------------------------
# Camada externa LIGADA: o que passa a ser exigido
# --------------------------------------------------------------------------------------

def _ligar(root: Path) -> None:
    caminho = root / "harness/harness.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["external_audit"]["enabled"] = True
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _atestado(root: Path, *, expires: str) -> None:
    import json

    destino = root / "harness/state"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "protection-attestation.json").write_text(json.dumps({
        "schema_version": "1.0", "metadata_version": "1.0",
        "source_of_truth": True, "generated_from": None,
        "attestation": {
            "repository": "danzeroum/project", "branch": "main",
            "checked_at": "2026-08-05T00:00:00+00:00", "expires_at": expires,
            "ruleset_ref": "org/rulesets/42",
            "issuer": {"identity": "harness-attestor", "kind": "github_app"},
            "verifier_version": "1.0", "config_digest": "sha256:" + "a" * 64,
        },
    }, indent=2), encoding="utf-8")


def test_ligada_sem_atestado_reprova(repo_copy: Path, run_auditor):
    _ligar(repo_copy)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("SEM-ATESTADO") for f in findings), [f["id"] for f in findings]


def test_atestado_externo_expirado_reprova(repo_copy: Path, run_auditor):
    """Expirado bloqueia do mesmo modo que ausente — senão o atestado vira carimbo eterno."""
    _ligar(repo_copy)
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=ontem)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("ATESTADO-EXPIRADO") for f in findings), [f["id"] for f in findings]


def test_atestado_valido_passa(repo_copy: Path, run_auditor):
    """O par positivo da camada ligada: com atestado válido, nada de externo bloqueia."""
    _ligar(repo_copy)
    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha)
    code, findings = run_auditor("audit_governance", repo_copy)
    bloqueantes = [f for f in findings
                   if f["origin"] == "external_audit" and f["severity"] != "info"]
    assert not bloqueantes, bloqueantes


def test_atestado_emitido_por_identidade_nao_autorizada_reprova(repo_copy: Path, run_auditor):
    """Atestado anônimo é indistinguível de atestado forjado — e quem mais teria motivo para
    forjá-lo é o próprio repositório fiscalizado."""
    import json

    _ligar(repo_copy)
    amanha = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")
    _atestado(repo_copy, expires=amanha)
    caminho = repo_copy / "harness/state/protection-attestation.json"
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    del doc["attestation"]["issuer"]
    caminho.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("ATESTADO-INVALIDO") for f in findings), [f["id"] for f in findings]


def test_cp_024_esta_deferred():
    """A CP não se declara implementada, e isso é uma afirmação verificável.

    A §7 do plano é explícita: sem identidade externa viável, a CP-024 fica `deferred` — não conta
    como implementada. Se alguém a promover a `executed` sem ligar a camada externa, este teste
    falha, e é a única coisa que impede a promoção silenciosa.
    """
    doc = yaml.safe_load(
        (REPO / "harness/change-proposals/CP-024-trava-externa-em-duas-camadas.yaml")
        .read_text(encoding="utf-8"))
    harness = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    if not harness["external_audit"]["enabled"]:
        assert doc["proposal"]["status"] == "deferred", \
            "camada externa desligada e CP não está deferred — ela estaria passando por pronta"
