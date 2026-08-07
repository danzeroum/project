"""Mordidas do painel de configuração (CP-050, ADR-031).

A mordida ÂNCORA é `test_enum_novo_aparece_sozinho`, e ela vale mais que todas as outras juntas.

A razão é o modo de falha deste painel em particular. No relatório de conteúdo, um dado velho
costuma ser visivelmente velho. Aqui não: um vocabulário transcrito continua renderizando perfeito
depois que o contrato mudou, e a tela passa a ensinar o que o repositório já não usa — sem erro,
sem aviso, sem nada ficar vermelho. Esta mordida é a única coisa que torna o painel seguro de
existir, e o que a torna âncora é a SEGUNDA asserção de cada uma das duas de classe: os bytes do
gerador têm de permanecer inalterados. Sem isso, elas provariam apenas que o pipeline rodou.

Idioma da casa: copiar o repositório para tmp_path, injetar UMA mutação, apontar o fiscal para a
cópia por HARNESS_REPO_ROOT. Nenhum teste toca a árvore de trabalho.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import recarregar_fiscais

REPO = Path(__file__).resolve().parent.parent.parent
HTML = "docs/configuracao/index.html"
DADOS = "docs/configuracao/config.json"
GERADOR = "ci/generate_config_report.py"


# ── utilidades ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def rodar(monkeypatch):
    """Roda o gerador contra uma cópia, recarregando o grafo de módulos dos fiscais."""

    def _run(root: Path, argv: list[str] | None = None) -> int:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        recarregar_fiscais()
        import generate_config_report
        importlib.reload(generate_config_report)
        return generate_config_report.main(list(argv or []) + ["--quiet"])

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    recarregar_fiscais()


def dados(root: Path) -> dict:
    return json.loads((root / DADOS).read_text(encoding="utf-8"))


def um_no_com(root: Path, chave: str) -> tuple[Path, dict, list]:
    """Acha, POR TRAVESSIA, o primeiro nó que tem `chave`.

    Escolher o alvo por travessia e não por nome de arquivo é o que faz esta mordida continuar
    valendo quando os contratos mudarem: ela não sabe qual contrato está mutando, e não precisa.
    """
    sys.path.insert(0, str(REPO / "ci"))
    import generate_config_report as gcr

    for caminho in sorted((root / "harness" / "schemas").glob("*.schema.json")):
        doc = json.loads(caminho.read_text(encoding="utf-8"))
        saida: list = []
        gcr.percorrer(doc, "", (), caminho.name, saida)
        for no in saida:
            if chave in no.node and isinstance(no.node.get(chave), list) and no.node[chave]:
                return caminho, doc, no.ponteiro.split("/")[1:]
    raise AssertionError(f"nenhum nó com {chave!r} — a travessia não achou o que devia")


def escrever(caminho: Path, doc: dict) -> None:
    caminho.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def desce(doc: dict, segmentos: list[str]):
    alvo = doc
    for seg in segmentos:
        seg = seg.replace("~1", "/").replace("~0", "~")
        alvo = alvo[int(seg)] if isinstance(alvo, list) else alvo[seg]
    return alvo


# ── as duas mordidas de classe ────────────────────────────────────────────────────────────────

def test_enum_novo_aparece_sozinho(repo_copy: Path, rodar):
    """A ÂNCORA. Um valor novo num contrato aparece na tela sem ninguém editar a tela.

    Se este teste falhar, a travessia é transcrição disfarçada e nada mais neste arquivo importa.
    """
    assert rodar(repo_copy) == 0
    antes = dados(repo_copy)
    fonte_antes = (repo_copy / GERADOR).read_bytes()

    caminho, doc, segmentos = um_no_com(repo_copy, "enum")
    alvo = desce(doc, segmentos)
    alvo["enum"].append("valor-sentinela")
    escrever(caminho, doc)

    assert rodar(repo_copy) == 0
    depois = dados(repo_copy)

    # 1. o valor aparece nos DOIS artefatos
    assert "valor-sentinela" in (repo_copy / DADOS).read_text(encoding="utf-8")
    assert "valor-sentinela" in (repo_copy / HTML).read_text(encoding="utf-8")

    # 2. e aparece no campo certo, tendo crescido em exatamente um — nunca uma contagem literal
    ptr = "/" + "/".join(segmentos)
    de_antes = [v for v in antes["vocabulary"] if v["pointer"] == ptr][0]
    de_depois = [v for v in depois["vocabulary"] if v["pointer"] == ptr][0]
    assert len(de_depois["values"]) == len(de_antes["values"]) + 1

    # 3. A ASSERÇÃO QUE FAZ DELA UMA ÂNCORA: nada no gerador mudou.
    assert (repo_copy / GERADOR).read_bytes() == fonte_antes, \
        "o valor só apareceu porque o gerador foi editado — isso é transcrição, não derivação"


def test_trava_nova_aparece_sozinha(repo_copy: Path, rodar):
    """Uma trava nova num contrato aparece na tela de travas, sintetizada, sem ninguém editá-la."""
    assert rodar(repo_copy) == 0
    fonte_antes = (repo_copy / GERADOR).read_bytes()
    antes = len(dados(repo_copy)["locks"])

    caminho = repo_copy / "harness" / "schemas" / "project.schema.json"
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    doc.setdefault("allOf", []).append({
        "comment": "porquê sentinela desta trava",
        "if": {"properties": {"schema_version": {"const": "9.9"}},
               "required": ["schema_version"]},
        "then": {"required": ["campo-sentinela"]},
    })
    escrever(caminho, doc)

    assert rodar(repo_copy) == 0
    travas = dados(repo_copy)["locks"]
    assert len(travas) == antes + 1

    nova = [t for t in travas if "campo-sentinela" in t["rule"]]
    assert nova, f"a trava nova não apareceu: {[t['pointer'] for t in travas][:5]}"
    nova = nova[0]

    # A regra foi SINTETIZADA: contém os dois lados do bloco, em prosa que o JSON não tinha.
    assert "9.9" in nova["rule"] and "campo-sentinela" in nova["rule"]
    assert nova["block_kind"] == "if/then"
    assert nova["why"] == "porquê sentinela desta trava"

    assert (repo_copy / GERADOR).read_bytes() == fonte_antes, \
        "a trava só apareceu porque o gerador foi editado"


# ── o --check ─────────────────────────────────────────────────────────────────────────────────

def test_artefato_vencido_reprova(repo_copy: Path, rodar):
    """Contrato editado sem regenerar: o --check contradiz, com exit 1."""
    assert rodar(repo_copy) == 0
    caminho, doc, segmentos = um_no_com(repo_copy, "enum")
    desce(doc, segmentos)["enum"].append("valor-sentinela")
    escrever(caminho, doc)
    assert rodar(repo_copy, ["--check"]) == 1


def test_artefato_editado_a_mao_reprova(repo_copy: Path, rodar):
    """A comparação é do ARQUIVO INTEIRO, não só do payload embutido."""
    assert rodar(repo_copy) == 0
    alvo = repo_copy / HTML
    alvo.write_text(alvo.read_text(encoding="utf-8") + "\n<!-- editado à mão -->\n",
                    encoding="utf-8")
    assert rodar(repo_copy, ["--check"]) == 1


def test_artefato_de_dados_editado_a_mao_reprova(repo_copy: Path, rodar):
    """O JSON é conferido junto: é a interface de máquina, e derivá-la sem vigiá-la seria pior."""
    assert rodar(repo_copy) == 0
    alvo = repo_copy / DADOS
    doc = json.loads(alvo.read_text(encoding="utf-8"))
    doc["vocabulary"] = doc["vocabulary"][:-1]
    alvo.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert rodar(repo_copy, ["--check"]) == 1


# ── determinismo ──────────────────────────────────────────────────────────────────────────────

def test_determinismo_apesar_do_ambiente(repo_copy: Path, rodar, monkeypatch):
    """Mesma árvore, mesmo byte — mesmo com o ambiente empurrando para o contrário.

    Um artefato que muda sozinho transforma o --check em gerador de ruído, e o remédio que as
    pessoas acabam escolhendo é desligá-lo.
    """
    assert rodar(repo_copy) == 0
    primeiro = (repo_copy / HTML).read_bytes()

    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    monkeypatch.setenv("GITHUB_REF_NAME", "outra-branch")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1")
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    assert rodar(repo_copy) == 0
    assert (repo_copy / HTML).read_bytes() == primeiro


def test_determinismo_com_hash_seed_diferente(repo_copy: Path, rodar):
    """PYTHONHASHSEED diferente pega iteração de `set` que escapou de um `sorted()`."""
    assert rodar(repo_copy) == 0
    esperado = (repo_copy / HTML).read_bytes()

    env = dict(os.environ, HARNESS_REPO_ROOT=str(repo_copy), PYTHONHASHSEED="12345",
               PYTHONPATH=str(repo_copy / "ci"))
    r = subprocess.run([sys.executable, str(repo_copy / GERADOR), "--quiet"],
                       cwd=repo_copy, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (repo_copy / HTML).read_bytes() == esperado


def test_ordem_de_chave_no_contrato_nao_muda_o_artefato(repo_copy: Path, rodar):
    """Reordenar as chaves de um contrato não muda o artefato.

    É o que força ordenar por PONTEIRO em vez de por ordem de encontro: ordem de chave de
    dicionário é ordem do arquivo em Python, e preservá-la faria um contrato semanticamente
    idêntico produzir bytes diferentes.
    """
    assert rodar(repo_copy) == 0
    antes = dados(repo_copy)

    for caminho in sorted((repo_copy / "harness" / "schemas").glob("*.schema.json")):
        doc = json.loads(caminho.read_text(encoding="utf-8"))
        escrever(caminho, {k: doc[k] for k in reversed(list(doc))})

    assert rodar(repo_copy) == 0
    depois = dados(repo_copy)

    # As coleções DERIVADAS são idênticas. O que muda é só o que é função do conteúdo do arquivo
    # — tamanho em bytes e a impressão das entradas —, e mudar aí é o comportamento correto: um
    # arquivo diferente TEM que ter impressão diferente, senão a procedência não serviria para
    # nada. A invariante é sobre a derivação, não sobre o disco.
    for colecao in ("vocabulary", "grammar", "consts", "locks"):
        assert depois[colecao] == antes[colecao], f"{colecao} reordenou com a ordem do arquivo"
    assert depois["provenance"]["inputs_fingerprint"] != antes["provenance"]["inputs_fingerprint"]


# ── classificação e distinções ────────────────────────────────────────────────────────────────

def test_const_condicional_vai_para_travas_nao_para_valores(repo_copy: Path, rodar):
    """`const` dentro de `if` é PREDICADO de uma trava, não valor travado.

    Tratá-lo como valor criaria dezenas de cards falsos, cada um afirmando que o repositório fixou
    algo que na verdade ele só usa como condição.
    """
    assert rodar(repo_copy) == 0
    d = dados(repo_copy)
    ponteiros_de_valor = {c["pointer"] for c in d["consts"]}
    condicionais = [p for p in ponteiros_de_valor
                    if any(seg in p.split("/") for seg in ("if", "then", "else", "not"))]
    assert not condicionais, f"const de predicado listado como valor travado: {condicionais}"


def test_escalas_homonimas_nao_sao_fundidas(repo_copy: Path, rodar):
    """A mesma escala em contratos diferentes aparece uma vez POR PONTEIRO.

    Deduplicar por valor as fundiria numa só e apagaria a informação de que são escalas distintas
    — que é justamente o que o leitor precisa saber.
    """
    assert rodar(repo_copy) == 0
    vocab = dados(repo_copy)["vocabulary"]

    por_valores: dict[tuple, list[str]] = {}
    for v in vocab:
        por_valores.setdefault(tuple(sorted(map(str, v["values"]))), []).append(v["pointer"])
    repetidas = [ps for ps in por_valores.values() if len(ps) > 1]
    assert repetidas, "nenhuma escala repetida no repositório — a mordida perdeu o alvo"
    assert any(len(set(ps)) > 1 for ps in repetidas), \
        "as escalas homônimas foram fundidas: sobrou um ponteiro só para valores idênticos"

    # A chave de deduplicação é (arquivo, ponteiro). Só o ponteiro não basta: `/properties/
    # schema_version` existe em quase todo contrato, e são campos diferentes de documentos
    # diferentes — colapsá-los seria a mesma fusão, num eixo mais fácil de não perceber.
    chaves = {(v["file"], v["pointer"]) for v in vocab}
    assert len(chaves) == len(vocab), "vocabulário deduplicado por valor"


def test_exemplo_de_pattern_existe_de_fato_no_repositorio(repo_copy: Path, rodar):
    """Todo exemplo mostrado é um valor REAL. Nenhum é sintético — a coluna some em vez disso."""
    assert rodar(repo_copy) == 0
    d = dados(repo_copy)

    # A mesma lista de documentos que o gerador usa, pela mesma razão que ele a usa: manter uma
    # segunda lista aqui faria a mordida passar ou falhar conforme quem a atualizou por último.
    sys.path.insert(0, str(REPO / "ci"))
    import validate_metadata

    bruto = "".join(
        (repo_copy / rel).read_text(encoding="utf-8")
        for rel, _schema in validate_metadata.DOCS if (repo_copy / rel).exists())
    for g in d["grammar"]:
        if "example" in g:
            assert g["example"] in bruto, \
                f"exemplo {g['example']!r} não existe no repositório — é sintético"


def test_contrato_novo_sem_grupo_reprova(repo_copy: Path, rodar):
    """Um contrato não classificado ACUSA, em vez de sumir da tela."""
    assert rodar(repo_copy) == 0
    (repo_copy / "harness" / "schemas" / "zz-sentinela.schema.json").write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema",
                    "title": "sentinela", "type": "object"}), encoding="utf-8")
    assert rodar(repo_copy) == 2


def test_entrada_morta_no_agrupamento_reprova(repo_copy: Path, rodar):
    """O inverso acusa igual: mapa que guarda contrato apagado faz a classificação parecer
    completa por uma razão que já não existe."""
    assert rodar(repo_copy) == 0
    (repo_copy / "harness" / "schemas" / "vision.schema.json").unlink()
    assert rodar(repo_copy) == 2


def test_variavel_negada_fora_de_familia_reprova(repo_copy: Path, rodar):
    """Variável negada nova que caia fora dos blocos declarados ACUSA, em vez de sumir."""
    assert rodar(repo_copy) == 0
    alvo = repo_copy / "harness" / "harness.yaml"
    texto = alvo.read_text(encoding="utf-8")
    texto = texto.replace("  env_denylist_exact:\n",
                          "  env_denylist_exact:\n    - LD_PRELOAD\n", 1)
    alvo.write_text(texto, encoding="utf-8")
    assert rodar(repo_copy) == 2


# ── o fiscal cego ─────────────────────────────────────────────────────────────────────────────

def test_contrato_ilegivel_sai_2_e_nao_encolhe_a_tela(repo_copy: Path, rodar):
    """O modo de falha mais perigoso deste painel: uma seção que encolhe em silêncio.

    Um contrato corrompido NÃO pode virar "esse arquivo não tem valores" — a tela continuaria
    bonita e menor. Vira exit 2, e o artefato anterior fica intacto.
    """
    assert rodar(repo_copy) == 0
    antes = (repo_copy / DADOS).read_bytes()
    (repo_copy / "harness" / "schemas" / "project.schema.json").write_text(
        "{ isto não é json", encoding="utf-8")

    assert rodar(repo_copy) == 2
    assert (repo_copy / DADOS).read_bytes() == antes, \
        "o artefato foi reescrito menor a partir de uma leitura que falhou"


def test_valor_de_vocabulario_transcrito_reprova(repo_copy: Path, rodar):
    """A autoauditoria morde. O valor injetado é TIRADO do vocabulário derivado, nunca digitado —
    digitá-lo faria a própria mordida transcrever aquilo que ela existe para proibir."""
    assert rodar(repo_copy) == 0
    valor = next(v for item in dados(repo_copy)["vocabulary"]
                 for v in item["values"] if isinstance(v, str) and len(v) > 6)

    alvo = repo_copy / GERADOR
    fonte = alvo.read_text(encoding="utf-8")
    alvo.write_text(fonte.replace("def coletar()",
                                  f"_TRANSCRICAO = [{valor!r}]\n\n\ndef coletar()", 1),
                    encoding="utf-8")
    assert rodar(repo_copy) == 2


def test_sem_dependencias_sai_2_com_o_proximo_passo(repo_copy: Path):
    """Ambiente sem as dependências: exit 2 e a instrução, jamais 0.

    Usa a exceção DECLARADA de PYTHONPATH (harness.yaml:env_hygiene.exceptions): rodar um fiscal
    contra uma cópia com stubs exige apontar o interpretador para ela.
    """
    stubs = repo_copy / "_stubs"
    stubs.mkdir()
    (stubs / "jsonschema.py").write_text(
        "raise ImportError('jsonschema ausente')", encoding="utf-8")

    env = dict(os.environ, HARNESS_REPO_ROOT=str(repo_copy),
               PYTHONPATH=f"{stubs}{os.pathsep}{repo_copy / 'ci'}")
    r = subprocess.run([sys.executable, str(repo_copy / GERADOR), "--check"],
                       cwd=repo_copy, env=env, capture_output=True, text=True)
    assert r.returncode == 2, f"saiu {r.returncode}: {r.stdout}{r.stderr}"
    assert "bootstrap" in r.stderr


# ── genericidade ──────────────────────────────────────────────────────────────────────────────

def test_colecao_vazia_renderiza_com_a_razao(repo_copy: Path, rodar):
    """Sem fichas de régua: a tela renderiza com a razão do vazio, exit 0, e nenhum traceback."""
    assert rodar(repo_copy) == 0
    for p in (repo_copy / "harness" / "suites").glob("*.yaml"):
        p.unlink()

    assert rodar(repo_copy) == 0
    d = dados(repo_copy)
    assert d["suites"]["registry"] == []
    assert d["empty_reasons"].get("registry"), "vazio sem razão declarada é um zero que mente"
    assert d["empty_reasons"]["registry"] in (repo_copy / HTML).read_text(encoding="utf-8")


def test_registro_de_regua_ausente_e_diferente_de_vazio(repo_copy: Path, rodar):
    """A outra metade, e ela não pode ter a mesma cor: diretório AUSENTE é fail-closed.

    `prefixos_efetivos` não devolve o que conseguiu ler — a família inteira de uma régua sairia da
    denylist porque um diretório sumiu.
    """
    assert rodar(repo_copy) == 0
    import shutil
    shutil.rmtree(repo_copy / "harness" / "suites")
    assert rodar(repo_copy) == 2


def test_sem_instancias_a_coluna_de_exemplo_some(repo_copy: Path, rodar):
    """Num repositório sem instâncias, o exemplo é OMITIDO — nunca inventado."""
    for rel in ("business/capabilities.yaml", "architecture/components.yaml",
                "architecture/interfaces.yaml"):
        alvo = repo_copy / rel
        if alvo.exists():
            alvo.write_text("schema_version: '1.0'\nmetadata_version: '1.0'\n"
                            "source_of_truth: true\ngenerated_from: null\n", encoding="utf-8")

    assert rodar(repo_copy) == 0
    d = dados(repo_copy)
    assert d["grammar"], "a gramática sumiu inteira — a travessia parou de derivar"
    for g in d["grammar"]:
        assert "example" not in g or g["example"], "exemplo vazio em vez de coluna omitida"


# ── invariantes de forma ──────────────────────────────────────────────────────────────────────

def test_ponteiros_publicados_resolvem(repo_copy: Path, rodar):
    """Todo ponteiro na tela é um endereço que o leitor consegue usar de fato."""
    assert rodar(repo_copy) == 0
    sys.path.insert(0, str(REPO / "ci"))
    import harness_lib as hl

    d = dados(repo_copy)
    for item in d["vocabulary"][:40] + d["locks"][:40]:
        doc = json.loads((repo_copy / "harness" / "schemas" / item["file"])
                         .read_text(encoding="utf-8"))
        assert hl.json_pointer(doc, item["pointer"]) is not None


def test_artefato_nao_se_declara_fonte_de_verdade(repo_copy: Path, rodar):
    assert rodar(repo_copy) == 0
    d = dados(repo_copy)
    assert d["source_of_truth"] is False
    assert d["generated_from"]
    assert d["provenance"]["commit"]["embedded"] is False


def test_artefato_abre_offline(repo_copy: Path, rodar):
    """Nada no HTML busca recurso na rede — o painel abre de file:// sem rede."""
    assert rodar(repo_copy) == 0
    html = (repo_copy / HTML).read_text(encoding="utf-8")
    assert "@import" not in html
    import re
    assert not re.search(r"<(?:link|script|img|iframe)[^>]*\b(?:src|href)\s*=", html)


def test_casca_tem_todos_os_pontos_de_montagem(repo_copy: Path, rodar):
    """Todo `getElementById` do renderer encontra um alvo na casca.

    Escrita depois de a página sair EM BRANCO com tudo verde: 566 testes passavam, o --check
    estava em dia, as mutações mordiam — e o `<body>` só tinha os dois `<script>`. Um
    getElementById sem alvo não degrada, ele levanta na primeira chamada, e o arquivo inteiro
    continua lá, com o tamanho certo, sem renderizar nada.

    Confere estaticamente porque o gate não pode depender de navegador: o CI deste repositório é
    Python puro por decisão (ADR-009), e uma trava que exige Chromium é uma trava que não roda.
    """
    assert rodar(repo_copy) == 0
    html = (repo_copy / HTML).read_text(encoding="utf-8")

    import re
    procurados = set(re.findall(r"getElementById\('([^']+)'\)", html))
    assert procurados, "o renderer não procura elemento algum — a leitura da mordida quebrou"
    existentes = set(re.findall(r'id="([^"]+)"', html))
    assert procurados <= existentes, \
        f"o renderer procura pontos de montagem que a casca não tem: {procurados - existentes}"


def test_link_para_o_painel_irmao_e_condicional(repo_copy: Path, rodar):
    """O relatório de conteúdo não existe neste repositório. A tela não finge que existe.

    Um link fixo para artefato ausente é a mesma mentira em miniatura que o painel inteiro existe
    para não cometer — e o dia em que o irmão for construído, o link aparece sozinho.
    """
    assert rodar(repo_copy) == 0
    assert not (repo_copy / "docs" / "relatorio" / "index.html").exists()
    assert "../relatorio/index.html" not in (repo_copy / HTML).read_text(encoding="utf-8")

    alvo = repo_copy / "docs" / "relatorio"
    alvo.mkdir(parents=True)
    (alvo / "index.html").write_text("<!-- irmão -->", encoding="utf-8")
    assert rodar(repo_copy) == 0
    assert "../relatorio/index.html" in (repo_copy / HTML).read_text(encoding="utf-8")


def test_contagem_de_fiscais_vem_de_steps(repo_copy: Path, rodar):
    """A contagem de agregados é derivada de _steps(), e cresce sozinha quando ele cresce.

    É a armadilha que este próprio trabalho armou: acrescentar o painel ao agregado mudou o
    número, e um literal em qualquer lugar teria feito a tela mentir no dia seguinte ao merge.
    """
    assert rodar(repo_copy) == 0
    antes = len(dados(repo_copy)["fiscais"]["aggregated"])

    alvo = repo_copy / "ci" / "validate_all.py"
    fonte = alvo.read_text(encoding="utf-8")
    alvo.write_text(fonte.replace(
        '        ("metadados", validate_metadata.main, []),',
        '        ("metadados", validate_metadata.main, []),\n'
        '        ("sentinela", validate_metadata.main, []),', 1), encoding="utf-8")

    assert rodar(repo_copy) == 0
    d = dados(repo_copy)
    assert len(d["fiscais"]["aggregated"]) == antes + 1
    assert any(f["step"] == "sentinela" for f in d["fiscais"]["aggregated"])
    assert str(antes + 1) in (repo_copy / HTML).read_text(encoding="utf-8")


def test_steps_ilegivel_sai_2(repo_copy: Path, rodar):
    """_steps() fora do alcance da máquina é 'não consegui', jamais 'zero fiscais'."""
    assert rodar(repo_copy) == 0
    alvo = repo_copy / "ci" / "validate_all.py"
    fonte = alvo.read_text(encoding="utf-8")
    inicio = fonte.index("def _steps()")
    fim = fonte.index("def main(")
    alvo.write_text(fonte[:inicio] + "def _steps():\n    return list(_MONTADO)\n\n\n"
                    + fonte[fim:], encoding="utf-8")
    assert rodar(repo_copy) == 2
