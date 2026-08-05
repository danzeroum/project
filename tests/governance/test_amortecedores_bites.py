"""Mordidas dos três amortecedores de mudança (CP-029 / ADR-019).

Cada teste usa a MUTAÇÃO CANÔNICA declarada na CP, e essa escolha é o ponto: são as mutações que a
prova de fogo 4 (§12) vai exercitar, então testá-las aqui é testar a mesma coisa que o CI vai
testar, e não uma aproximação dela.

Os pares positivos importam mais aqui do que em qualquer outro fiscal desta casa. O amortecedor
(ii) existe justamente para DEIXAR PASSAR o item em transição: um gate de maturidade que reprovasse
`proposed` fecharia a saída honesta, e a única forma de ficar verde durante um pivô voltaria a ser
mentir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import audit_governance as ag  # noqa: E402


# --------------------------------------------------------------------------------------
# (i) Arestas por ID, não por caminho
# --------------------------------------------------------------------------------------

def test_referencia_por_caminho_reprova(repo_copy: Path, run_auditor):
    """A mutação canônica da CP-029: trocar CAP-001 por um caminho de arquivo num campo `satisfies`.

    Rodada sobre um campo REAL do repositório (`ui_surfaces[].satisfies`), não sobre um arquivo
    inventado: a trava precisa morder onde os dados moram.
    """
    caminho = repo_copy / "design/ui-surfaces.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["ui_surfaces"][0]["satisfies"] = ["business/requirements/backlog.yaml"]
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-REF-PATH") for f in findings), [f["id"] for f in findings]


def test_referencia_por_id_valido_passa(repo_copy: Path, run_auditor):
    """O par positivo: o repositório como está não produz achado de aresta."""
    code, findings = run_auditor("audit_governance", repo_copy)
    assert not [f for f in findings if f["origin"] == "change_buffer"], findings


def test_schema_novo_com_campo_de_referencia_frouxo_reprova(repo_copy: Path, run_auditor):
    """A garantia que os dados sozinhos não dão.

    Os schemas de hoje já travam padrão de ID nos campos que existem — o valor desta asserção é
    cobrir os campos que AINDA NÃO foram escritos. Um schema novo com `satisfies` de string livre
    passava antes desta CP; a partir dela, não.
    """
    novo = repo_copy / "harness/schemas/exemplo-frouxo.schema.json"
    novo.write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"satisfies": {"type": "array", "items": {"type": "string"}}},
    }, indent=2), encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-REF-BY-ID") for f in findings), [f["id"] for f in findings]


def test_campo_de_caminho_nao_e_acusado(repo_copy: Path, run_auditor):
    """`verified_by` e `source_paths` SÃO caminhos por desenho (ADR-009).

    Tratá-los como campos de ID inverteria a decisão — e um fiscal que acusa o legítimo é desligado
    por quem tem trabalho a fazer, que é o pior desfecho possível para uma trava.
    """
    code, findings = run_auditor("audit_governance", repo_copy)
    acusados = [f for f in findings
                if f["origin"] == "change_buffer" and "verified_by" in f.get("summary", "")]
    assert not acusados, acusados


# --------------------------------------------------------------------------------------
# (ii) Maturidade permite transição honesta
# --------------------------------------------------------------------------------------

def test_verificado_sem_teste_reprova(repo_copy: Path, run_auditor):
    """Mutação canônica: declarar maturidade concreta sem a evidência que ela afirma existir."""
    caminho = repo_copy / "business/capabilities.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["capabilities"][0]["test_paths"] = []
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-MATURITY") for f in findings), [f["id"] for f in findings]


def test_proposed_sem_codigo_passa(repo_copy: Path, run_auditor):
    """O par positivo, e é a metade que costuma ser esquecida.

    Rebaixar para `proposed` durante um pivô é a saída HONESTA: o repositório fica verde dizendo
    "em transição" em vez de vermelho por semanas ou verde mentindo. Se este teste falhar, alguém
    fechou essa saída — e a única forma de ficar verde durante uma cascata volta a ser mentir.
    """
    caminho = repo_copy / "business/capabilities.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["capabilities"][0]["status"] = "proposed"
    doc["capabilities"][0]["source_paths"] = []
    doc["capabilities"][0]["test_paths"] = []
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    _, findings = run_auditor("audit_governance", repo_copy)
    maturidade = [f for f in findings if f["id"].startswith("FIND-MATURITY")]
    assert not maturidade, maturidade


# --------------------------------------------------------------------------------------
# (iii) Fonte de verdade se edita com revisão; derivado se regenera sem licença
# --------------------------------------------------------------------------------------

def test_artefato_derivado_sem_cabecalho_reprova(repo_copy: Path, run_auditor):
    """Mutação canônica: um derivado que não se anuncia como derivado.

    Sem o cabeçalho, a edição manual acontece de boa-fé e o `--check` do CI a contradiz depois, na
    hora mais cara.
    """
    caminho = repo_copy / "docs/alignment.md"
    texto = caminho.read_text(encoding="utf-8")
    caminho.write_text(texto.replace("<!-- GENERATED: não editar; rodar ci/alignment_report.py -->",
                                     "# um título qualquer"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-DERIVED-NO-HEADER") for f in findings), \
        [f["id"] for f in findings]


def test_cabecalho_apontando_para_script_errado_reprova(repo_copy: Path, run_auditor):
    """O cabeçalho não é decoração: ele manda o leitor a um comando. Errado, manda ao lugar errado."""
    caminho = repo_copy / "docs/alignment.md"
    texto = caminho.read_text(encoding="utf-8")
    caminho.write_text(texto.replace("rodar ci/alignment_report.py",
                                     "rodar ci/generate_graph.py"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-DERIVED-WRONG-SCRIPT") for f in findings), \
        [f["id"] for f in findings]


def test_geradores_sao_derivados_do_diretorio_nao_de_lista():
    """A lição do CP-020 aplicada a esta CP.

    Se a lista fosse mantida à mão, `ci/alignment_report.py` estaria fora dela — ele não casa o
    glob `generate_*.py` com que esta regra foi originalmente enunciada. O fiscal descobriu isso
    sozinho justamente por derivar do diretório real.
    """
    mapa = ag.geradores_declarados()
    assert mapa.get("docs/alignment.md") == "ci/alignment_report.py"
    assert mapa.get("docs/metadata-graph.md") == "ci/generate_graph.py"


def test_gerador_novo_nasce_coberto(repo_copy: Path, run_auditor):
    """Um script novo que declara escrever em docs/ entra na cobertura sem ninguém o registrar."""
    (repo_copy / "ci/generate_exemplo.py").write_text(
        'DOC = "docs/exemplo-derivado.md"\n', encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-DERIVED-MISSING") for f in findings), \
        [f["id"] for f in findings]


# --------------------------------------------------------------------------------------
# Mutação de pivô (Adendo A2, acréscimo à prova de fogo 4)
# --------------------------------------------------------------------------------------

def test_pivo_sem_cascata_completa_reprova(repo_copy: Path, run_auditor, run_metadata):
    """Alterar a semântica de uma CAP raiz sem executar a cascata deixa dependentes órfãos.

    É a prova de que o vermelho É o mapa: o fiscal não conserta nada, mas enumera exatamente quem
    ficou pendurado — que é a informação de que quem executa a cascata precisa.
    """
    caminho = repo_copy / "business/capabilities.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    removida = doc["capabilities"].pop(0)["id"]
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    code, erros = run_metadata(repo_copy)
    assert code == 1
    orfaos = [e for e in erros if removida in e]
    assert orfaos, f"nenhum dependente de {removida} foi apontado: {erros}"


def test_pivo_com_estados_proposed_passa(repo_copy: Path, run_auditor):
    """O caminho verde-honesto do mesmo pivô: rebaixar em vez de remover.

    Rebaixar mantém as arestas resolvendo (nada some) e isenta de código e teste (nada mente). É a
    razão de o amortecedor (ii) existir, e este teste é o que impede alguém de fechá-lo.
    """
    caminho = repo_copy / "business/capabilities.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    for cap in doc["capabilities"]:
        cap["status"] = "proposed"
        cap["source_paths"] = []
        cap["test_paths"] = []
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    _, findings = run_auditor("audit_governance", repo_copy)
    amortecedores = [f for f in findings if f["origin"] == "change_buffer"]
    assert not amortecedores, amortecedores
