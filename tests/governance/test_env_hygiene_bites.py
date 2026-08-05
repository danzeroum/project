"""Mordidas da higiene de ambiente estendida (CP-025 / ADR-018).

`violacoes` recebe o ambiente como DICIONÁRIO em vez de ler `os.environ`, e isso não é preferência
de estilo: um teste que dependesse do ambiente real passaria ou falharia conforme a máquina — e o
sandbox onde este repositório é desenvolvido tem proxy definido, então metade destes testes
"passaria" por acidente e a outra metade falharia sem defeito nenhum. Ambiente como argumento é o
que torna a trava testável em qualquer lugar.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import env_guard as eg  # noqa: E402

POLITICA = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))["env_hygiene"]

# Derivada do arquivo real, nunca redigitada: uma variável nova na denylist nasce coberta por
# estes testes, e a lista do teste não pode divergir da lista que morde (lição do CP-020).
NOMES_NEGADOS = POLITICA["env_denylist_exact"]


def test_ambiente_limpo_passa():
    """O par positivo. Sem ele, um guard que reprovasse tudo passaria em todos os negativos."""
    assert eg.violacoes({"PATH": "/usr/bin", "HOME": "/root", "LANG": "C"}, POLITICA) == []


@pytest.mark.parametrize("nome", NOMES_NEGADOS)
def test_cada_variavel_de_sequestro_aborta(nome: str):
    """Uma por uma. Um teste que checasse só a lista inteira não perceberia a entrada removida."""
    achados = eg.violacoes({"PATH": "/usr/bin", nome: "valor"}, POLITICA)
    assert any(nome in a for a in achados), achados


def test_prefixo_webqa_continua_mordendo():
    """A família antiga não pode ter sido perdida ao acrescentar a nova."""
    achados = eg.violacoes({"WEBQA_LOAD_AUTHORIZED": "1"}, POLITICA)
    assert any("WEBQA_LOAD_AUTHORIZED" in a for a in achados), achados


def test_excecao_declarada_vale_so_no_contexto_declarado():
    """O contexto é o que torna a exceção honesta.

    Uma exceção sem contexto valeria em toda parte — e exceção que vale em toda parte é a entrada
    removida da lista com outro nome. Este teste é o que impede essa degradação silenciosa.
    """
    ambiente = {"PYTHONPATH": "/tmp/copia/ci"}
    assert eg.violacoes(ambiente, POLITICA, contexto="mutation-tests") == []
    assert eg.violacoes(ambiente, POLITICA, contexto="outro-contexto") != []
    assert eg.violacoes(ambiente, POLITICA, contexto=None) != []


def test_excecao_nao_libera_variavel_diferente():
    """A exceção é de PYTHONPATH no contexto de mutação — não é um salvo-conduto para o contexto."""
    achados = eg.violacoes({"HTTPS_PROXY": "http://x"}, POLITICA, contexto="mutation-tests")
    assert any("HTTPS_PROXY" in a for a in achados), achados


def test_fail_on_denied_env_desligado_nao_aborta():
    """Documenta o comportamento do interruptor — e prova que ele não é decorativo.

    Se este teste falhar dizendo que abortou mesmo com a flag desligada, alguém cravou o
    comportamento no código e a declaração em harness.yaml virou enfeite.
    """
    pol = {**POLITICA, "fail_on_denied_env": False}
    achados = eg.violacoes({"HTTP_PROXY": "x"}, pol)
    assert achados, "violações continuam sendo DETECTADAS; o que muda é o que se faz com elas"


def test_guard_sai_10_com_variavel_negada(tmp_path: Path):
    """DENIED_ENV=10 é o mesmo código do guard da suíte, de propósito: um código só para a mesma
    classe de erro é o que permite um passo de CI reagir sem interpretar texto."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "ci/env_guard.py"), "--quiet"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HARNESS_REPO_ROOT": str(REPO), "HTTP_PROXY": "http://evil"},
    )
    assert proc.returncode == 10, proc.stderr


def test_guard_sai_0_com_ambiente_limpo():
    proc = subprocess.run(
        [sys.executable, str(REPO / "ci/env_guard.py"), "--quiet"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HARNESS_REPO_ROOT": str(REPO)},
    )
    assert proc.returncode == 0, proc.stderr


def test_workflows_nao_duplicam_a_lista():
    """Derivar, nunca duplicar. Uma segunda cópia deriva em silêncio, e a primeira entrada a
    divergir é justamente a que alguém removeu.

    O que se proíbe é a lista em CONFIGURAÇÃO EXECUTÁVEL — linhas de comentário citando um exemplo
    são prosa, e prosa não deriva porque ninguém a lê como fonte. A distinção importa: um teste que
    proibisse a palavra em qualquer lugar do arquivo impediria explicar a decisão onde ela é
    aplicada, e comentário é justamente onde o próximo leitor procura o porquê.

    E um nome negado só aparece em configuração executável se houver EXCEÇÃO DECLARADA para ele em
    harness.yaml. É o que torna a declaração load-bearing: sem esta checagem, `exceptions` seria um
    bloco decorativo que ninguém confere, e a variável apareceria no workflow com ou sem ele.

    HTTP_PROXY é o caso à parte, e é deliberado: ele aparece em `env:` do passo NEGATIVO, que
    existe justamente para provar que a trava morde. Isentá-lo aqui é o preço de ter a prova.
    """
    declaradas = {e["name"] for e in POLITICA.get("exceptions") or []}
    for wf in (".github/workflows/qa.yml", ".github/workflows/governance.yml"):
        linhas = [l for l in (REPO / wf).read_text(encoding="utf-8").splitlines()
                  if not l.lstrip().startswith("#")]
        codigo = "\n".join(linhas)
        repetidas = [n for n in NOMES_NEGADOS
                     if n in codigo and n != "HTTP_PROXY" and n not in declaradas]
        assert not repetidas, (
            f"{wf} usa {repetidas} em configuração executável sem exceção declarada em "
            f"harness.yaml:env_hygiene.exceptions")


def test_toda_excecao_declarada_e_usada():
    """Isenção morta é isenção que só faz a trava parecer mais apertada do que é.

    Mesma lógica do `ungoverned` de stages.yaml: uma exceção que não protege uso algum devia ser
    removida, e enquanto estiver lá dá permissão que ninguém pediu.
    """
    usos = "\n".join((REPO / wf).read_text(encoding="utf-8")
                     for wf in (".github/workflows/qa.yml", ".github/workflows/governance.yml"))
    usos += "\n".join(p.read_text(encoding="utf-8")
                      for p in (REPO / "tests/governance").glob("*.py"))
    for excecao in POLITICA.get("exceptions") or []:
        assert excecao["name"] in usos, (
            f"exceção declarada para {excecao['name']} não protege uso algum — "
            f"exceção morta dá permissão que ninguém pediu")


def test_hook_do_agente_recusa_sequestro():
    """A trava que só existe no CI não protege onde o agente tem shell."""
    payload = json.dumps({"tool_input": {"command": "PYTHONPATH=/tmp/meu python ci/validate_all.py"}})
    proc = subprocess.run(
        [sys.executable, str(REPO / "ci/hooks/pre_bash_env_hygiene.py")],
        input=payload, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 2, proc.stdout
    assert "DENIED_ENV" in proc.stderr


def test_hook_do_agente_deixa_passar_comando_limpo():
    payload = json.dumps({"tool_input": {"command": "python ci/validate_all.py"}})
    proc = subprocess.run(
        [sys.executable, str(REPO / "ci/hooks/pre_bash_env_hygiene.py")],
        input=payload, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr


def test_denylist_vazia_reprova_no_schema():
    """minItems 1 faz esvaziar a lista ser tão visível quanto remover a chave — e esvaziar é o
    gesto mais provável de quem quer desligar a trava sem parecer que a removeu."""
    import harness_lib as hl

    doc = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    doc["env_hygiene"]["env_denylist_exact"] = []
    assert hl.schema_errors("harness.yaml", "harness.schema.json", doc)
