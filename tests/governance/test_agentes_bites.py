"""Mordidas da correspondência prompts↔agentes e da metacognição (CP-027 / ADR-022).

A correspondência é lida do `inputs.md` de cada agente, e os testes precisam refletir isso — um
teste que assumisse a convenção `<agente>-task.md` passaria hoje e falharia no dia em que alguém
lesse o repositório de verdade: `review-task.md` é do `reviewer`, `lgpd-task.md` é do `privacy`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO, recarregar_fiscais

sys.path.insert(0, str(REPO / "ci"))

import generate_schema_docs as gsd  # noqa: E402
import harness_lib as hl  # noqa: E402
import orient  # noqa: E402


@pytest.fixture
def em_copia(monkeypatch):
    """Aponta os módulos para uma cópia e DEVOLVE a árvore real no teardown.

    Sem o teardown, um teste que recarrega harness_lib para /tmp deixa REPO congelado lá e todos
    os testes seguintes julgam um repositório que já foi apagado — o bug que o conftest chama de
    "REPO congelado do teste anterior", e que já custou caro nesta suíte.
    """
    import importlib

    def _apontar(root, modulo):
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        # O GRAFO INTEIRO, não só harness_lib: orient.pronto() chama cobertura_do_alvo(), que usa
        # inventory_code. Recarregar pela metade deixa um módulo julgando a cópia e outro a árvore
        # real — e o erro que isso produz ("não está no subpath de") não parece um bug de teste.
        recarregar_fiscais()
        return importlib.reload(modulo)

    yield _apontar

    monkeypatch.delenv("HARNESS_REPO_ROOT", raising=False)
    recarregar_fiscais()
    importlib.reload(gsd)
    importlib.reload(orient)


# --------------------------------------------------------------------------------------
# Correspondência bidirecional
# --------------------------------------------------------------------------------------

def test_todo_agente_tem_template(repo_copy: Path, run_auditor):
    """O par positivo: o repositório como está satisfaz as duas direções."""
    code, findings = run_auditor("audit_governance", repo_copy)
    assert not [f for f in findings if f["origin"] == "agent_pairing"], findings


def test_agente_sem_template_reprova(repo_copy: Path, run_auditor):
    """A fronteira do AGENT.md existe e não é lida — quem invocar o agente improvisa a instrução."""
    inputs = repo_copy / "harness/agents/developer/inputs.md"
    inputs.write_text(inputs.read_text(encoding="utf-8").replace(
        "- `harness/prompts/developer-task.md` — o template da tarefa.", ""), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-AGENT-NO-TEMPLATE") for f in findings), \
        [f["id"] for f in findings]


def test_agente_fantasma_reprova(repo_copy: Path, run_auditor):
    """Template sem agente: instrução viva para um papel que não existe, com proibições que
    ninguém mantém — e continua invocável."""
    (repo_copy / "harness/prompts/fantasma-task.md").write_text(
        "# Task template: fantasma\n\nVocê pode tudo.\n", encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-PROMPT-GHOST") for f in findings), [f["id"] for f in findings]


def test_template_declarado_inexistente_reprova(repo_copy: Path, run_auditor):
    inputs = repo_copy / "harness/agents/tester/inputs.md"
    inputs.write_text(inputs.read_text(encoding="utf-8").replace(
        "harness/prompts/tester-task.md", "harness/prompts/nao-existe.md"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f["id"].startswith("FIND-AGENT-TEMPLATE-MISSING") for f in findings), \
        [f["id"] for f in findings]


def test_correspondencia_nao_assume_convencao_de_nome():
    """A evidência que derrubaria uma convenção `<agente>-task.md`, registrada como teste.

    Se alguém "arrumar" o fiscal para usar o nome do arquivo, estes dois pares quebram — e são
    pares REAIS, citados por ADRs e pelo registro de riscos.
    """
    reviewer = (REPO / "harness/agents/reviewer/inputs.md").read_text(encoding="utf-8")
    privacy = (REPO / "harness/agents/privacy/inputs.md").read_text(encoding="utf-8")
    assert "harness/prompts/review-task.md" in reviewer
    assert "harness/prompts/lgpd-task.md" in privacy


def test_todo_template_declara_o_proibido():
    """Um template que não repete as proibições devolve o agente ao improviso — que é o problema
    inteiro que esta CP existe para resolver."""
    for arquivo in sorted((REPO / "harness/prompts").glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8").lower()
        assert "proibid" in texto or "nunca" in texto or "não dispara" in texto, arquivo.name


# --------------------------------------------------------------------------------------
# Documentação viva dos schemas
# --------------------------------------------------------------------------------------

def test_schema_docs_check_reprova_desatualizado(repo_copy: Path, em_copia):
    """R-11: doc que pode envelhecer sem custo envelhece, e passa a mentir com autoridade."""
    (repo_copy / "docs/schema-reference.md").write_text("# desatualizado\n", encoding="utf-8")
    assert em_copia(repo_copy, gsd).main(["--check"]) == 1


def test_schema_docs_em_dia_passa(repo_copy: Path, em_copia):
    assert em_copia(repo_copy, gsd).main(["--check"]) == 0


def test_schema_docs_carrega_cabecalho_canonico():
    """Nasce coberto por check_derived_vs_source — a prova de que aquele fiscal deriva do
    diretório em vez de conhecer dois arquivos."""
    texto = (REPO / "docs/schema-reference.md").read_text(encoding="utf-8")
    assert texto.startswith("<!-- GENERATED: não editar; rodar ci/generate_schema_docs.py -->")


def test_schema_docs_nao_inventa_campo_inexistente():
    """O gerador não desce em allOf/if/then: um índice que descreve campos inexistentes manda o
    leitor procurar o que não há, e isso é pior que um índice incompleto."""
    doc = gsd.render()
    assert "allOf" not in doc and "/if/" not in doc


# --------------------------------------------------------------------------------------
# Prontidão como modo (R-10)
# --------------------------------------------------------------------------------------

def test_orient_pronto_nao_reprova():
    """O contrato do orientador (ADR-014): ele responde 'o que falta', nunca reprova.

    Um orientador que também fiscaliza vira o oitavo fiscal, sem política e sem teste de mordida.
    """
    assert orient.main(["--pronto"]) == 0


def test_orient_pronto_reprova_lock_ausente(repo_copy: Path, em_copia):
    """"Reprova" aqui significa APONTAR — o exit continua 0, e é essa a decisão.

    O nome do teste vem do plano; o comportamento correto é o do ADR-014. A pendência aparece na
    lista, e o gate continua sendo validate_all.py.
    """
    import yaml

    projeto = repo_copy / "project.yaml"
    doc = yaml.safe_load(projeto.read_text(encoding="utf-8"))
    doc["project"]["kind"] = "derived"
    doc["target"] = {"repo": "exemplo/alvo", "ref": "main", "lock_source": "target.lock",
                     "code_roots": ["src"], "test_roots": ["tests"]}
    projeto.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    modulo = em_copia(repo_copy, orient)
    dados = modulo.pronto()

    itens = [p["item"] for p in dados["pendencias"]]
    assert any("target_sha" in i for i in itens), itens
    assert any("mold_release" in i for i in itens), itens
    assert modulo.main(["--pronto"]) == 0


def test_pronto_reusa_as_funcoes_do_panorama():
    """R-10 rejeitou o script separado porque ele duplicava — e a duplicata errava o caminho do
    lock. Este teste é o que impede a duplicação de voltar."""
    fonte = (REPO / "ci/orient.py").read_text(encoding="utf-8")
    corpo = fonte.split("def pronto(")[1].split("\ndef ")[0]
    assert "papel()" in corpo and "fiscais_agora()" in corpo and "cobertura_do_alvo()" in corpo
