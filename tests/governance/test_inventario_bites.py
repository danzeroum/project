"""Prova que "código sem metadado não existe" morde — e em três linguagens diferentes.

Um alvo só não prova genericidade. Os três aqui são deliberadamente distintos:

  python      caminho feliz e adapter nativo (AST)
  typescript  monorepo com dois pacotes e import cruzado — code_roots múltiplos
  go          linguagem SEM leitor semântico: o fallback resolve pertencimento e o laudo
              DECLARA que as arestas de dependência ficaram por fazer

O teste que mais importa é test_go_cai_no_fallback_e_declara_o_que_nao_leu. Uma linguagem
desconhecida que saísse verde seria cobertura afirmada e nunca verificada — verde por vacuidade,
indistinguível de verde por cobertura. O que se exige do fiscal não é onisciência: é que a
ignorância apareça.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
import yaml

CI = Path(__file__).resolve().parent.parent.parent / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))


@pytest.fixture
def inventariar(monkeypatch):
    """Constrói o inventário de uma cópia, com REPO apontado para ela."""

    def _run(root: Path) -> dict:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        import harness_lib
        importlib.reload(harness_lib)
        import adapters
        importlib.reload(adapters)
        import inventory_code
        importlib.reload(inventory_code)
        inventory_code.reset_cache()
        return inventory_code.build()

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


def _ancora(root: Path, code_roots: list[str], test_roots: list[str], languages: list[str]) -> None:
    """Transforma a cópia num derivado cujo alvo já está materializado em workspace/target/."""
    p = root / "project.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["project"]["kind"] = "derived"
    doc["target"] = {"repo": "sintetico/alvo", "ref": "principal", "lock_source": "target.lock",
                     "code_roots": code_roots, "test_roots": test_roots, "languages": languages}
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    lock = root / "target.lock"
    ldoc = yaml.safe_load(lock.read_text(encoding="utf-8"))
    ldoc.update(kind="derived", target_sha="0" * 40)
    lock.write_text(yaml.safe_dump(ldoc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _componentes(root: Path, componentes: list[dict], exemptions: list[dict] | None = None) -> None:
    p = root / "architecture/components.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["components"] = componentes
    doc["exemptions"] = exemptions or []
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _escrever(root: Path, arquivos: dict[str, str]) -> None:
    for rel, conteudo in arquivos.items():
        alvo = root / "workspace/target" / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")


def _por_path(inv: dict) -> dict[str, dict]:
    return {m["path"]: m for m in inv["modulos"]}


# --------------------------------------------------------------------------------------
# O molde fiscaliza a si mesmo
# --------------------------------------------------------------------------------------

def test_baseline_do_molde_esta_conforme(repo_copy, run_metadata):
    code, errors = run_metadata(repo_copy)
    assert code == 0, f"o baseline deveria estar verde, mas: {errors}"


def test_arquivo_novo_sem_componente_reprova(repo_copy, run_metadata):
    """A invariante, no caso mais simples: implementação nova sem metadado que a reivindique."""
    (repo_copy / "src/project/novo_modulo.py").write_text("VALOR = 1\n", encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("novo_modulo.py" in e and "órfão" in e for e in errors), errors


def test_isencao_declarada_faz_o_arquivo_passar(repo_copy, run_metadata):
    """A trava tem que aceitar a declaração — senão empurra o time a inventar um dono falso."""
    (repo_copy / "src/project/novo_modulo.py").write_text("VALOR = 1\n", encoding="utf-8")
    p = repo_copy / "architecture/components.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["exemptions"].append({
        "path": "src/project/novo_modulo.py",
        "justification": "constante de configuração sem lógica de negócio, injetada pelo teste "
                         "para provar que a isenção declarada é aceita",
    })
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 0, errors


def test_isencao_morta_reprova(repo_copy, run_metadata):
    """Isenção que não protege nada só serve para a cobertura parecer fechada."""
    p = repo_copy / "architecture/components.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["exemptions"].append({
        "path": "src/nao/existe.py",
        "justification": "isenção deliberadamente morta, injetada pelo teste para provar a mordida",
    })
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("isenção morta" in e for e in errors), errors


def test_dois_donos_reprovam(repo_copy, run_metadata):
    """Dono ambíguo é dono nenhum: quando o arquivo mudar, cada time acha que o outro revisou."""
    p = repo_copy / "architecture/components.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["components"][1]["source_paths"].append("src/project/pricing.py")
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("mais de um componente" in e for e in errors), errors


def test_teste_orfao_reprova(repo_copy, run_metadata):
    (repo_copy / "tests/unit/test_novo.py").write_text("def test_x():\n    assert True\n",
                                                       encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("teste órfão" in e for e in errors), errors


def test_dependencia_nao_declarada_reprova(repo_copy, run_metadata):
    """Import real entre componentes que nenhum depends_on registrou."""
    p = repo_copy / "architecture/components.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    for comp in doc["components"]:
        if comp["id"] == "CMP-PRICING":
            comp["depends_on"] = []          # o import de ports.py continua existindo
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("depends_on" in e for e in errors), errors


def test_exposes_inexistente_reprova(repo_copy, run_metadata):
    p = repo_copy / "architecture/components.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["components"][0]["exposes"].append("project.pricing.funcao_que_nao_existe")
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("exposes" in e for e in errors), errors


# --------------------------------------------------------------------------------------
# Os três alvos sintéticos
# --------------------------------------------------------------------------------------

def test_alvo_python_e_lido_semanticamente(repo_copy, inventariar):
    _escrever(repo_copy, {
        "app/servico.py": "from app.repo import buscar\n\n\ndef executar():\n    return buscar()\n",
        "app/repo.py": "def buscar():\n    return []\n",
        "app/__init__.py": "",
        "provas/test_servico.py": "def test_ok():\n    assert True\n",
    })
    _ancora(repo_copy, ["app"], ["provas"], ["python"])
    inv = inventariar(repo_copy)

    mods = _por_path(inv)
    assert inv["adapters"]["python"]["semantico"] is True
    servico = mods["workspace/target/app/servico.py"]
    assert servico["exposes"] == ["app.servico.executar"]
    assert servico["imports"] == ["workspace/target/app/repo.py"]
    assert mods["workspace/target/provas/test_servico.py"]["kind"] == "test"


def test_alvo_typescript_monorepo_resolve_import_cruzado(repo_copy, inventariar):
    """Dois pacotes, duas raízes de código, uma aresta entre eles."""
    _escrever(repo_copy, {
        "packages/core/index.ts": "export function somar(a: number, b: number) { return a + b }\n",
        "apps/web/main.ts": (
            'import { somar } from "../../packages/core/index"\n'
            "export const total = somar(1, 2)\n"
        ),
        "apps/web/main.test.ts": 'import { total } from "./main"\nexport const t = total\n',
    })
    _ancora(repo_copy, ["packages", "apps"], [], ["typescript"])
    inv = inventariar(repo_copy)

    mods = _por_path(inv)
    assert inv["adapters"]["typescript"]["semantico"] is False
    assert "nao_lido" in inv["adapters"]["typescript"]
    assert mods["workspace/target/packages/core/index.ts"]["exposes"] == ["somar"]
    assert mods["workspace/target/apps/web/main.ts"]["imports"] == [
        "workspace/target/packages/core/index.ts"
    ]


def test_go_cai_no_fallback_e_declara_o_que_nao_leu(repo_copy, inventariar):
    """Sem leitor semântico de Go, o pertencimento continua resolvido — e a perda é declarada.

    Verde por não ter entendido o código é o único resultado que este repositório não aceita.
    """
    _escrever(repo_copy, {
        "cmd/main.go": 'package main\n\nfunc main() { println("oi") }\n',
        "interno/servico.go": "package interno\n\nfunc Buscar() int { return 1 }\n",
    })
    _ancora(repo_copy, ["cmd", "interno"], [], ["go"])
    inv = inventariar(repo_copy)

    generico = inv["adapters"]["generico"]
    assert generico["arquivos"] == 2
    assert generico["semantico"] is False
    assert "arestas de dependência" in generico["nao_lido"]

    mods = _por_path(inv)
    assert set(mods) == {"workspace/target/cmd/main.go", "workspace/target/interno/servico.go"}
    assert all(m["exposes"] == [] and m["imports"] == [] for m in mods.values())


def test_alvo_go_sem_componente_ainda_reprova(repo_copy, run_metadata):
    """A invariante atravessa a barreira da linguagem: o fallback não é um passe livre."""
    _escrever(repo_copy, {"cmd/main.go": "package main\n\nfunc main() {}\n"})
    _ancora(repo_copy, ["cmd"], [], ["go"])
    _componentes(repo_copy, [{
        "id": "CMP-CLI", "kind": "domain-module", "capability": "CAP-PRICING", "status": "proposed",
        "source_paths": [], "tested_by": [], "owner": "engineering",
    }])
    code, errors = run_metadata(repo_copy)
    assert code == 1
    assert any("main.go" in e and "órfão" in e for e in errors), errors


def test_raiz_declarada_inexistente_e_exit_2(repo_copy, inventariar):
    """Fiscal que percorre conjunto vazio reporta verde — por isso isto é erro, não achado."""
    (repo_copy / "workspace/target").mkdir(parents=True, exist_ok=True)
    _ancora(repo_copy, ["nao-existe"], [], ["python"])
    # Exception, e não HarnessError: a fixture recarrega harness_lib, então a classe importada
    # aqui no topo do módulo deixa de ser a mesma que o fiscal levanta. A mensagem é o contrato.
    with pytest.raises(Exception, match="vacuidade"):
        inventariar(repo_copy)
