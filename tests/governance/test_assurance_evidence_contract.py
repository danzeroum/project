"""Mordidas do contrato de evidência do produtor PSE (CP-051, ADR-032).

O assurance lock é metadado novo e paga as quatro coisas: schema, registro em DOCS, etapa em
stages.yaml e política — e as asserções de ADR-032 provam que a trava morde. Estas mordidas são o
passo negativo delas: cada teste copia o repositório, injeta UMA violação e exige que o fiscal
reprove. "O fiscal existe" e "o fiscal morde" são afirmações diferentes, e só a segunda importa.

Reconciliação pós-merge (Sprint 6.2): a PR #2 da pse-suite foi mergeada e o estado do produtor
mudou de candidate_not_merged para merged_unreleased — merge no main não é release publicado. As
mutações M36-M40 são as travas novas dessa reconciliação.

Idioma da casa: cópia em tmp_path via HARNESS_REPO_ROOT; nenhum teste toca a árvore de trabalho.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import ids_of

REPO = Path(__file__).resolve().parent.parent.parent
MATRIZ = "harness/suite-contract/evidence-bundle/compatibility-matrix.yaml"
SCHEMA_REF = "harness/schemas/evidence-reference.schema.json"
SCHEMA_LOCK = "harness/schemas/assurance-lock.schema.json"
POLITICA = "harness/policies/assurance-evidence.md"
STAGES = "harness/stages.yaml"
VALIDATE = "ci/validate_metadata.py"
README = "harness/suite-contract/evidence-bundle/README.md"
FIXTURE_VALID = "harness/suite-contract/evidence-bundle/fixtures/candidate-valid.json"


# ── utilidades ────────────────────────────────────────────────────────────────────────────────

def subs(caminho: Path, de: str, para: str) -> None:
    caminho.write_text(
        caminho.read_text(encoding="utf-8").replace(de, para), encoding="utf-8")


def apagar_linha(caminho: Path, trecho: str) -> None:
    """Apaga a linha que contém `trecho` — o inverso do file_matches da asserção."""
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines(keepends=True)
              if trecho not in l]
    caminho.write_text("".join(linhas), encoding="utf-8")


# ── metadados: a matriz é validada pelo schema ───────────────────────────────────────────────

def test_matriz_limpa_passa_metadados(repo_copy: Path, run_metadata):
    code, erros = run_metadata(repo_copy)
    assert code == 0, erros


def test_released_sem_metadados_reprova(repo_copy: Path, run_metadata):
    """M38 — 'state: released' sem tag/version/manifest/hash é inexpressível: o schema recusa."""
    subs(repo_copy / MATRIZ, "state: merged_unreleased", "state: released")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


def test_release_eligivel_reprova(repo_copy: Path, run_metadata):
    """release_eligible: true com merged_unreleased é inexpressível — sem release, não há
    elegibilidade (M36)."""
    subs(repo_copy / MATRIZ, "release_eligible: false", "release_eligible: true")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


def test_estado_fora_do_enum_reprova(repo_copy: Path, run_metadata):
    """Um quarto estado (ex.: 'integrated') não existe como opção de erro."""
    subs(repo_copy / MATRIZ, "state: merged_unreleased", "state: integrated")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


def test_faltando_situacao_reprova(repo_copy: Path, run_metadata):
    """O fecho é completo por minItems: tirar uma situação muda o contrato, não enriquece."""
    linhas = repo_copy / MATRIZ
    texto = linhas.read_text(encoding="utf-8")
    texto = texto.replace("    - id: SIT-LOCAL-EXEC\n", "").replace(
        '      situation: "bundle com local_execution: true"\n', "").replace(
        "      expected: blocked\n      scope: strict_ci\n", "", 1)
    linhas.write_text(texto, encoding="utf-8")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


def test_situacao_extra_reprova(repo_copy: Path, run_metadata):
    """Uma décima segunda situação é edição de contrato — maxItems fecha a porta para
    enriquecimento silencioso."""
    subs(repo_copy / MATRIZ,
         "    - id: SIT-NO-RELEASE\n",
         "    - id: SIT-EXTRA\n      situation: \"situação inventada\"\n"
         "      expected: accepted\n      scope: production\n    - id: SIT-NO-RELEASE\n")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


def test_situacao_fora_do_vocabulario_reprova(repo_copy: Path, run_metadata):
    """expected fora do enum fechado é recusado — 'accepted' em produção não existe como opção."""
    subs(repo_copy / MATRIZ,
         "      expected: blocked\n      scope: strict_ci",
         "      expected: accepted\n      scope: strict_ci")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


def test_matriz_sem_assurance_lock_reprova(repo_copy: Path, run_metadata):
    """Sem o bloco assurance_lock não há matriz — required no schema."""
    subs(repo_copy / MATRIZ, "assurance_lock:\n", "")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("compatibility-matrix" in e or "assurance-lock" in e for e in erros), erros


# ── as travas de ADR-032 mordem (audit_governance) ───────────────────────────────────────────

def test_auditor_limpo_passa(repo_copy: Path, run_auditor):
    """Nenhum achado ADR-032 no repositório limpo.

    O exit code pode ser 1 por vermelho PRÉ-EXISTENTE (atestado de proteção externa expirado,
    FIND-EXT-AUDIT-ATESTADO-EXPIRADO) — o que este teste exige é que o contrato novo não crie
    achado próprio. Nenhuma mutação abaixo perde valor com isso: cada uma exige o ID específico
    da asserção correspondente nos achados."""
    code, achados = run_auditor("audit_governance", repo_copy)
    assert not any(a["id"].startswith("ADR-032") for a in achados), achados


def test_auditor_morde_estado_da_matriz(repo_copy: Path, run_auditor):
    """ADR-032-A3: a matriz é a autoridade de estado — virá-la para 'released' sem metadados é
    acusado."""
    subs(repo_copy / MATRIZ, "state: merged_unreleased", "state: released")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A3" in ids_of(achados), achados


def test_auditor_morde_enum_sem_candidato(repo_copy: Path, run_auditor):
    """ADR-032-A4: o enum perde candidate_not_merged (mutação canônica do schema_lock)."""
    subs(repo_copy / SCHEMA_REF, '"candidate_not_merged"', '"merged"')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A4" in ids_of(achados), achados


def test_auditor_morde_candidato_eligivel(repo_copy: Path, run_auditor):
    """ADR-032-A5: candidate_not_merged com release_eligible liberado é a mutação canônica."""
    subs(repo_copy / SCHEMA_REF, '"const": false', '"const": true')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A5" in ids_of(achados), achados


def test_auditor_morde_enum_sem_merged(repo_copy: Path, run_auditor):
    """ADR-032-A10: o enum perde merged_unreleased — o estado real do produtor desde o merge."""
    subs(repo_copy / SCHEMA_REF, '"merged_unreleased"', '"merged"')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A10" in ids_of(achados), achados


def test_auditor_morde_enum_sem_released(repo_copy: Path, run_auditor):
    """ADR-032-A11: o enum perde released — released deixa de ser expressável por completo."""
    subs(repo_copy / SCHEMA_REF, '"released"', '"removed"')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A11" in ids_of(achados), achados


def test_auditor_morde_merged_eligivel(repo_copy: Path, run_auditor):
    """ADR-032-A12 (M36): merged_unreleased com release_eligible liberado é acusado."""
    subs(repo_copy / SCHEMA_REF, '"const": false', '"const": true')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A12" in ids_of(achados), achados


def test_auditor_morde_merged_como_fonte_ci(repo_copy: Path, run_auditor):
    """ADR-032-A13 (M37): a situação de mergeado sem release como fonte no CI estrito some da
    matriz."""
    subs(repo_copy / MATRIZ, "SIT-MERGED-UNRELEASED-CI", "SIT-MERGED-CI")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A13" in ids_of(achados), achados


def test_auditor_morde_released_sem_bloco_release(repo_copy: Path, run_auditor):
    """ADR-032-A14 (M38): o estado released perde a exigência do bloco release."""
    subs(repo_copy / SCHEMA_REF, '"required": ["release"]', '"required": []')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A14" in ids_of(achados), achados


def test_auditor_morde_release_sem_hash(repo_copy: Path, run_auditor):
    """ADR-032-A15 (M38): o bloco release perde a exigência de artifact_hash verificável."""
    subs(repo_copy / SCHEMA_REF, '"artifact_hash"', '"tag"')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A15" in ids_of(achados), achados


def test_auditor_morde_source_commit_divergente(repo_copy: Path, run_auditor):
    """ADR-032-A16 (M39): a matriz perde o adapter_source_commit — source divergente fica
    desprotegido."""
    subs(repo_copy / MATRIZ, "f19e593257b8480e7822795ba49a36f284963371",
         "0000000000000000000000000000000000000000")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A16" in ids_of(achados), achados


def test_auditor_morde_ctrl_dep_satisfied(repo_copy: Path, run_auditor):
    """ADR-032-A17 (M40): CTRL-DEP-001 vira 'satisfied' na matriz — acusado."""
    subs(repo_copy / MATRIZ, "expected: not_satisfied", "expected: satisfied")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A17" in ids_of(achados), achados


def test_auditor_morde_url_no_contrato(repo_copy: Path, run_auditor):
    """ADR-032-A2: URL de repositório dentro do diretório do contrato é acusada — a referência
    é org/repo, nunca URL (molde genérico, ADR-008-A5)."""
    with (repo_copy / README).open("a", encoding="utf-8") as f:
        f.write("URL proibida: github.com/exemplo/alvo-especifico\n")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A2" in ids_of(achados), achados


def test_auditor_morde_fixture_com_main(repo_copy: Path, run_auditor):
    """ADR-032-A6: fixture que referencie branch main/latest é proibido por forma."""
    subs(repo_copy / FIXTURE_VALID, '"catalog_hash": "',
         '"ref_banida": "main",\n    "catalog_hash": "')
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A6" in ids_of(achados), achados


def test_auditor_morde_sem_footer(repo_copy: Path, run_auditor):
    """ADR-032-A7: a política perde o footer 'Fiscalizado por:' e a asserção acusa."""
    apagar_linha(repo_copy / POLITICA, "Fiscalizado por:")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A7" in ids_of(achados), achados


def test_auditor_morde_sem_stage(repo_copy: Path, run_auditor):
    """ADR-032-A8: tirar o artefato da etapa fecha a partição — a asserção acusa."""
    apagar_linha(repo_copy / STAGES, "harness/suite-contract/evidence-bundle")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A8" in ids_of(achados), achados


def test_auditor_morde_sem_registro_docs(repo_copy: Path, run_auditor):
    """ADR-032-A9: sem o registro em DOCS, o schema vira decoração — a asserção acusa."""
    apagar_linha(repo_copy / VALIDATE, "evidence-bundle/compatibility-matrix.yaml")
    code, achados = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-032-A9" in ids_of(achados), achados


@pytest.mark.parametrize("arquivo", [
    "harness/schemas/evidence-reference.schema.json",
    "harness/schemas/assurance-lock.schema.json",
])
def test_schemas_do_contrato_sao_validos(repo_copy: Path, arquivo: str):
    """Os schemas novos são JSON válido — um schema ilegível quebraria a travessa em silêncio."""
    import json
    doc = json.loads((repo_copy / arquivo).read_text(encoding="utf-8"))
    assert doc.get("$schema", "").startswith("https://json-schema.org/draft/2020-12")