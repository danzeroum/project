"""Prova que as duas travas do ADR-010 mordem: proveniência ancorada e julgamento reservado.

O teste central é test_sha_de_proveniencia_atrasado_reprova. Sem a igualdade de SHA, "este
metadado descreve o alvo" degrada em silêncio para "descrevia em algum momento" — e degrada
*parecendo* atual, porque o item continua bem-formado, com schema válido e caminho existente. É
o modo de falha que target.lock resolve uma camada abaixo, e aqui ele seria mais caro.

O segundo é test_pending_judgment_em_documento_promovido_reprova. O sentinela só é honesto se
alguém o expulsa: um campo que a máquina preenche e nenhum fiscal recusa é a definição do
'to-be-assessed' que o ADR-002 proíbe.
"""

from __future__ import annotations

import yaml

from conftest import ids_of

SHA_LOCK = "1" * 40
SHA_ANTIGO = "2" * 40
ALVO = "sintetico/alvo"


def _ler(root, rel: str) -> dict:
    return yaml.safe_load((root / rel).read_text(encoding="utf-8"))


def _gravar(root, rel: str, doc: dict) -> None:
    (root / rel).write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")


def _derivado(root, code_roots=("app",), test_roots=("provas",)) -> None:
    """Derivado ancorado com o alvo materializado e cartografado — o estado pós-ingestão."""
    doc = _ler(root, "project.yaml")
    doc["project"]["kind"] = "derived"
    doc["target"] = {"repo": ALVO, "ref": "principal", "lock_source": "target.lock",
                     "code_roots": list(code_roots), "test_roots": list(test_roots),
                     "languages": ["python"]}
    _gravar(root, "project.yaml", doc)

    lock = _ler(root, "target.lock")
    lock.update(kind="derived", target_sha=SHA_LOCK)
    _gravar(root, "target.lock", lock)

    for rel, conteudo in {
        "app/servico.py": "def executar():\n    return 1\n",
        "provas/test_servico.py": "def test_ok():\n    assert True\n",
    }.items():
        alvo = root / "workspace/target" / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")


def _componente_ingerido(sha: str = SHA_LOCK, path: str = "app/servico.py") -> dict:
    return {
        "id": "CMP-SERVICO", "kind": "domain-module", "capability": "CAP-PRICING",
        "status": "proposed", "source_paths": ["workspace/target/app/servico.py"],
        "tested_by": [], "owner": "engineering",
        "derived_from": {"repo": ALVO, "sha": sha, "path": path, "section": "executar"},
    }


def _cartografado(root, componente: dict | None = None) -> None:
    doc = _ler(root, "architecture/components.yaml")
    doc["source_of_truth"] = False
    doc["generated_from"] = "harness/pipeline/ingest.yaml#ING-03-CARTOGRAFIA"
    doc["components"] = [componente or _componente_ingerido()]
    doc["exemptions"] = [{
        "path": "workspace/target/provas/test_servico.py",
        "justification": "arquivo de teste do alvo, coberto pela raiz de teste declarada e não "
                         "por um componente — isenção injetada pelo cenário de ingestão",
    }]
    _gravar(root, "architecture/components.yaml", doc)


# --------------------------------------------------------------------------------------
# Proveniência
# --------------------------------------------------------------------------------------

def test_baseline_do_molde_esta_conforme(repo_copy, run_metadata):
    code, errors = run_metadata(repo_copy)
    assert code == 0, f"o baseline deveria estar verde, mas: {errors}"


def test_sha_de_proveniencia_atrasado_reprova(repo_copy, run_metadata):
    """O item continua bem-formado e o caminho existe — só o commit é outro. É a falha silenciosa
    que a igualdade de SHA existe para tornar barulhenta."""
    _derivado(repo_copy)
    _cartografado(repo_copy, _componente_ingerido(sha=SHA_ANTIGO))
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("derived_from.sha não casa target.lock" in e for e in errors), errors


def test_proveniencia_de_outro_alvo_reprova(repo_copy, run_metadata):
    _derivado(repo_copy)
    comp = _componente_ingerido()
    comp["derived_from"]["repo"] = "outro-owner/outro-repo"
    _cartografado(repo_copy, comp)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("não é o alvo declarado" in e for e in errors), errors


def test_proveniencia_apontando_para_arquivo_inexistente_reprova(repo_copy, run_metadata):
    """Proveniência que não resolve é trava quebrada, não trava satisfeita (ADR-006)."""
    _derivado(repo_copy)
    _cartografado(repo_copy, _componente_ingerido(path="app/nao_existe.py"))
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("não existe no alvo" in e for e in errors), errors


def test_proveniencia_no_molde_reprova(repo_copy, run_metadata):
    """Proveniência sem alvo é ficção: o molde não governa repositório algum."""
    doc = _ler(repo_copy, "architecture/components.yaml")
    doc["components"][0]["derived_from"] = {
        "repo": ALVO, "sha": SHA_LOCK, "path": "app/servico.py"}
    _gravar(repo_copy, "architecture/components.yaml", doc)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("não governa alvo algum" in e for e in errors), errors


def test_proveniencia_coerente_passa(repo_copy, run_metadata):
    """A trava tem que deixar passar o caso legítimo — senão é obstáculo, não trava."""
    _derivado(repo_copy)
    _cartografado(repo_copy)
    _, errors = run_metadata(repo_copy)
    assert not [e for e in errors if "proveniência" in e], errors


# --------------------------------------------------------------------------------------
# Julgamento reservado
# --------------------------------------------------------------------------------------

def test_pending_judgment_em_documento_promovido_reprova(repo_copy, run_metadata):
    """Promover é substituir o sentinela, não redeclarar o cabeçalho com ele dentro."""
    doc = _ler(repo_copy, "business/capabilities.yaml")
    doc["capabilities"][0]["risk_level"] = "pending_judgment"
    _gravar(repo_copy, "business/capabilities.yaml", doc)   # segue source_of_truth: true
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("julgamento" in e and "pending_judgment" in e for e in errors), errors


def test_pending_judgment_em_documento_derivado_passa(repo_copy, run_metadata):
    """O sentinela é legítimo enquanto o documento se declara derivado — é para isso que existe."""
    doc = _ler(repo_copy, "business/capabilities.yaml")
    doc["source_of_truth"] = False
    doc["generated_from"] = "harness/pipeline/ingest.yaml#ING-04-NEGOCIO"
    doc["capabilities"][0]["risk_level"] = "pending_judgment"
    _gravar(repo_copy, "business/capabilities.yaml", doc)
    _, errors = run_metadata(repo_copy)
    assert not [e for e in errors if "julgamento" in e], errors


# --------------------------------------------------------------------------------------
# O pipeline
# --------------------------------------------------------------------------------------

def _editar_fase(root, mutate) -> None:
    doc = _ler(root, "harness/pipeline/ingest.yaml")
    mutate(doc["phases"][0])
    _gravar(root, "harness/pipeline/ingest.yaml", doc)


def test_fase_com_fiscal_inexistente_reprova(repo_copy, run_auditor):
    """Fase de ingestão sem fiscal é metadado escrito por máquina que ninguém confere."""
    _editar_fase(repo_copy, lambda f: f["fiscal"].update(symbol="funcao_que_nao_existe"))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-INGEST-FISCAL-ING-01-INVENTARIO" in ids_of(findings), ids_of(findings)


def test_fase_com_agente_sem_contrato_reprova(repo_copy, run_auditor):
    _editar_fase(repo_copy, lambda f: f.update(agent="agente-inexistente"))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-INGEST-AGENT-ING-01-INVENTARIO" in ids_of(findings), ids_of(findings)


def test_fase_escrevendo_no_alvo_reprova(repo_copy, run_auditor):
    """A ingestão lê o alvo e escreve no derivado. O contrário faria o vigia hospedar-se no
    vigiado — a mesma razão pela qual os metadados não moram no repositório auditado."""
    _editar_fase(repo_copy, lambda f: f["outputs"].append("workspace/target/METADATA.md"))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-INGEST-WRITE-ING-01-INVENTARIO" in ids_of(findings), ids_of(findings)


def test_ordem_duplicada_reprova(repo_copy, run_auditor):
    doc = _ler(repo_copy, "harness/pipeline/ingest.yaml")
    doc["phases"][1]["order"] = doc["phases"][0]["order"]
    _gravar(repo_copy, "harness/pipeline/ingest.yaml", doc)
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(i.startswith("FIND-INGEST-ORDER-") for i in ids_of(findings)), ids_of(findings)
