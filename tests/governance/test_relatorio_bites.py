"""As mordidas do relatório derivado (CP-045, ADR-031).

`ADR-024`: toda trava prova que morde. Um teste que só confirma o caminho feliz não é mordida — ele
confirma o que se queria ouvir. Cada teste aqui aplica uma MUTAÇÃO a uma cópia do repositório e
exige a reprovação, com o código de saída certo.

As duas últimas são mordidas **de classe** e valem mais que as outras sete: elas não impedem esta
ocorrência, impedem a PRÓXIMA. Um identificador literal e um leitor de YAML paralelo são os dois
modos pelos quais este gerador deixaria de derivar e passaria a enumerar — em silêncio, e com
aparência de código cuidadoso.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO

CI = REPO / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))

GERADOR = "ci/generate_report.py"
HTML = "docs/relatorio/index.html"
JSON_ = "docs/relatorio/report.json"


def _rodar(root: Path, argv: list[str], monkeypatch) -> int:
    """Roda o gerador contra uma cópia, recarregando o grafo para que REPO aponte para ela.

    Recarregar pela metade deixaria um REPO congelado do teste anterior — o bug mais caro desta
    suíte, e a razão de o conftest recarregar `harness_lib` ANTES de quem o importa.
    """
    monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
    import harness_lib
    importlib.reload(harness_lib)
    import generate_report
    importlib.reload(generate_report)
    return generate_report.main(argv)


@pytest.fixture(autouse=True)
def _restaura_repo():
    yield
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)
    import generate_report
    importlib.reload(generate_report)


# --------------------------------------------------------------------------------------
# 1–2. O artefato não pode envelhecer, nem ser corrigido à mão
# --------------------------------------------------------------------------------------

def test_artefato_vencido_REPROVA(repo_copy, monkeypatch):
    """Fonte mudou e ninguém regenerou ⇒ exit 1. É o que impede o artefato de virar ficção.

    A mutação escolhida é uma etapa nova em `stages.yaml` de propósito: ela muda um CONTADOR, que é
    a classe de defeito que este relatório inteiro existe para não cometer. Se o `--check` deixasse
    passar, a tela diria "catorze" para sempre — exatamente como `CLAUDE.md` diz "treze" hoje.
    """
    assert _rodar(repo_copy, [], monkeypatch) == 0, "o artefato precisa nascer em dia"

    stages = repo_copy / "harness/stages.yaml"
    texto = stages.read_text(encoding="utf-8")
    marca = "ungoverned:"
    assert marca in texto
    texto = texto.replace(marca, (
        "  - id: STAGE-INVENTADA\n"
        "    order: 99\n"
        '    name: "Etapa que só existe para mover o contador"\n'
        '    artifacts: ["docs"]\n'
        "    privacy_lens:\n"
        "      scan: false\n"
        '      question: "nenhuma"\n\n'
    ) + marca, 1)
    stages.write_text(texto, encoding="utf-8")

    assert _rodar(repo_copy, ["--check", "--quiet"], monkeypatch) == 1


def test_artefato_editado_a_mao_REPROVA(repo_copy, monkeypatch):
    """A edição manual é contradita na hora mais cara — antes do merge, não depois do relatório."""
    assert _rodar(repo_copy, [], monkeypatch) == 0

    alvo = repo_copy / HTML
    alvo.write_text(alvo.read_text(encoding="utf-8").replace("</main>", "<p>corrigido à mão</p></main>"),
                    encoding="utf-8")

    assert _rodar(repo_copy, ["--check", "--quiet"], monkeypatch) == 1


def test_o_check_olha_os_DOIS_artefatos(repo_copy, monkeypatch):
    """Mexer só no JSON também reprova. O HTML é projeção do JSON; vigiar um só deixaria metade
    do contrato sem trava, e seria a metade que as ferramentas consomem."""
    assert _rodar(repo_copy, [], monkeypatch) == 0

    alvo = repo_copy / JSON_
    doc = json.loads(alvo.read_text(encoding="utf-8"))
    doc["counts"]["capabilities"] = 999
    alvo.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")

    assert _rodar(repo_copy, ["--check", "--quiet"], monkeypatch) == 1


# --------------------------------------------------------------------------------------
# 3. Determinismo — sem ele o --check vira ruído, e ruído se desliga
# --------------------------------------------------------------------------------------

def test_determinismo_byte_a_byte(repo_copy, monkeypatch):
    """Duas execuções, saída idêntica. Um artefato não determinístico transforma a trava num
    gerador de ruído, e o remédio que as pessoas escolhem é desligá-la."""
    assert _rodar(repo_copy, [], monkeypatch) == 0
    primeiro = (repo_copy / JSON_).read_bytes(), (repo_copy / HTML).read_bytes()

    assert _rodar(repo_copy, [], monkeypatch) == 0
    segundo = (repo_copy / JSON_).read_bytes(), (repo_copy / HTML).read_bytes()

    assert primeiro == segundo


def test_nenhum_relogio_no_artefato(repo_copy, monkeypatch):
    """A trava sobre a causa, não sobre o sintoma: um timestamp de execução tornaria o teste acima
    vermelho de forma intermitente, que é pior que vermelho sempre — intermitente se atribui ao
    ambiente. O carimbo legítimo é o digest das fontes."""
    assert _rodar(repo_copy, [], monkeypatch) == 0
    doc = json.loads((repo_copy / JSON_).read_text(encoding="utf-8"))

    assert "sources_digest" in doc["provenance"]
    texto = (repo_copy / JSON_).read_text(encoding="utf-8")
    for proibido in ("generated_at", "timestamp", "now"):
        assert f'"{proibido}"' not in texto, f"{proibido} no artefato quebra o --check no dia seguinte"


# --------------------------------------------------------------------------------------
# 4–5. Vazio é estado de primeira classe, e a genericidade é o produto
# --------------------------------------------------------------------------------------

def test_genericidade_sem_o_negocio_de_exemplo(repo_copy, monkeypatch):
    """Relatório VAZIO E COERENTE, exit 0 — não traceback e não tela com buracos.

    É o que o `CP-000` do `/adotar` faz num derivado: remove o negócio de exemplo. Se o gerador
    assumisse "existe pelo menos uma capacidade", ele quebraria na PRIMEIRA tela que alguém abre
    num repositório recém-derivado.
    """
    import shutil
    shutil.rmtree(repo_copy / "business")
    shutil.rmtree(repo_copy / "design")
    (repo_copy / "architecture/components.yaml").unlink()

    assert _rodar(repo_copy, [], monkeypatch) == 0

    doc = json.loads((repo_copy / JSON_).read_text(encoding="utf-8"))
    assert doc["counts"]["capabilities"] == 0
    assert doc["counts"]["components"] == 0
    assert doc["empty_reasons"]["capabilities"] == "ainda não ingerido"
    assert "<html" in (repo_copy / HTML).read_text(encoding="utf-8")


def test_os_tres_vazios_NAO_saem_iguais(repo_copy, monkeypatch):
    """`declarado vazio` ≠ `ainda não ingerido`, e a distinção é a CP-040 inteira.

    Um diretório que existe e está vazio é uma AFIRMAÇÃO; um que não existe é trabalho pendente.
    Saindo iguais na tela, alguém avança achando que não há trabalho — e num derivado em incubação,
    que é quem mais abre esta tela, quase tudo cai no segundo caso (RISK-INCUBA-001, aberto).
    """
    import shutil
    shutil.rmtree(repo_copy / "business/rules")           # some ⇒ não ingerido
    (repo_copy / "harness/releases").mkdir(exist_ok=True)  # existe e vazio ⇒ declarado vazio

    assert _rodar(repo_copy, [], monkeypatch) == 0
    doc = json.loads((repo_copy / JSON_).read_text(encoding="utf-8"))

    assert doc["empty_reasons"]["rules"] == "ainda não ingerido"
    assert doc["empty_reasons"]["releases"] == "declarado vazio"
    assert doc["empty_reasons"]["rules"] != doc["empty_reasons"]["releases"]


def test_colecao_vazia_renderiza_com_a_RAZAO_do_vazio(repo_copy, monkeypatch):
    """Vazio se comunica com a razão, nunca com um `0` solto. O `0` é a tela que serve igual para
    "nada a declarar" e para "não sei olhar"."""
    import shutil
    shutil.rmtree(repo_copy / "business")

    assert _rodar(repo_copy, [], monkeypatch) == 0
    html = (repo_copy / HTML).read_text(encoding="utf-8")
    assert "ainda não ingerido" in html


# --------------------------------------------------------------------------------------
# 6–7. Não consegui fiscalizar NUNCA se parece com fiscalizei e passou
# --------------------------------------------------------------------------------------

def test_fonte_ilegivel_sai_DOIS(repo_copy, monkeypatch):
    """YAML corrompido ⇒ exit 2, jamais 0 e jamais 1.

    Os três códigos dizem coisas diferentes e confundi-los é o defeito: 0 é "olhei e está certo",
    1 é "olhei e está errado", 2 é "não consegui olhar". Um fiscal que devolve 0 quando não
    conseguiu ler responde "nada a ver aqui" para a pergunta que não chegou a fazer.
    """
    (repo_copy / "governance/risk-register.yaml").write_text("isto: [nao\n  fecha", encoding="utf-8")

    assert _rodar(repo_copy, ["--check", "--quiet"], monkeypatch) == 2
    assert _rodar(repo_copy, ["--quiet"], monkeypatch) == 2


def test_chave_ausente_nao_vira_lista_vazia(repo_copy, monkeypatch):
    """`.get(x) or []` transformaria *não declarado* em *declarado vazio*, e num fiscal essa
    diferença é a diferença entre indeterminação e permissão. É a CP-040 na sua forma mais direta."""
    alvo = repo_copy / "governance/risk-register.yaml"
    doc = alvo.read_text(encoding="utf-8")
    assert "risks:" in doc
    alvo.write_text(doc.replace("risks:", "riscos_renomeados:", 1), encoding="utf-8")

    assert _rodar(repo_copy, ["--quiet"], monkeypatch) == 2


def test_sem_pyyaml_sai_DOIS_com_o_proximo_passo(repo_copy, tmp_path):
    """Clone fresco sem as dependências ⇒ exit 2 e a instrução, nunca traceback com exit 1.

    Rodado em SUBPROCESSO porque a ausência precisa existir no momento do import do módulo — é lá
    que ela morde. Quem mais precisa desta mensagem é exatamente quem acabou de clonar, e um
    traceback devolve exit 1, que significa "encontrei divergência".
    """
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "yaml.py").write_text('raise ImportError("stub: pyyaml ausente")\n', encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(stub)
    env["HARNESS_REPO_ROOT"] = str(repo_copy)
    proc = subprocess.run([sys.executable, str(repo_copy / GERADOR), "--check"],
                          capture_output=True, text=True, env=env, cwd=str(repo_copy))

    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "pip install" in proc.stderr, proc.stderr


# --------------------------------------------------------------------------------------
# 8–9. AS MORDIDAS DE CLASSE — impedem a PRÓXIMA ocorrência, não só esta
# --------------------------------------------------------------------------------------

def test_identificador_literal_no_gerador_ACUSA(repo_copy, run_auditor):
    """Identificador como DADO no gerador ⇒ a asserção do ADR reprova.

    Esta é a trava que impede o gerador de deixar de derivar e passar a enumerar. Sem ela, a
    primeira lista escrita à mão entra sem barulho, e a partir dali existe uma segunda descrição do
    repositório que deriva da primeira em silêncio.
    """
    alvo = repo_copy / GERADOR
    alvo.write_text(alvo.read_text(encoding="utf-8")
                    + '\nCAPACIDADES_FIXAS = ["CAP-EXEMPLO", "CAP-OUTRA"]\n', encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1, [f["id"] for f in findings]
    assert any("ADR-031-A3" in str(f.get("assertion") or f.get("id")) for f in findings), \
        [f.get("assertion") or f.get("id") for f in findings]


def test_identificador_em_PROSA_nao_acusa(repo_copy, run_auditor):
    """O outro lado da asserção, e é o que a torna sustentável: identificador citado num comentário
    para EXPLICAR a regra continua permitido.

    Sem este teste, a correção óbvia para o teste anterior seria endurecer o padrão até proibir
    qualquer menção — e aí o gerador não poderia mais dizer por que suas regras existem, no lugar
    exato onde o próximo leitor procura. É a família âncora-na-menção que `conformance.md` registra
    com nove ocorrências, a última nascida dentro do fiscal escrito para vigiar as anteriores.
    """
    alvo = repo_copy / GERADOR
    alvo.write_text(alvo.read_text(encoding="utf-8")
                    + "\n# Ver CP-040 e RISK-INCUBA-001: é por isso que o vazio tem três estados.\n",
                    encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    ofensores = [f for f in findings
                 if "ADR-031-A3" in str(f.get("assertion") or f.get("id"))]
    assert not ofensores, ofensores


def test_leitor_de_yaml_paralelo_ACUSA(repo_copy, run_auditor):
    """Um segundo leitor ⇒ `import_forbidden` reprova.

    A regra mais importante do gerador, e a razão é a mesma do `orient.py`: ele não contém a
    informação, ele a deriva. Duas leituras da mesma fonte produzem duas respostas para a mesma
    pergunta no dia em que uma delas ganhar um tratamento que a outra não tem.
    """
    alvo = repo_copy / GERADOR
    texto = alvo.read_text(encoding="utf-8")
    alvo.write_text(texto.replace("import argparse", "import argparse\nimport yaml", 1),
                    encoding="utf-8")

    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1, [f["id"] for f in findings]
    assert any("ADR-031-A2" in str(f.get("assertion") or f.get("id")) for f in findings), \
        [f.get("assertion") or f.get("id") for f in findings]


# --------------------------------------------------------------------------------------
# A decisão de privacidade, que não pode ser default
# --------------------------------------------------------------------------------------

def test_redigir_troca_campos_do_inventario_por_CONTAGENS(repo_copy, monkeypatch):
    """Com inventário NÃO-vazio e `--redigir`, os campos não saem em claro.

    No molde o inventário está vazio, então testar contra ele provaria nada — a fixture injeta um
    inventário com dado real. Num derivado, este é o caso normal, e um HTML publicado com ele não
    vaza o dado do titular: vaza o MAPA de onde ele está, que é o que se procura primeiro.
    """
    inv = repo_copy / "governance/data-inventory.yaml"
    doc = inv.read_text(encoding="utf-8")
    doc = doc.replace("fields: []", 'fields:\n  - name: "email_do_titular"\n'
                                    '    purpose: "contato"\n    legal_basis: "consentimento"\n'
                                    '    owner: "CMP-EXEMPLO"\n', 1)
    inv.write_text(doc, encoding="utf-8")

    assert _rodar(repo_copy, ["--redigir", "--quiet"], monkeypatch) == 0
    html = (repo_copy / HTML).read_text(encoding="utf-8")
    corpo = json.loads((repo_copy / JSON_).read_text(encoding="utf-8"))

    assert "email_do_titular" not in html, "campo do inventário vazou para o artefato redigido"
    assert "email_do_titular" not in json.dumps(corpo, ensure_ascii=False)
    assert corpo["computed"]["inventory"]["redigido"] is True
    assert corpo["computed"]["inventory"]["total_campos"] >= 1, \
        "redigir troca por CONTAGEM — sumir com o número esconderia que há inventário"


def test_sem_redigir_o_inventario_aparece(repo_copy, monkeypatch):
    """O outro lado: redigir é DECISÃO, não comportamento silencioso. Se o modo padrão também
    escondesse, ninguém saberia que a redação estava acontecendo — e uma trava invisível não é
    auditável."""
    inv = repo_copy / "governance/data-inventory.yaml"
    doc = inv.read_text(encoding="utf-8")
    doc = doc.replace("fields: []", 'fields:\n  - name: "email_do_titular"\n'
                                    '    purpose: "contato"\n    legal_basis: "consentimento"\n'
                                    '    owner: "CMP-EXEMPLO"\n', 1)
    inv.write_text(doc, encoding="utf-8")

    assert _rodar(repo_copy, ["--quiet"], monkeypatch) == 0
    corpo = json.loads((repo_copy / JSON_).read_text(encoding="utf-8"))
    assert corpo["computed"]["inventory"]["redigido"] is False
    assert "email_do_titular" in json.dumps(corpo, ensure_ascii=False)


# --------------------------------------------------------------------------------------
# A trava sobre o próprio gerador: nenhum contador escrito na tela
# --------------------------------------------------------------------------------------

def test_nenhum_contador_literal_no_gerador():
    """Verificação rigorosa por AST, sobre constantes de string em CÓDIGO EXECUTÁVEL.

    A asserção `ADR-031-A3` ancora em aspas e por isso não alcança tudo; este teste alcança. Ele
    percorre a árvore, ignora docstrings e comentários (que não são nós `Constant` em contexto de
    expressão), e recusa identificador em qualquer literal de string.

    É a diferença entre proibir o FATO e proibir a MENÇÃO — o repositório já pagou nove vezes por
    confundir os dois.
    """
    import ast
    import re

    fonte = (REPO / GERADOR).read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            corpo = getattr(no, "body", [])
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
                docstrings.add(id(corpo[0].value))

    padrao = re.compile(r"\b[A-Z]{2,}-[A-Z0-9]{2,}")
    ofensores = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings:
            achado = padrao.search(no.value)
            if achado:
                ofensores.append((no.lineno, achado.group(0)))

    assert not ofensores, (
        f"identificador literal usado como DADO em {GERADOR}: {ofensores}. "
        f"O gerador não contém a informação, ele a deriva.")


def test_o_json_responde_ao_proprio_contrato(repo_copy, monkeypatch):
    """O JSON é a INTERFACE; validá-lo é parte do `--check`, não uma conferência manual.

    O HTML é a vista humana, mas quem consome estado do repositório sem parsear HTML — uma suíte,
    um CI de auditoria — lê o JSON. Um artefato que viola o schema que o descreve é uma interface
    quebrada com aparência de válida, e quem descobre é o consumidor, longe daqui.
    """
    import harness_lib as hl_local

    assert _rodar(repo_copy, [], monkeypatch) == 0
    doc = json.loads((repo_copy / JSON_).read_text(encoding="utf-8"))

    importlib.reload(hl_local)
    erros = hl_local.schema_errors(JSON_, "repo-report.schema.json", doc)
    assert not erros, erros


def test_relatorio_que_viola_o_contrato_sai_DOIS(repo_copy, monkeypatch):
    """E a trava morde: schema apertado de forma que o artefato real não satisfaça ⇒ exit 2.

    Exit 2 e não 1 de propósito — um artefato que contradiz o próprio contrato não é 'desatualizado',
    é indeterminado: não dá para dizer se o errado é o gerador ou o schema, e responder 1 escolheria
    uma das duas hipóteses sem base.
    """
    schema = repo_copy / "harness/schemas/repo-report.schema.json"
    doc = json.loads(schema.read_text(encoding="utf-8"))
    doc["required"] = list(doc["required"]) + ["campo_que_nao_existe"]
    schema.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    assert _rodar(repo_copy, ["--quiet"], monkeypatch) == 2
