"""A referência do produtor é uma coisa só (CP-051, ADR-032).

Estas mordidas amarram o *assurance lock* aos fixtures: o estado e o adapter_source_commit
declarados na matriz são os dos fixtures, o hash canônico de cada fixture é o do produtor real
(json.dumps sort_keys, ensure_ascii=False — a serialização canônica do adapter), e a classificação
de cada fixture é exatamente a que a matriz declara. Nenhum fixture é aceitável em produção ou CI
estrito; o lugar dele é fixture/preparação — ou nenhum, se for local, sem SHA ou de source
divergente.

Reconciliação pós-merge (Sprint 6.2): a PR #2 foi mergeada (main 443da92…, source f19e593…), e o
estado é merged_unreleased — merge no main não é release publicado, e released exige metadados.

A matriz é a autoridade de estado; estes testes são o elo que impede a matriz e os fixtures de
divergirem sem ninguém notar.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
MATRIZ = REPO / "harness/suite-contract/evidence-bundle/compatibility-matrix.yaml"
FIXTURES = REPO / "harness/suite-contract/evidence-bundle/fixtures"

COMMIT_MAIN = "443da92dbdb22a9af18aa6eebb51aac2da901458"
SOURCE_ADAPTER = "f19e593257b8480e7822795ba49a36f284963371"


# ── utilidades ────────────────────────────────────────────────────────────────────────────────

def matriz() -> dict:
    return yaml.safe_load(MATRIZ.read_text(encoding="utf-8"))


def situacoes() -> dict[str, dict]:
    return {s["id"]: s for s in matriz()["assurance_lock"]["situations"]}


def referencia() -> dict:
    return matriz()["assurance_lock"]["candidate_reference"]


def bundle(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))["evidence_bundle"]


def hash_canonico(d: dict) -> str:
    """A serialização canônica do adapter: json.dumps(sort_keys, ensure_ascii=False), utf-8."""
    interno = {k: v for k, v in d.items() if k != "integrity"}
    canonical = json.dumps(interno, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classificar(b: dict) -> str:
    """Classifica um bundle como a matriz classifica — a fronteira em uma função."""
    if b["producer"].get("local_execution"):
        return situacoes()["SIT-LOCAL-EXEC"]["expected"]
    if not b["producer"].get("suite_commit"):
        return situacoes()["SIT-NO-COMMIT-SHA"]["expected"]
    if b["producer"]["suite_commit"] != referencia()["adapter_source_commit"]:
        return situacoes()["SIT-ADAPTER-COMMIT-MISMATCH"]["expected"]
    return situacoes()["SIT-MERGED-UNRELEASED-FIXTURE"]["expected"]


# ── o elo matriz ↔ fixture ───────────────────────────────────────────────────────────────────

def test_matriz_declara_a_referencia_do_produtor():
    """A matriz trava o produtor: mergeado no main, SEM release, e a fonte do adapter."""
    ref = referencia()
    assert ref["repository"] == "danzeroum/pse-suite"
    assert ref["branch"] == "main"
    assert ref["commit"] == COMMIT_MAIN
    assert ref["adapter_source_commit"] == SOURCE_ADAPTER
    assert ref["state"] == "merged_unreleased"
    assert ref["release_eligible"] is False


def test_produtor_nao_e_released_ainda():
    """Merge no main não é release: o estado é merged_unreleased, nunca released (sem tag,
    manifesto ou pin, released seria uma promessa)."""
    assert referencia()["state"] != "released"


def test_o_fecho_de_situacoes_e_completo_e_fechado():
    """11 situações, ids únicos — o vocabulário de expected/scope é o do contrato."""
    ss = situacoes()
    assert len(ss) == 11
    assert len({s["id"] for s in matriz()["assurance_lock"]["situations"]}) == 11
    for s in ss.values():
        assert s["expected"] in {
            "blocked", "accepted_in_fixture_only", "not_assessed",
            "not_satisfied", "release_eligible_false"}
        assert s["scope"] in {"strict_ci", "production", "fixture_preparation"}


def test_o_commit_do_fixture_e_o_adapter_source_commit():
    """candidate-valid.json é DO adapter mergeado — source f19e593…, o SHA que a matriz declara
    como adapter_source_commit (M39)."""
    b = bundle("candidate-valid.json")
    assert b["producer"]["suite_commit"] == SOURCE_ADAPTER
    assert b["producer"]["suite_commit"] == referencia()["adapter_source_commit"]


@pytest.mark.parametrize("nome", [
    "candidate-valid.json", "candidate-local.json", "candidate-no-commit.json",
])
def test_hash_canonico_de_cada_fixture_confere(nome: str):
    """Integridade não é decorativa: o hash declarado é o da serialização canônica do dict."""
    b = bundle(nome)
    assert b["integrity"]["canonical_hash"] == hash_canonico(b), nome


def test_candidato_estrito_e_aceito_somente_em_fixture():
    """O único bundle aceito é o do adapter mergeado, e só como fixture/preparação."""
    b = bundle("candidate-valid.json")
    assert classificar(b) == "accepted_in_fixture_only"
    s = situacoes()["SIT-MERGED-UNRELEASED-FIXTURE"]
    assert s["expected"] == "accepted_in_fixture_only"
    assert s["scope"] == "fixture_preparation"


def test_candidato_local_e_bloqueado_no_ci_estrito():
    """local_execution: true é acusado — evidência local não entra em CI estrito."""
    b = bundle("candidate-local.json")
    assert b["producer"]["local_execution"] is True
    assert classificar(b) == "blocked"
    assert situacoes()["SIT-LOCAL-EXEC"]["scope"] == "strict_ci"


def test_candidato_sem_sha_e_bloqueado():
    """Proveniência sem SHA verificável não é proveniência — blocked, sem exceção."""
    b = bundle("candidate-no-commit.json")
    assert "suite_commit" not in b["producer"]
    assert classificar(b) == "blocked"
    assert situacoes()["SIT-NO-COMMIT-SHA"]["scope"] == "strict_ci"


def test_merged_unreleased_nao_e_fonte_de_producao():
    """M37 — mergeado sem release é blocked em produção E como fonte no CI estrito."""
    assert situacoes()["SIT-MERGED-UNRELEASED-PROD"]["expected"] == "blocked"
    assert situacoes()["SIT-MERGED-UNRELEASED-PROD"]["scope"] == "production"
    assert situacoes()["SIT-MERGED-UNRELEASED-CI"]["expected"] == "blocked"
    assert situacoes()["SIT-MERGED-UNRELEASED-CI"]["scope"] == "strict_ci"


def test_merged_unreleased_aceito_somente_em_fixture():
    """O lugar do produtor mergeado sem release é fixture/preparação, e só."""
    s = situacoes()["SIT-MERGED-UNRELEASED-FIXTURE"]
    assert s["expected"] == "accepted_in_fixture_only"
    assert s["scope"] == "fixture_preparation"


def test_released_exige_metadados_verificaveis():
    """M38 — released só é expresso com tag/version/manifest/hash (bloco release exigido)."""
    import jsonschema
    schema = json.loads(
        (REPO / "harness/schemas/evidence-reference.schema.json").read_text(encoding="utf-8"))

    base = dict(referencia())
    base["state"] = "released"
    base["release_eligible"] = True
    sem_release = dict(base)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(sem_release)

    com_release_incompleto = dict(base)
    com_release_incompleto["release"] = {"tag": "v0.4.0", "version": "0.4.0"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(com_release_incompleto)

    com_release_completo = dict(base)
    com_release_completo["release"] = {
        "tag": "v0.4.0", "version": "0.4.0", "commit": COMMIT_MAIN,
        "manifest": "harness/releases/v0.4.0.manifest.json",
        "artifact_hash": "sha256:" + "0" * 64,
    }
    jsonschema.Draft202012Validator(schema).validate(com_release_completo)


def test_source_commit_divergente_e_bloqueado():
    """M39 — bundle que não saiu do adapter mergeado não é evidência do produtor declarado."""
    b = bundle("candidate-valid.json")
    b["producer"]["suite_commit"] = COMMIT_MAIN
    assert classificar(b) == "blocked"
    assert situacoes()["SIT-ADAPTER-COMMIT-MISMATCH"]["scope"] == "strict_ci"


def test_ctrl_dep_001_permanece_nao_satisfeito():
    """M40 — CTRL-DEP-001 não é satisfeito por evidência de produtor não releaseado."""
    s = situacoes()["SIT-CTRL-DEP-001"]
    assert s["expected"] == "not_satisfied"
    assert s["scope"] == "strict_ci"


def test_nenhum_fixture_aponta_para_main_ou_latest():
    """Proibição por forma: a palavra main/latest não existe nos fixtures."""
    for nome in ("candidate-valid.json", "candidate-local.json", "candidate-no-commit.json"):
        texto = (FIXTURES / nome).read_text(encoding="utf-8")
        assert re.search(r"(main|latest)", texto) is None, nome


def test_nenhum_fixture_contem_url_de_repositorio():
    """A referência é org/repo, nunca URL — molde genérico (ADR-008-A5)."""
    for nome in ("candidate-valid.json", "candidate-local.json", "candidate-no-commit.json"):
        texto = (FIXTURES / nome).read_text(encoding="utf-8")
        assert re.search(r"github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", texto) is None, nome


# ── integridade reage a adulteração ──────────────────────────────────────────────────────────

def test_hash_reage_a_commit_trocado(tmp_path: Path):
    """Trocar o suite_commit muda o hash canônico — o elo com a matriz se rompe."""
    b = bundle("candidate-valid.json")
    b["producer"]["suite_commit"] = COMMIT_MAIN
    assert b["integrity"]["canonical_hash"] != hash_canonico(b)


def test_hash_reage_a_assertion_trocada(tmp_path: Path):
    """Trocar um dado de assertion muda o hash — o fixture é um dado assinado, não um texto."""
    b = bundle("candidate-valid.json")
    b["assertions"][0]["executed_at"] = "2099-01-01T00:00:00Z"
    assert b["integrity"]["canonical_hash"] != hash_canonico(b)


def test_matriz_bloqueia_bundle_em_producao():
    """A matriz diz o que nenhum teste deveria precisar provar: produção não aceita evidência de
    produtor não releaseado."""
    s = situacoes()["SIT-MERGED-UNRELEASED-PROD"]
    assert s["expected"] == "blocked"
    assert s["scope"] == "production"