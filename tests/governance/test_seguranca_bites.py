"""Prova que o departamento de segurança morde nas duas frentes.

O teste central é test_dependencia_declarada_e_nao_inventariada_reprova: é a direção reversa da
Fase E aplicada a supply chain. A régua já estava pinada, mas o pin cobre UMA dependência de um
universo inteiro — acrescentar biblioteca sem passar pelo inventário era, até aqui, invisível.

O segundo é test_ameaca_sem_residual_rastreavel_reprova. Uma ameaça catalogada e sem tratamento é
o 'to-be-assessed' do ADR-002 vestido de diligência: parece trabalho de segurança, enche um
documento e não obriga a nada.
"""

from __future__ import annotations

import yaml


def _ler(root, rel: str) -> dict:
    return yaml.safe_load((root / rel).read_text(encoding="utf-8"))


def _gravar(root, rel: str, doc: dict) -> None:
    (root / rel).write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")


def test_baseline_esta_conforme(repo_copy, run_metadata):
    code, errors = run_metadata(repo_copy)
    assert code == 0, f"o baseline deveria estar verde, mas: {errors}"


# --------------------------------------------------------------------------------------
# Modelo de ameaças
# --------------------------------------------------------------------------------------

def test_ameaca_contra_componente_inexistente_reprova(repo_copy, run_metadata):
    """Trava que não encontra o que vigiar está quebrada, não satisfeita (ADR-006)."""
    _gravar(repo_copy, "security/threat-model.yaml", {
        **(d := _ler(repo_copy, "security/threat-model.yaml")),
        "threats": [{**d["threats"][0], "target": "CMP-QUE-NAO-EXISTE"}],
    })
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("target CMP-QUE-NAO-EXISTE" in e for e in errors), errors


def test_ameaca_sem_residual_rastreavel_reprova(repo_copy, run_metadata):
    """Sem residual ancorado, a ameaça não herda dono nem prazo — vira ilha."""
    d = _ler(repo_copy, "security/threat-model.yaml")
    d["threats"][0]["residual_risk"] = "RISK-QUE-NAO-EXISTE"
    _gravar(repo_copy, "security/threat-model.yaml", d)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("residual_risk" in e and "limbo" in e for e in errors), errors


def test_ameaca_sem_mitigacao_e_estruturalmente_impossivel(repo_copy, run_metadata):
    """minItems: 1 — o schema recusa antes de o fiscal precisar reclamar."""
    d = _ler(repo_copy, "security/threat-model.yaml")
    d["threats"][0]["mitigations"] = []
    _gravar(repo_copy, "security/threat-model.yaml", d)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("estrutural" in e and "mitigations" in e for e in errors), errors


def test_mitigacao_apontando_para_arquivo_inexistente_reprova(repo_copy, run_metadata):
    d = _ler(repo_copy, "security/threat-model.yaml")
    d["threats"][0]["mitigations"][0] = {"kind": "local_path", "ref": "nao/existe.md"}
    _gravar(repo_copy, "security/threat-model.yaml", d)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("mitigação local_path inexistente" in e for e in errors), errors


def test_severidade_pendente_em_documento_promovido_reprova(repo_copy, run_metadata):
    """Nenhuma ferramenta decide gravidade de ameaça — e o sentinela não sobrevive à promoção."""
    d = _ler(repo_copy, "security/threat-model.yaml")
    d["threats"][0]["severity"] = "pending_judgment"
    _gravar(repo_copy, "security/threat-model.yaml", d)   # segue source_of_truth: true
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("julgamento" in e and "pending_judgment" in e for e in errors), errors


# --------------------------------------------------------------------------------------
# Inventário de dependências
# --------------------------------------------------------------------------------------

def test_dependencia_declarada_e_nao_inventariada_reprova(repo_copy, run_metadata):
    """Acrescentar biblioteca sem passar pelo inventário era invisível até aqui."""
    p = repo_copy / "pyproject.toml"
    p.write_text(p.read_text(encoding="utf-8").replace(
        '    "pyyaml>=6",\n', '    "pyyaml>=6",\n    "requests>=2",\n'), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("'requests'" in e and "inventário" in e for e in errors), errors


def test_dependencia_inventariada_e_nao_declarada_reprova(repo_copy, run_metadata):
    """Entrada morta faz o inventário parecer mais completo do que é."""
    d = _ler(repo_copy, "security/dependencies.yaml")
    d["dependencies"].append({
        "name": "biblioteca-fantasma", "scope": "dev", "declared_in": "pyproject.toml",
        "pin_kind": "range", "owner": "technical_owner",
        "purpose": "entrada morta injetada pelo teste para provar a mordida",
    })
    _gravar(repo_copy, "security/dependencies.yaml", d)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("não é declarada em lugar nenhum" in e for e in errors), errors


def test_declared_in_divergente_reprova(repo_copy, run_metadata):
    d = _ler(repo_copy, "security/dependencies.yaml")
    for dep in d["dependencies"]:
        if dep["name"] == "pytest":
            dep["declared_in"] = "requirements-qa.txt"
    _gravar(repo_copy, "security/dependencies.yaml", d)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("'pytest'" in e for e in errors), errors


def test_inventario_le_declaracao_e_nao_ambiente(repo_copy, run_metadata):
    """O fiscal não consulta site-packages: um inventário conferido contra o que está instalado
    passaria ou reprovaria conforme o computador de quem roda."""
    import sys
    assert "requests" not in sys.modules
    code, errors = run_metadata(repo_copy)
    # pytest/jsonschema/pyyaml estão instalados neste ambiente e inventariados; nada além disso
    # entra no veredito, e é o que mantém o resultado reprodutível fora desta máquina.
    assert code == 0, errors


# --------------------------------------------------------------------------------------
# CP-019: a ameaça ao harness ganha alvo verdadeiro — e alvo inexistente segue reprovando
# --------------------------------------------------------------------------------------

def _threats(root):
    import yaml
    p = root / "security/threat-model.yaml"
    return p, yaml.safe_load(p.read_text(encoding="utf-8"))


def _gravar_threats(p, doc):
    import yaml
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_ameaca_pode_ter_etapa_como_alvo(repo_copy, run_metadata):
    """O que a ameaça ao harness de fato ameaça é a máquina de governar, não um componente de
    negócio. Antes do CP-019 ela só passava apontando para um CMP-* arbitrário que existisse —
    o fiscal satisfeito sem que a declaração dissesse nada verdadeiro."""
    p, doc = _threats(repo_copy)
    doc["threats"][0]["target"] = "STAGE-CI-HARNESS"
    _gravar_threats(p, doc)
    code, errors = run_metadata(repo_copy)
    assert not [e for e in errors if "[ameaça]" in e], errors
    assert code == 0, errors


def test_alvo_de_etapa_inexistente_reprova(repo_copy, run_metadata):
    """A namespace nova não é passe livre: ela resolve contra harness/stages.yaml como as outras
    resolvem contra components, interfaces e ui-surfaces."""
    p, doc = _threats(repo_copy)
    doc["threats"][0]["target"] = "STAGE-QUE-NAO-EXISTE"
    _gravar_threats(p, doc)
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("[ameaça]" in e and "STAGE-QUE-NAO-EXISTE" in e for e in errors), errors
