"""Prova que o fiscal de LGPD morde — e que ele NÃO acusa o repositório limpo.

test_baseline_sem_falso_positivo é o contrapeso: um léxico agressivo demais transforma todo
identificador em achado, o time aprende a ignorar o fiscal, e a trava morre por ruído em vez
de morrer por omissão. Os dois modos de falha custam a mesma coisa.
"""

from __future__ import annotations

import json

import pytest
import yaml
from jsonschema import Draft202012Validator

from conftest import ids_of, origins_of

REPO_SCHEMAS = "harness/schemas"


def _write_yaml(path, doc):
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _refresh_fingerprint(repo, run_auditor):
    """Recalcula o fingerprint na cópia — senão todo teste falharia por judgment_stale."""
    import importlib
    import io
    import contextlib
    import os
    os.environ["HARNESS_REPO_ROOT"] = str(repo)
    import harness_lib
    importlib.reload(harness_lib)
    import audit_lgpd
    importlib.reload(audit_lgpd)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit_lgpd.main(["--print-fingerprint"])
    fp = buf.getvalue().strip()
    p = repo / "governance/privacy-review.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["review"]["scope_fingerprint"] = fp
    _write_yaml(p, doc)
    return fp


def test_baseline_sem_falso_positivo(repo_copy, run_auditor):
    """O domínio de exemplo (sku, preco_centavos, quantidade) não tem dado pessoal."""
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 0, f"o baseline deveria estar verde, mas: {findings}"
    assert "lgpd_scan" not in origins_of(findings)


def test_pii_shadow_morde(repo_copy, run_auditor):
    (repo_copy / "src/project/ports.py").write_text(
        (repo_copy / "src/project/ports.py").read_text(encoding="utf-8")
        + "\n\nclass Cliente:\n    cpf: str\n    data_nascimento: str\n",
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 1
    scan = [f for f in findings if f["origin"] == "lgpd_scan"]
    assert scan, "campo com forma de CPF fora do inventário deveria ser achado"
    assert all(f["lgpd_article"].startswith("Art.") for f in scan), \
        "achado de LGPD sem artigo é opinião, não parecer"
    assert all("pbd_principle" in f for f in scan)


def test_pii_sensivel_e_severidade_maior(repo_copy, run_auditor):
    (repo_copy / "src/project/ports.py").write_text(
        (repo_copy / "src/project/ports.py").read_text(encoding="utf-8")
        + "\n\nclass Paciente:\n    diagnostico: str\n",
        encoding="utf-8",
    )
    _, findings = run_auditor("audit_lgpd", repo_copy)
    scan = [f for f in findings if f["origin"] == "lgpd_scan"]
    assert any(f["severity"] == "high" for f in scan)


def test_token_ambiguo_nao_gera_falso_positivo(repo_copy, run_auditor):
    """'transformacao_digital' não é biometria; 'microphone' não é telefone."""
    (repo_copy / "src/project/ports.py").write_text(
        (repo_copy / "src/project/ports.py").read_text(encoding="utf-8")
        + "\n\nclass Config:\n    transformacao_digital: bool\n    microphone_gain: int\n",
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert "lgpd_scan" not in origins_of(findings), \
        f"casamento por substring voltou: {[f['summary'] for f in findings]}"
    assert code == 0


def test_judgment_stale_morde(repo_copy, run_auditor):
    p = repo_copy / "governance/data-inventory.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "\n# altera o escopo declarado\n",
                 encoding="utf-8")
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 1
    assert "FIND-JUDGMENT-STALE" in ids_of(findings)


def test_campo_inventariado_exige_ripd_completo(repo_copy, run_auditor):
    p = repo_copy / "governance/data-inventory.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["controller"] = {"role": "controller", "dpo_contact": "dpo@example.invalid"}
    doc["purposes"] = [{"id": "PURP-001", "description": "Emitir nota fiscal do pedido.",
                        "legal_basis": "obrigacao_legal"}]
    doc["fields"] = [{
        "id": "PD-001", "name": "cpf_comprador", "classification": "pessoal",
        "purpose": "PURP-001", "legal_basis": "obrigacao_legal",
        "owning_component": "CMP-PRICING",
        "retention": {"policy": "obrigacao_legal", "legal_ref": "Art. 195 CTN"},
        "locations": ["src/project/pricing.py"],
    }]
    _write_yaml(p, doc)
    _refresh_fingerprint(repo_copy, run_auditor)

    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 1
    ids = ids_of(findings)
    # kind errado (parecer onde o estado exige RIPD), papel divergente e direitos sem endpoint.
    assert "FIND-JUDGMENT-KIND" in ids
    assert "FIND-ROLE-MISMATCH" in ids
    assert any(i.startswith("FIND-RIGHT-") for i in ids)


def test_direito_sem_endpoint_e_achado(repo_copy, run_auditor):
    p = repo_copy / "governance/data-inventory.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["fields"] = [{
        "id": "PD-001", "name": "email_contato", "classification": "pessoal",
        "purpose": "PURP-001", "legal_basis": "execucao_contrato",
        "owning_component": "CMP-CATALOG",
        "retention": {"policy": "prazo_definido", "max_days": 365},
        "locations": ["src/project/ports.py"],
    }]
    _write_yaml(p, doc)
    _refresh_fingerprint(repo_copy, run_auditor)
    _, findings = run_auditor("audit_lgpd", repo_copy)
    rights = [f for f in findings if f["id"].startswith("FIND-RIGHT-")]
    assert len(rights) == 4, "os quatro direitos do Art. 18 precisam de endpoint"
    assert all(f["lgpd_article"].startswith("Art. 18") for f in rights)


def test_exclusao_morta_e_achado(repo_copy, run_auditor):
    p = repo_copy / "governance/data-inventory.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["scan"]["exclusions"] = [{
        "path_glob": "src/project/pricing.py", "token": "cpf",
        "justification": "Exclusão que não suprime nada — deve ser sinalizada como morta.",
    }]
    _write_yaml(p, doc)
    _refresh_fingerprint(repo_copy, run_auditor)
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 1
    assert any(i.startswith("FIND-EXCLUSION-STALE-") for i in ids_of(findings))


# --------------------------------------------------------------------------------------
# Travas ESTRUTURAIS: a violação não pode ser escrita, então não precisa ser detectada.
# --------------------------------------------------------------------------------------

def _inventory_validator():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    schema = json.loads(
        (root / REPO_SCHEMAS / "data-inventory.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _base_inventory(**overrides):
    doc = {
        "schema_version": "1.0", "metadata_version": "1.0",
        "source_of_truth": True, "generated_from": None,
        "controller": {"role": "none"}, "purposes": [], "fields": [],
        "subject_rights": {"confirmation": None, "access": None,
                           "deletion": None, "portability": None},
        "scan": {"exclusions": []},
    }
    doc.update(overrides)
    return doc


@pytest.mark.parametrize("base_legal", ["legitimo_interesse", "protecao_credito"])
def test_sensivel_com_base_do_art_7_e_recusado_pelo_schema(base_legal):
    """Art. 11 não admite legítimo interesse nem proteção ao crédito para dado sensível."""
    doc = _base_inventory(
        controller={"role": "controller", "dpo_contact": "dpo@example.invalid"},
        fields=[{
            "id": "PD-001", "name": "diagnostico", "classification": "sensivel",
            "art_11_category": "saude", "purpose": "PURP-001", "legal_basis": base_legal,
            "owning_component": "CMP-PRICING", "masked_at_rest": True,
            "retention": {"policy": "prazo_definido", "max_days": 30},
            "locations": ["src/project/ports.py"],
        }],
    )
    errors = list(_inventory_validator().iter_errors(doc))
    assert errors, f"o schema deveria recusar dado sensível com base legal '{base_legal}'"


def test_papel_de_tratador_exige_encarregado():
    """Art. 41: papel declarado sem contato do encarregado é papel de fachada."""
    doc = _base_inventory(controller={"role": "controller"})
    assert list(_inventory_validator().iter_errors(doc))


def test_retencao_sem_prazo_e_recusada():
    doc = _base_inventory(fields=[{
        "id": "PD-001", "name": "email", "classification": "pessoal",
        "purpose": "PURP-001", "legal_basis": "consentimento",
        "owning_component": "CMP-CATALOG",
        "retention": {"policy": "prazo_definido"},  # sem max_days
        "locations": ["src/project/ports.py"],
    }])
    assert list(_inventory_validator().iter_errors(doc))


def test_lgpd_relevance_livre_e_recusado():
    """'to-be-assessed' era texto livre que nenhum fiscal reprovava. Agora é enum."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    schema = json.loads(
        (root / REPO_SCHEMAS / "project.schema.json").read_text(encoding="utf-8"))
    doc = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    doc["classification"]["lgpd_relevance"] = "to-be-assessed"
    assert list(Draft202012Validator(schema).iter_errors(doc))


# --------------------------------------------------------------------------------------
# A trava do próprio laudo: um fiscal que emite achado de LGPD sem artigo citado seria a
# versão executável de "markdown que não morde". O if/then existia no schema desde o início,
# mas nada provava que emit_report o aplicasse — trava sem prova é trava por enquanto.
# --------------------------------------------------------------------------------------

def _report_com(finding: dict) -> dict:
    return {
        "schema_version": "1.0",
        "provenance": {
            "auditor": "ci/audit_lgpd.py", "auditor_version": "1.0",
            "repository": "danzeroum/project", "commit": "0" * 40,
            "generated_at": "2026-08-04T00:00:00+00:00", "stages_covered": ["STAGE-CODE"],
        },
        "result": "findings",
        "summary": {"total": 1, "by_severity": {"medium": 1}},
        "findings": [finding],
    }


def test_laudo_lgpd_sem_artigo_sai_2_e_nao_escreve(repo_copy, monkeypatch):
    import importlib
    monkeypatch.setenv("HARNESS_REPO_ROOT", str(repo_copy))
    import harness_lib
    importlib.reload(harness_lib)

    destino = "harness/reports/teste-laudo-invalido.json"
    ruim = _report_com({
        "id": "FIND-X", "origin": "lgpd_scan", "severity": "medium",
        "summary": "achado sem artigo citado",
        # falta lgpd_article e pbd_principle
    })
    with pytest.raises(harness_lib.HarnessError):
        harness_lib.emit_report(destino, ruim)
    assert not (repo_copy / destino).exists(), \
        "nenhum arquivo pode ser escrito quando o laudo não satisfaz o próprio contrato"

    bom = _report_com({
        "id": "FIND-X", "origin": "lgpd_scan", "severity": "medium",
        "summary": "achado com artigo citado",
        "lgpd_article": "Art. 37", "pbd_principle": "Privacidade no Design",
    })
    harness_lib.emit_report(destino, bom)
    assert (repo_copy / destino).exists()


def test_upload_sem_retention_days_e_achado(repo_copy, run_auditor):
    """L9 — a retenção declarada precisa alcançar a evidência que sobrevive ao runner."""
    p = repo_copy / ".github/workflows/governance.yml"
    p.write_text(p.read_text(encoding="utf-8").replace("          retention-days: 90\n", ""),
                 encoding="utf-8")
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 1
    ret = [f for f in findings if f["origin"] == "lgpd_retention"]
    assert ret, "upload de harness/reports/ sem retention-days deveria ser achado"
    assert all(f["lgpd_article"].startswith("Art.") for f in ret)


def test_retention_divergente_da_declarada_e_achado(repo_copy, run_auditor):
    p = repo_copy / ".github/workflows/governance.yml"
    p.write_text(p.read_text(encoding="utf-8").replace("retention-days: 90", "retention-days: 400"),
                 encoding="utf-8")
    code, findings = run_auditor("audit_lgpd", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-ARTIFACT-RETENTION-MISMATCH") for f in findings)
