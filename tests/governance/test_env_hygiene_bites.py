"""Mordidas da higiene de ambiente estendida (CP-025 / ADR-018).

`violacoes` recebe o ambiente como DICIONÁRIO em vez de ler `os.environ`, e isso não é preferência
de estilo: um teste que dependesse do ambiente real passaria ou falharia conforme a máquina — e o
sandbox onde este repositório é desenvolvido tem proxy definido, então metade destes testes
"passaria" por acidente e a outra metade falharia sem defeito nenhum. Ambiente como argumento é o
que torna a trava testável em qualquer lugar.
"""

from __future__ import annotations

import ast
import json
import re
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


# --------------------------------------------------------------------------------------
# Os TRÊS estados da política (CP-040) — chave ausente não é lista vazia
# --------------------------------------------------------------------------------------

def _ficha_minima(raiz: Path, prefixo: str = "WEBQA_") -> None:
    """O registro de suites, que desde o CP-041 é de onde os prefixos derivam.

    Um repositório sintético sem ele não é um repositório sintético mais simples — é um que a
    trava recusa, e com razão: some o registro, some a denylist derivada. Os testes abaixo querem
    exercer as DUAS famílias da denylist, então o registro precisa existir para que a ausência
    dele não seja a coisa medida. Quem mede a ausência é o teste próprio, logo abaixo.
    """
    (raiz / "harness/suites").mkdir(parents=True, exist_ok=True)
    (raiz / "harness/suites/qa-suite.yaml").write_text(
        yaml.safe_dump({"schema_version": "1.0", "metadata_version": "1.0",
                        "source_of_truth": True, "generated_from": None,
                        "suite": {"nome": "qa-suite", "env_prefix": prefixo}},
                       allow_unicode=True, sort_keys=False), encoding="utf-8")


def _hook_isolado(tmp_path: Path, harness_doc: dict, com_registro: bool = True) -> Path:
    """Uma cópia do hook num repositório sintético, com o harness.yaml que o teste quiser.

    O hook resolve a raiz a partir do PRÓPRIO arquivo (`__file__`), e é justamente por isso que a
    cópia é necessária: apontar variável de ambiente para outra raiz não mudaria o documento que
    ele lê. Foi essa mesma resolução que produziu o defeito no derivado real — o hook mordia, e
    quem via a mordida concluía que a política dali estava no lugar, quando a política lida era a
    do molde.
    """
    raiz = tmp_path / "repo"
    (raiz / "ci/hooks").mkdir(parents=True)
    (raiz / "harness").mkdir(parents=True)
    (raiz / "ci/hooks/pre_bash_env_hygiene.py").write_bytes(
        (REPO / "ci/hooks/pre_bash_env_hygiene.py").read_bytes())
    (raiz / "harness/harness.yaml").write_text(
        yaml.safe_dump(harness_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if com_registro:
        _ficha_minima(raiz)
    return raiz / "ci/hooks/pre_bash_env_hygiene.py"


def _rodar(hook: Path, comando: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"tool_input": {"command": comando}}),
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})


def test_chave_ausente_e_indeterminacao_e_nao_permissao(tmp_path: Path):
    """O fail-open que estava aberto no primeiro derivado real.

    Sem `env_denylist_exact` no harness.yaml, o hook fazia `.get(...) or []`, lia lista vazia e
    DEIXAVA PASSAR. O idioma transforma "não declarado" em "declarado vazio", e num fiscal essa é a
    distância entre indeterminação e permissão. Que o schema exija a chave não salva ninguém: o
    schema fiscaliza o DOCUMENTO, e o hook lê o documento sem passar por ele.
    """
    hook = _hook_isolado(tmp_path, {"env_hygiene": {"env_denylist_prefix": ["WEBQA_"]}})
    proc = _rodar(hook, "PYTHONPATH=/tmp/meu python ci/validate_all.py")
    assert proc.returncode == 2, proc.stdout
    assert "FISCAL_CEGO" in proc.stderr
    assert "env_denylist_exact" in proc.stderr


def test_chave_ausente_para_o_comando_limpo_tambem(tmp_path: Path):
    """Cego é cego. Um hook que só reclamasse ao ver algo suspeito ainda estaria decidindo com a
    política ausente — e "não vi nada de errado" sem saber o que procurar é a frase que o exit 2
    existe para não deixar ninguém dizer."""
    hook = _hook_isolado(tmp_path, {"env_hygiene": {"env_denylist_prefix": ["WEBQA_"]}})
    proc = _rodar(hook, "python ci/validate_all.py")
    assert proc.returncode == 2, proc.stdout
    assert "FISCAL_CEGO" in proc.stderr


def test_chave_presente_volta_a_decidir_normalmente(tmp_path: Path):
    """O par positivo, no MESMO repositório sintético: o que muda entre este teste e os dois
    acima é uma linha do harness.yaml, e nada mais."""
    doc = {"env_hygiene": {"env_denylist_prefix": ["WEBQA_"],
                           "env_denylist_exact": ["PYTHONPATH", "HTTP_PROXY"]}}
    hook = _hook_isolado(tmp_path, doc)
    assert _rodar(hook, "PYTHONPATH=/tmp/meu python x.py").returncode == 2
    assert "DENIED_ENV" in _rodar(hook, "PYTHONPATH=/tmp/meu python x.py").stderr
    assert _rodar(hook, "python ci/validate_all.py").returncode == 0


def test_o_prefixo_tambem_morde_com_a_politica_completa(tmp_path: Path):
    """A família antiga não pode ter sido perdida ao ler a política de uma vez só."""
    doc = {"env_hygiene": {"env_denylist_prefix": ["WEBQA_"],
                           "env_denylist_exact": ["PYTHONPATH"]}}
    proc = _rodar(_hook_isolado(tmp_path, doc), "WEBQA_LOAD_AUTHORIZED=1 python x.py")
    assert proc.returncode == 2
    assert "DENIED_ENV" in proc.stderr, proc.stderr


def test_prefixo_derivado_da_ficha_morde_sem_estar_no_harness_yaml(tmp_path: Path):
    """CP-041: o prefixo da régua vem do REGISTRO, e `harness.yaml` não o restata.

    O par positivo da derivação: `env_denylist_prefix` vazio, e mesmo assim `PRIVSUITE_*` é
    negado — porque uma ficha o declara. É a diferença entre uma denylist que cresce à mão e uma
    que nasce coberta.
    """
    doc = {"env_hygiene": {"env_denylist_prefix": [], "env_denylist_exact": ["PYTHONPATH"]}}
    hook = _hook_isolado(tmp_path, doc, com_registro=False)
    _ficha_minima(hook.parent.parent.parent, prefixo="PRIVSUITE_")
    proc = _rodar(hook, "PRIVSUITE_SCAN_AUTHORIZED=1 python x.py")
    assert proc.returncode == 2
    assert "DENIED_ENV" in proc.stderr, proc.stderr


def test_registro_ausente_e_indeterminacao_no_hook(tmp_path: Path):
    """E o fail-closed do outro lado: sem registro, o hook não decide — ele para.

    Devolver o que conseguiu ler faria o hook liberar `WEBQA_*` em silêncio no dia em que o
    registro sumisse ou um YAML quebrasse. É a mesma lição da chave ausente, um nível acima: agora
    a fonte da lista é que pode faltar.
    """
    doc = {"env_hygiene": {"env_denylist_prefix": [], "env_denylist_exact": ["PYTHONPATH"]}}
    proc = _rodar(_hook_isolado(tmp_path, doc, com_registro=False), "python x.py")
    assert proc.returncode == 2
    assert "FISCAL_CEGO" in proc.stderr
    assert "harness/suites" in proc.stderr


def test_politica_incompleta_nao_produz_veredito_parcial(tmp_path: Path):
    """Com metade da política ausente, nem a metade presente emite veredito — e é deliberado.

    Seria tentador deixar a mordida por prefixo passar na frente: ela funcionaria, e o comando
    seria bloqueado do mesmo jeito. Mas `DENIED_ENV` afirma "olhei o que havia para olhar e foi
    isto que achei", e essa frase é falsa quando metade da política não foi lida. Um bloqueio certo
    com justificativa errada ensina a coisa errada a quem lê — e o que se aprende ali é que a
    política estava inteira.
    """
    hook = _hook_isolado(tmp_path, {"env_hygiene": {"env_denylist_prefix": ["WEBQA_"]}})
    proc = _rodar(hook, "WEBQA_LOAD_AUTHORIZED=1 python x.py")
    assert proc.returncode == 2
    assert "FISCAL_CEGO" in proc.stderr, proc.stderr
    assert "DENIED_ENV" not in proc.stderr


def test_default_embutido_na_denylist_deixou_de_existir():
    """`or ["WEBQA_"]` era uma SEGUNDA fonte da lista dentro do código.

    Pior que a lista vazia por um motivo a mais: além de apagar a ausência da chave, ela derivaria
    da lista real no dia em que alguém acrescentasse um prefixo ao harness.yaml e não a este
    arquivo — a fonte paralela de sempre, escondida num valor default.
    """
    assert 'or ["WEBQA_"]' not in _codigo_executavel("ci/hooks/pre_bash_env_hygiene.py")


# --------------------------------------------------------------------------------------
# A mordida de CLASSE — o idioma, não a ocorrência
# --------------------------------------------------------------------------------------

def _codigo_executavel(rel: str) -> str:
    """O arquivo sem a prosa: comentários e docstrings fora.

    Mesma distinção que `test_workflows_nao_duplicam_a_lista` já fazia, estendida ao que este lote
    tornou necessário. Um fiscal corrigido EXPLICA o defeito que corrigiu, e explicar exige citar o
    idioma proibido — a docstring de `PoliticaAusente` em post_edit_guard.py cita, palavra por
    palavra, o encadeamento que ela descreve. Acusar essa citação seria a armadilha de sempre nesta
    casa: ancorar na MENÇÃO em vez do FATO, e o preço seria proibir que a correção seja explicada
    onde o próximo leitor procura o porquê.
    """
    arvore = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    prosa: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            prosa.update(range(no.lineno, (no.end_lineno or no.lineno) + 1))
    return "\n".join(
        "" if (n in prosa or l.lstrip().startswith("#")) else l
        for n, l in enumerate((REPO / rel).read_text(encoding="utf-8").splitlines(), start=1))


def _chaves_exigidas_pelo_schema() -> set[str]:
    """As chaves que o SCHEMA marca `required`, derivadas dele e nunca redigitadas.

    É esta derivação que torna a mordida de classe não-arbitrária. A fronteira entre "ausência é
    indeterminação" e "ausência é vazio" não é gosto de quem escreve o fiscal: é o que o documento
    já promete. Chave `required` ausente significa que o documento está fora do próprio schema —
    indeterminação. Chave opcional ausente (`exceptions`) significa exatamente o que o silêncio diz
    — nenhuma exceção declarada, um estado legítimo e completo.

    E a lista cresce sozinha: uma chave nova marcada `required` no schema nasce coberta por este
    teste, sem ninguém lembrar de acrescentá-la aqui.
    """
    schema = json.loads((REPO / "harness/schemas/harness.schema.json").read_text(encoding="utf-8"))
    exigidas = set(schema.get("required") or [])
    for bloco in ("env_hygiene", "repository"):
        exigidas |= set((schema["properties"].get(bloco) or {}).get("required") or [])
    return exigidas


CHAVES_EXIGIDAS = _chaves_exigidas_pelo_schema()

# Leitores de política: os arquivos que decidem BLOQUEIO a partir do documento declarado. A lista é
# explícita e curta de propósito — varrer `ci/` inteiro varreria também os lugares onde o idioma é
# legítimo, e um teste que acusa o uso legítimo é um teste que alguém afrouxa.
LEITORES_DE_POLITICA = (
    "ci/hooks/pre_bash_env_hygiene.py",
    "ci/hooks/post_edit_guard.py",
    "ci/env_guard.py",
)


def _idioma(chave: str) -> re.Pattern:
    return re.compile(rf"""\.get\(\s*["']{re.escape(chave)}["']\s*\)\s+or\s+(\[\]|\{{\}}|set\(\))""")


@pytest.mark.parametrize("rel", LEITORES_DE_POLITICA)
def test_leitor_de_politica_nao_transforma_ausencia_em_lista_vazia(rel: str):
    """A CLASSE do defeito, e não a ocorrência que foi encontrada.

    Corrigir só `denied_exact` deixaria o idioma vivo nos vizinhos — e deixou: escrito primeiro
    contra o hook, este teste acusou `ci/env_guard.py` e `ci/hooks/post_edit_guard.py` na primeira
    execução. No env_guard o efeito era o mais eloquente de todos: sem as chaves, ele imprimia
    "✓ higiene de ambiente: 0 regra(s) da denylist, nenhuma violada" e saía 0. No post_edit_guard,
    `protected_paths` ausente liberava a edição de qualquer caminho protegido.

    Onde o valor alimenta uma decisão de bloqueio, ausência tem de ser distinguível de vazio.
    Se um uso legítimo do idioma aparecer num destes arquivos, o conserto é dar-lhe um nome que
    declare a opcionalidade (`_opcional`), não afrouxar este teste.
    """
    codigo = _codigo_executavel(rel)
    achados = [c for c in CHAVES_EXIGIDAS if _idioma(c).search(codigo)]
    assert not achados, (
        f"{rel} usa `.get(\"{achados[0]}\") or []` numa decisão de bloqueio, e o schema marca essa "
        f"chave como required: 'não declarado' e 'declarado vazio' passam a sair iguais, e o "
        f"segundo deixa passar")


def test_a_mordida_de_classe_pegaria_o_defeito_original():
    """O teste do teste. Sem esta prova, o regex acima poderia estar errado e o parametrize passaria
    em silêncio — verde por não casar nada é o modo de falha que este repositório persegue.
    """
    assert "env_denylist_exact" in CHAVES_EXIGIDAS
    assert "protected_paths" in CHAVES_EXIGIDAS
    assert "exceptions" not in CHAVES_EXIGIDAS, (
        "`exceptions` é opcional no schema: se virar required, o `_opcional` de env_guard.py "
        "precisa mudar junto")

    original = '    return _politica().get("env_denylist_exact") or []'
    assert _idioma("env_denylist_exact").search(original)
    assert not _idioma("env_denylist_exact").search(
        '    return politica["env_denylist_exact"] or []')
    assert not _idioma("env_denylist_exact").search('    return politica.get(chave) or []'), (
        "o acesso por VARIÁVEL é o helper nomeado, cujo contrato está declarado num lugar só")


def test_denylist_vazia_reprova_no_schema():
    """minItems 1 faz esvaziar a lista ser tão visível quanto remover a chave — e esvaziar é o
    gesto mais provável de quem quer desligar a trava sem parecer que a removeu."""
    import harness_lib as hl

    doc = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    doc["env_hygiene"]["env_denylist_exact"] = []
    assert hl.schema_errors("harness.yaml", "harness.schema.json", doc)
