"""Prova que a cobertura reversa morde — as quatro direções que ninguém verificava.

O teste que mais importa é test_r1_capacidade_de_alto_risco_sem_risco_reprova, porque a lacuna
que ele fecha não é hipotética: os treze primeiros riscos deste repositório eram TODOS sobre a
própria harness, e o CI ficou verde o tempo todo. Verificar que todo controle aponta para algo
real nunca diria nada sobre o que não foi declarado.

test_isencao_morta_reprova é o segundo. Uma isenção que não protege nada é pior que nenhuma: ela
consome a atenção de quem revisa e faz a cobertura parecer fechada.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

CI = Path(__file__).resolve().parent.parent.parent / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))


@pytest.fixture
def run_alignment(monkeypatch):
    def _run(root: Path, argv: list[str] | None = None) -> tuple[int, list[dict]]:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        import harness_lib
        importlib.reload(harness_lib)
        import alignment_report
        importlib.reload(alignment_report)
        code = alignment_report.main(list(argv or []) + ["--quiet"])
        laudo = root / "harness/reports/alignment-audit.json"
        achados = json.loads(laudo.read_text(encoding="utf-8"))["findings"] if laudo.exists() else []
        return code, achados

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


def _editar(root: Path, rel: str, mutate) -> None:
    p = root / rel
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    mutate(doc)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _ids(achados: list[dict]) -> set[str]:
    return {a["id"] for a in achados}


def test_baseline_esta_alinhado(repo_copy, run_alignment):
    code, achados = run_alignment(repo_copy)
    assert code == 0, [a for a in achados if a["severity"] != "info"]


# --------------------------------------------------------------------------------------
# R1–R4
# --------------------------------------------------------------------------------------

def test_r1_capacidade_de_alto_risco_sem_risco_reprova(repo_copy, run_alignment):
    """Risco reconhecido em campo e invisível na governança — a lacuna que este repositório tinha."""
    _editar(repo_copy, "business/capabilities.yaml",
            lambda d: d["capabilities"][1].update(risk_level="critical"))
    code, achados = run_alignment(repo_copy)
    assert code == 1
    assert "FIND-ALIGN-R1-CAP-CATALOG" in _ids(achados), _ids(achados)


def test_r1_aceita_isencao_declarada(repo_copy, run_alignment):
    """A trava tem que aceitar a declaração — senão empurra o time a inventar um risco de fachada."""
    _editar(repo_copy, "business/capabilities.yaml",
            lambda d: d["capabilities"][1].update(risk_level="critical"))
    _editar(repo_copy, "governance/risk-register.yaml", lambda d: d["risk_exemptions"].append({
        "ref": "CAP-CATALOG",
        "justification": "isenção injetada pelo teste para provar que a declaração explícita é "
                         "aceita e não exige inventar um risco de fachada",
    }))
    code, achados = run_alignment(repo_copy)
    assert code == 0, [a for a in achados if a["severity"] != "info"]


def test_r1_aceita_risco_que_referencia_a_capacidade(repo_copy, run_alignment):
    _editar(repo_copy, "business/capabilities.yaml",
            lambda d: d["capabilities"][1].update(risk_level="critical"))
    _editar(repo_copy, "governance/risk-register.yaml",
            lambda d: d["risks"][0].setdefault("related", []).append("CAP-CATALOG"))
    code, achados = run_alignment(repo_copy)
    assert code == 0, [a for a in achados if a["severity"] != "info"]


def test_r2_risco_aberto_sem_prazo_reprova(repo_copy, run_alignment):
    """'open' soa como trabalho em andamento — é por isso que dura para sempre sem o prazo."""
    _editar(repo_copy, "governance/risk-register.yaml",
            lambda d: d["risks"][0].update(status="open"))
    code, achados = run_alignment(repo_copy)
    assert code == 1
    assert any(i.startswith("FIND-ALIGN-R2-") for i in _ids(achados)), _ids(achados)


def test_r2_risco_aberto_com_prazo_passa(repo_copy, run_alignment):
    _editar(repo_copy, "governance/risk-register.yaml",
            lambda d: d["risks"][0].update(status="open", due="2027-01-31"))
    code, achados = run_alignment(repo_copy)
    assert code == 0, [a for a in achados if a["severity"] != "info"]


def test_r3_superficie_orfa_reprova(repo_copy, run_alignment):
    _editar(repo_copy, "design/ui-surfaces.yaml",
            lambda d: d["ui_surfaces"][0].pop("satisfies", None))
    code, achados = run_alignment(repo_copy)
    assert code == 1
    assert "FIND-ALIGN-R3-UI-PRICING-PAGE" in _ids(achados), _ids(achados)


def test_r4_componente_sem_requisito_nem_regra_reprova(repo_copy, run_alignment):
    """CMP-CATALOG é 'verified' e não implementa requisito: só a regra verificada o justifica.
    Tirando a regra, ele vira código maduro cuja razão de existir ninguém registrou."""
    _editar(repo_copy, "business/rules/catalog.yaml",
            lambda d: d["rules"][0].update(status="proposed"))
    code, achados = run_alignment(repo_copy)
    assert code == 1
    assert "FIND-ALIGN-R4-CMP-CATALOG" in _ids(achados), _ids(achados)


def test_isencao_morta_reprova(repo_copy, run_alignment):
    """Isenção que não protege nada consome a atenção de quem revisa sem cobrir ativo algum."""
    _editar(repo_copy, "governance/risk-register.yaml", lambda d: d["risk_exemptions"].append({
        "ref": "CAP-QUE-NAO-EXISTE",
        "justification": "isenção deliberadamente morta, injetada pelo teste para provar a mordida",
    }))
    code, achados = run_alignment(repo_copy)
    assert code == 1
    assert "FIND-ALIGN-EXEMPT-CAP-QUE-NAO-EXISTE" in _ids(achados), _ids(achados)


# --------------------------------------------------------------------------------------
# O artefato derivado
# --------------------------------------------------------------------------------------

def test_alignment_md_editado_a_mao_e_acusado(repo_copy, run_alignment):
    """Fonte paralela: a matriz é justamente onde alguém corrigiria o número em vez do fato."""
    p = repo_copy / "docs/alignment.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n<!-- editado à mão -->\n", encoding="utf-8")
    code, _ = run_alignment(repo_copy, ["--check"])
    assert code == 1


def test_check_nao_reescreve_o_artefato(repo_copy, run_alignment):
    """--check verifica; quem escreve é a execução sem flag. Um --check que conserta esconderia
    a divergência que ele existe para mostrar."""
    p = repo_copy / "docs/alignment.md"
    sujo = p.read_text(encoding="utf-8") + "\n<!-- editado à mão -->\n"
    p.write_text(sujo, encoding="utf-8")
    run_alignment(repo_copy, ["--check"])
    assert p.read_text(encoding="utf-8") == sujo
