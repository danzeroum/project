"""Mordidas da prova de mutação e do fiscal de dependências (CP-030 / ADR-024).

Este é o teste de um fiscal de fiscais, e a assimetria importa: os testes que valem aqui são os
que provam que ele acusa quando DEVE — porque o modo de falha dele não é reprovar demais, é passar
de leve e certificar travas decorativas como se mordessem.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import audit_mutations as am  # noqa: E402
import check_dependency_conflict as cdc  # noqa: E402


# --------------------------------------------------------------------------------------
# Derivação da mutação
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("asser,esperado", [
    ({"kind": "path_present", "paths": ["ci/x.py"]}, "remover_caminho"),
    ({"kind": "path_absent", "paths": ["webqa"]}, "criar_caminho"),
    ({"kind": "file_matches", "files": ["a.md"], "pattern": "x"}, "apagar_padrao"),
    ({"kind": "schema_lock", "file": "s.json", "pointer": "/a"}, "quebrar_ponteiro"),
    ({"kind": "import_required", "module_glob": "m.py", "symbols": ["a.b.C"]}, "apagar_linha"),
    ({"kind": "import_forbidden", "module_glob": "m.py", "symbols": ["a.b.C"]}, "injetar_texto"),
])
def test_cada_tipo_de_assercao_tem_inverso(asser, esperado):
    """Derivar em vez de declarar 118 vezes é a decisão — e ela exige que o inverso exista."""
    assert am.derivar_mutacao(asser)["op"] == esperado


def test_mutacao_declarada_vence_a_derivada():
    """O escape para o que a derivação não alcança."""
    asser = {"kind": "file_matches", "files": ["a.md"], "pattern": "x",
             "mutation": {"op": "injetar_texto", "alvo": "b.md", "texto": "t"}}
    assert am.derivar_mutacao(asser)["alvo"] == "b.md"


def test_regex_expressiva_nao_e_derivavel():
    """Errar aqui é SEGURO por desenho: o fiscal confere se o texto de fato casa antes de usá-lo.

    Adivinhação verificada é barata; adivinhação confiada seria a fonte de um verde falso — a
    asserção passaria por provada sem nunca ter sido negada.
    """
    asser = {"kind": "file_lacks", "files": ["a.md"], "pattern": r"(duration|elapsed).*[0-9]+"}
    assert am.derivar_mutacao(asser) is None


def test_texto_derivado_de_fato_casa_o_padrao():
    """A verificação que torna a heurística aceitável."""
    import re

    texto = am._texto_que_casa(r"^Fiscalizado por:")
    assert texto and re.search(r"^Fiscalizado por:", texto, re.MULTILINE)


def test_apagar_padrao_remove_todas_as_ocorrencias(tmp_path: Path):
    """A correção que a própria prova exigiu.

    Com uma ocorrência só, cinco asserções ficaram verdes depois da mutação e o fiscal as acusou
    de decorativas. Elas não eram — a mutação é que era insuficiente. O inverso de "o arquivo
    contém o padrão" é "não contém mais".
    """
    alvo = tmp_path / "a.txt"
    alvo.write_text("marca\noutra\nmarca\nmarca\n", encoding="utf-8")
    am.aplicar({"op": "apagar_padrao", "alvo": "a.txt", "pattern": "marca"}, tmp_path)
    assert "marca" not in alvo.read_text(encoding="utf-8")


def test_mutacao_de_import_mantem_o_arquivo_parseavel(tmp_path: Path):
    """Apagar o SÍMBOLO deixava `from x import # comentário` — SyntaxError.

    O fiscal passava a reportar ERRO ("não consegui fiscalizar") em vez de ACHADO, e os dois
    estados são distintos por desenho nesta casa. A mutação não pode confundi-los: ela existe para
    provar que a asserção MORDE.
    """
    import ast

    alvo = tmp_path / "m.py"
    alvo.write_text("from a.b import C\n\nx = 1\n", encoding="utf-8")
    am.aplicar({"op": "apagar_linha", "alvo": "m.py", "contendo": "C"}, tmp_path)
    ast.parse(alvo.read_text(encoding="utf-8"))
    assert "import C" not in alvo.read_text(encoding="utf-8")


def test_glob_nao_escolhe_arquivo_que_a_assercao_exclui(tmp_path: Path):
    """Mutar o arquivo excluído não prova nada — e faz o fiscal acusar o lugar errado."""
    (tmp_path / "d").mkdir()
    (tmp_path / "d/README.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "d/outro.md").write_text("x\n", encoding="utf-8")
    escolhido = am._resolver(tmp_path, "d/*.md", exclude=["d/README.md"])
    assert escolhido.name == "outro.md"


def test_restaurar_devolve_o_arquivo_ao_estado_anterior(tmp_path: Path):
    """Sem restauração fiel, a segunda mutação julgaria o estrago da primeira."""
    alvo = tmp_path / "a.txt"
    alvo.write_text("original\n", encoding="utf-8")
    antes = am.aplicar({"op": "injetar_texto", "alvo": "a.txt", "texto": "sujeira"}, tmp_path)
    am.restaurar(antes, tmp_path)
    assert alvo.read_text(encoding="utf-8") == "original\n"


# --------------------------------------------------------------------------------------
# A prova ponta a ponta
# --------------------------------------------------------------------------------------

def test_toda_regra_bloqueante_morde(repo_copy: Path):
    """A prova de fogo 4 inteira, sobre uma cópia real.

    Se este teste falhar dizendo `nao_morde`, alguma asserção virou decorativa. Se falhar dizendo
    `mutacao_nao_derivavel`, alguma asserção nova precisa declarar sua mutação.
    """
    achados, provadas = am.provar(repo_copy)
    assert not achados, achados
    assert provadas > 100, provadas


def test_assercao_decorativa_e_acusada(repo_copy: Path):
    """O fiscal reprovando a si mesmo: uma asserção que não morde precisa aparecer.

    A asserção injetada exige um padrão que o arquivo já contém em muitos lugares, e a mutação
    aponta para OUTRO arquivo — então a asserção continua verde depois de mutada, que é a definição
    de decorativa.
    """
    caminho = repo_copy / "architecture/adr/index.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["adrs"][0]["assertions"].append({
        "id": "ADR-001-A99", "kind": "file_matches", "severity": "high",
        "risk": "RISK-WEBQA-001", "description": "asserção decorativa de teste",
        "files": ["README.md"], "pattern": "a",
        "mutation": {"op": "injetar_texto", "alvo": "LICENSE", "texto": "nada a ver"},
    })
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    achados, _ = am.provar(repo_copy, apenas="ADR-001-A99")
    assert any(a["problema"] == "nao_morde" for a in achados), achados


def test_assercao_sem_mutacao_derivavel_e_acusada(repo_copy: Path):
    """'Regra bloqueante sem mutação declarada reprova a si mesma' (§12)."""
    caminho = repo_copy / "architecture/adr/index.yaml"
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    doc["adrs"][0]["assertions"].append({
        "id": "ADR-001-A98", "kind": "file_lacks", "severity": "high",
        "risk": "RISK-WEBQA-001", "description": "regex que não se deriva",
        "files": ["README.md"], "pattern": r"(alfa|beta)+\d{2,}",
    })
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    achados, _ = am.provar(repo_copy, apenas="ADR-001-A98")
    assert any(a["problema"] == "mutacao_nao_derivavel" for a in achados), achados


def test_prova_fica_fora_da_validacao_total():
    """Um fiscal que torna o loop de trabalho insuportável é desligado, não obedecido."""
    assert "audit_mutations" not in (REPO / "ci/validate_all.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Conflito de dependências (§10)
# --------------------------------------------------------------------------------------

def test_versoes_exatas_divergentes_reprovam():
    decl = {"pytest": [("pyproject.toml", "==", "8.0.0"), ("requirements-ci.txt", "==", "9.1.1")]}
    assert cdc.conflitos(decl)


def test_faixa_com_pin_nao_e_conflito():
    """Um >=8 no pyproject com um ==9.1.1 no lock não se contradizem — o segundo é resolução
    válida do primeiro. Acusar isso seria o fiscal reprovando o funcionamento normal de um
    lockfile, e fiscal que acusa o legítimo é desligado por quem tem trabalho a fazer."""
    decl = {"pytest": [("pyproject.toml", ">=", "8"), ("requirements-ci.txt", "==", "9.1.1")]}
    assert not cdc.conflitos(decl)


def test_mesma_versao_em_duas_fontes_nao_e_conflito():
    decl = {"pyyaml": [("a.txt", "==", "6.0.3"), ("b.txt", "==", "6.0.3")]}
    assert not cdc.conflitos(decl)


def test_declaracoes_lidas_das_fontes_reais():
    """Lê o DECLARADO, nunca o instalado: conferir contra o site-packages faria o fiscal passar ou
    reprovar conforme a máquina de quem roda."""
    decl = cdc.declaracoes()
    assert "webqa-suite" in decl
    assert any(f == "requirements-ci.txt" for ocs in decl.values() for f, _, _ in ocs)


def test_conflito_real_reprova_ponta_a_ponta(repo_copy: Path, monkeypatch):
    import importlib

    import harness_lib as hl

    alvo = repo_copy / "requirements-ci.txt"
    alvo.write_text(alvo.read_text(encoding="utf-8") + "\npyyaml==1.0.0 \\\n    --hash=sha256:"
                    + "0" * 64 + "\n", encoding="utf-8")
    (repo_copy / "requirements-qa.txt").write_text(
        (repo_copy / "requirements-qa.txt").read_text(encoding="utf-8") + "\npyyaml==2.0.0\n",
        encoding="utf-8")

    monkeypatch.setenv("HARNESS_REPO_ROOT", str(repo_copy))
    importlib.reload(hl)
    modulo = importlib.reload(cdc)
    assert modulo.main(["--quiet"]) == 1
