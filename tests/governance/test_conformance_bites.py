"""Prova que o fiscal de conformidade morde — uma injeção por espécie de asserção.

O teste mais importante é test_glob_vazio_e_achado: uma asserção cujo alvo não existe "passa"
por vacuidade em qualquer implementação ingênua, e passar por vacuidade é o modo de falha que o
ADR-002 descreve, reencarnado dentro do mecanismo que deveria impedi-lo.
"""

from __future__ import annotations

import yaml

from conftest import ids_of, origins_of


def _edit_index(root, mutate):
    p = root / "architecture/adr/index.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    mutate(doc)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _assertion(doc, aid):
    for adr in doc["adrs"]:
        for a in adr.get("assertions", []):
            if a["id"] == aid:
                return a
    raise AssertionError(f"asserção {aid} não encontrada")


def test_baseline_esta_conforme(repo_copy, run_auditor):
    code, findings = run_auditor("audit_governance", repo_copy)
    blocking = [f for f in findings if f["severity"] != "info"]
    assert code == 0, f"o baseline deveria estar verde, mas: {blocking}"


def test_import_forbidden_morde(repo_copy, run_auditor):
    (repo_copy / "src/project/pricing.py").write_text(
        (repo_copy / "src/project/pricing.py").read_text(encoding="utf-8")
        + "\nfrom project.ports import CatalogoEmMemoria  # injetado\n",
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-005-A2" in ids_of(findings)


def test_import_forbidden_pega_uso_por_atributo(repo_copy, run_auditor):
    """import project.ports + project.ports.CatalogoEmMemoria() — a 2ª passada do AST."""
    (repo_copy / "src/project/pricing.py").write_text(
        (repo_copy / "src/project/pricing.py").read_text(encoding="utf-8")
        + "\nimport project.ports\n\n\ndef _fabrica():\n"
        "    return project.ports.CatalogoEmMemoria({})\n",
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-005-A2" in ids_of(findings)


def test_import_relativo_resolve_sem_achado(repo_copy, run_auditor):
    """from .ports import CatalogoProdutos satisfaz import_required (level > 0)."""
    src = (repo_copy / "src/project/pricing.py").read_text(encoding="utf-8")
    src = src.replace("from project.ports import CatalogoProdutos",
                      "from .ports import CatalogoProdutos")
    (repo_copy / "src/project/pricing.py").write_text(src, encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert "FIND-ADR-005-A1" not in ids_of(findings), \
        "import relativo deveria satisfazer a dependência da porta"
    assert code == 0


def test_import_required_morde(repo_copy, run_auditor):
    src = (repo_copy / "src/project/pricing.py").read_text(encoding="utf-8")
    src = src.replace("from project.ports import CatalogoProdutos", "CatalogoProdutos = object")
    (repo_copy / "src/project/pricing.py").write_text(src, encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-005-A1" in ids_of(findings)


def test_path_absent_morde(repo_copy, run_auditor):
    (repo_copy / "checks").mkdir()
    (repo_copy / "checks/local.py").write_text("# régua copiada\n", encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-001-A1" in ids_of(findings)


def test_file_lacks_morde(repo_copy, run_auditor):
    (repo_copy / "requirements-qa.txt").write_text("webqa-suite>=1.0.0\n", encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-001-A4" in ids_of(findings)


def test_file_matches_morde(repo_copy, run_auditor):
    """Tirar um dos três alvos da recusa de régua copiada é desligar parte da trava."""
    p = repo_copy / ".github/workflows/qa.yml"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "for alvo in webqa checks data/caminhos-sensiveis.yaml",
            "for alvo in webqa checks",
        ),
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-001-A3" in ids_of(findings)


def test_schema_lock_morde_quando_valor_muda(repo_copy, run_auditor):
    """A mutação é ESTRUTURAL, não textual, e a distinção custou um vermelho para aparecer.

    Antes, este teste trocava a string '"human_approval_required": { "const": true }' pela versão
    com false. Funcionava enquanto o schema estivesse formatado exatamente assim — e no dia em que
    o arquivo foi reindentado, o replace virou no-op silencioso: a mutação não acontecia, o fiscal
    passava, e o teste declarava que a trava mordia sem nunca a ter testado. Um teste de mordida
    que depende de formatação é um teste que deixa de morder sem falhar, que é o pior modo de
    falha possível nesta suíte.
    """
    import json

    p = repo_copy / "harness/schemas/change-proposal.schema.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    alvo = doc["allOf"][0]["then"]["properties"]["proposal"]["properties"]
    alvo["human_approval_required"]["const"] = False
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-004-A1" in ids_of(findings)


def test_schema_lock_morde_quando_ponteiro_some(repo_copy, run_auditor):
    """Ponteiro que não resolve é ACHADO (a trava sumiu), nunca exceção que derruba o fiscal."""
    import json
    p = repo_copy / "harness/schemas/change-proposal.schema.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    del doc["allOf"]
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert {"FIND-ADR-004-A1", "FIND-ADR-004-A2"} <= ids_of(findings)


def test_glob_vazio_e_achado(repo_copy, run_auditor):
    """Asserção vácua não passa. É a trava que protege todas as outras."""
    _edit_index(repo_copy, lambda d: _assertion(d, "ADR-005-A2").__setitem__(
        "module_glob", "src/project/modulo_que_nao_existe.py"))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-005-A2-UNRESOLVABLE" in ids_of(findings)


def test_adr_aceito_sem_assercao_e_achado(repo_copy, run_auditor):
    _edit_index(repo_copy, lambda d: d["adrs"][4].__setitem__("assertions", []))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-005-NO-ASSERTIONS" in ids_of(findings)
    assert "adr_meta" in origins_of(findings)


def test_fiscal_renomeado_e_achado(repo_copy, run_auditor):
    """Auto-referência só é honesta com prova externa: renomear o fiscal precisa reprovar."""
    p = repo_copy / "ci/audit_governance.py"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "def check_adr_conformance(", "def check_adr_conformance_RENAMED("),
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f.get("stage") == "STAGE-DECISIONS" for f in findings)


def test_etapa_sem_fiscal_e_achado(repo_copy, run_auditor):
    p = repo_copy / "harness/stages.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["stages"][0]["enforced_by"] = [
        {"kind": "schema", "ref": "harness/schemas/nao-existe.json"}
    ]
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-STAGE-VISION-UNENFORCED" in ids_of(findings)


def test_simbolo_inexistente_em_ci_script_e_achado(repo_copy, run_auditor):
    p = repo_copy / "harness/stages.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["stages"][0]["enforced_by"][1]["symbol"] = "funcao_que_nao_existe"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any("funcao_que_nao_existe" in f["summary"] for f in findings)


def test_arquivo_fora_de_etapa_e_achado(repo_copy, run_auditor):
    (repo_copy / "novo").mkdir()
    (repo_copy / "novo/foo.py").write_text("x = 1\n", encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-UNCOVERED-NOVO-FOO-PY" in ids_of(findings)


def test_politica_sem_fiscal_e_achado(repo_copy, run_auditor):
    p = repo_copy / "harness/policies/lgpd.md"
    text = p.read_text(encoding="utf-8")
    p.write_text(text[: text.index("Fiscalizado por:")], encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-POLICY-LGPD-NO-POINTER" in ids_of(findings)


def test_codeowners_ausente_e_achado(repo_copy, run_auditor):
    (repo_copy / ".github/CODEOWNERS").unlink()
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-CODEOWNERS-MISSING" in ids_of(findings)


def test_risco_sem_dono_e_achado(repo_copy, run_auditor):
    p = repo_copy / "project.yaml"
    p.write_text(
        p.read_text(encoding="utf-8").replace('security_owner: "@danzeroum"',
                                              'security_owner: "unassigned"'),
        encoding="utf-8",
    )
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].endswith("-OWNER-UNASSIGNED") for f in findings)


def test_kind_sem_implementacao_sai_2(repo_copy, run_auditor):
    """Schema e código não podem divergir em silêncio.

    Um kind declarado no índice sem função registrada em KINDS é ERRO de fiscalização (exit 2),
    nunca achado e muito menos silêncio: se fosse ignorado, bastaria escrever um kind inventado
    para que a asserção deixasse de ser executada sem que nada aparecesse.
    """
    _edit_index(repo_copy, lambda d: _assertion(d, "ADR-005-A2").__setitem__(
        "kind", "kind_que_nao_existe"))
    code, _ = run_auditor("audit_governance", repo_copy)
    assert code == 2
