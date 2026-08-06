"""Mordidas da CP-039 — as três lacunas que só apareceram quando um derivado TERMINOU.

A CP-038 trouxe o que aparece quando um consumidor começa. Estas três apareceram quando
`danzeroum/projectCockpitDocker` fechou a ingestão dele: extraiu a própria harness para um
repositório e passou a consumi-la por pin de SHA — a coisa certa, e a que este molde prega.

Cada bloco tem PAR: o caso que prova que o fiscal acusa, e o caso que prova que ele não acusa o
que é legítimo. Fiscal que só se testa pelo lado que reprova é fiscal cuja permissividade ninguém
mediu.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "ci"))

import harness_lib as hl  # noqa: E402
import validate_metadata as vm  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════════════════
# (1a) A referência direta PEP 508 — a forma mais perigosa era a única invisível
# ══════════════════════════════════════════════════════════════════════════════════════════

def _nome(linha: str) -> str | None:
    m = vm._DEP_PYPROJECT.match(linha)
    return m.group(1) if m else None


def test_DEPENDENCIA_GIT_e_reconhecida_como_declarada():
    """A mordida que a CP-039 existe para instalar.

    Antes, o regex aceitava só `[<>=!~]` depois do nome. Uma dependência `nome @ git+url` — código
    arbitrário de um host qualquer, sem índice e sem assinatura — não era vista como DECLARADA, e
    o efeito invertia o fiscal: quem a inventariasse corretamente em security/dependencies.yaml
    levava achado de "entrada morta"; quem NÃO a inventariasse não levava achado nenhum.
    """
    linha = '    "cockpit-harness @ git+https://github.com/o/r@9522f0dbf4c308648189a999f095393e439067b2",'
    assert _nome(linha) == "cockpit-harness", (
        "a referência direta voltou a ser invisível — o inventário de supply chain deixa passar "
        "justamente a forma que mais precisa ser vista")


@pytest.mark.parametrize("linha,esperado", [
    ('    "pyyaml>=6",', "pyyaml"),
    ('    "webqa-suite==1.0.0",', "webqa-suite"),
    ('    "httpx[http2]>=0.27.2",', "httpx"),
    ('    "cockpit-harness @ git+https://h/r@abc",', "cockpit-harness"),
    ('    "pytest >= 8"', "pytest"),
])
def test_as_formas_legitimas_da_PEP_508_continuam_reconhecidas(linha, esperado):
    """O outro lado do par. Alargar o regex para aceitar `@` não pode ter quebrado as formas
    antigas — se tivesse, o fiscal passaria a não ver dependências que ele via ontem, e a
    regressão apareceria como 'entrada morta' em repositório nenhum mudou."""
    assert _nome(linha) == esperado


@pytest.mark.parametrize("linha", [
    '    "not a package name",',
    '# "comentado>=1",',
    'dependencies = [',
    '    build-backend = "setuptools.build_meta"',
])
def test_o_que_NAO_e_declaracao_de_dependencia_continua_fora(linha):
    """Alargar não pode virar aceitar tudo: um regex que casasse qualquer string com aspas
    encheria o inventário de nomes inventados, e cada um viraria um achado falso que empurra
    alguém a apagar a checagem."""
    assert _nome(linha) is None


def test_o_inventario_deste_repositorio_e_reconhecido_por_inteiro():
    """Contra o repositório real, não contra fixture: toda dependência inventariada em
    security/dependencies.yaml é encontrada por _declaradas(). Se este cair, a mudança do regex
    quebrou o elo nos dois sentidos que check_dependency_inventory confere."""
    import yaml
    inv = yaml.safe_load((RAIZ / "security/dependencies.yaml").read_text(encoding="utf-8"))
    declaradas = vm._declaradas()
    faltando = [d["name"].lower() for d in inv["dependencies"]
                if d["name"].lower() not in declaradas]
    assert not faltando, f"inventariadas e não reconhecidas como declaradas: {faltando}"


# ══════════════════════════════════════════════════════════════════════════════════════════
# (1b) O controle que vive numa dependência pinada
# ══════════════════════════════════════════════════════════════════════════════════════════

def _schema_risco() -> dict:
    return json.loads((RAIZ / "harness/schemas/risk-register.schema.json").read_text(encoding="utf-8"))


def _valida_controle(controle: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    schema = _schema_risco()
    ctrl = schema["properties"]["risks"]["items"]["properties"]["controls"]["items"]
    return [e.message for e in Draft202012Validator(ctrl).iter_errors(controle)]


def test_controle_em_dependencia_pinada_e_declaravel():
    """O kind que faltava. Sem ele, um consumidor que extrai código para um repositório próprio
    perde a capacidade de dizer onde o controle foi parar — e a saída que sobra é comentário YAML,
    que fiscal nenhum lê."""
    assert _valida_controle({
        "kind": "pinned_dependency",
        "ref": "cockpit_harness.plano.pode_disparar",
        "dependency": "cockpit-harness",
        "version_source": "pyproject.toml",
    }) == []


def test_controle_em_dependencia_pinada_SEM_ancora_de_versao_e_recusado():
    """A mordida. `standard_symbol` exige `version_source` pela razão de sempre: controle externo
    sem versão ancorada é controle que muda sozinho. O kind novo herda a exigência — se não
    herdasse, ele seria a porta de fuga do rigor que ele imita."""
    erros = _valida_controle({
        "kind": "pinned_dependency",
        "ref": "cockpit_harness.plano.pode_disparar",
        "dependency": "cockpit-harness",
    })
    assert any("version_source" in e for e in erros), erros


def test_controle_LOCAL_continua_proibido_de_fingir_ancora_externa():
    """O outro lado: `local_path` não admite `version_source` nem `dependency`. Um arquivo daqui
    não tem versão externa a ancorar, e permitir o campo faria a âncora virar decoração."""
    erros = _valida_controle({
        "kind": "local_path", "ref": "ci/catraca.py", "version_source": "pyproject.toml",
    })
    assert erros, "local_path aceitou campo de ancoragem externa"


def test_standard_symbol_continua_preso_a_fonte_unica_da_regua():
    """Alargar `version_source` para o kind novo não pode ter soltado o antigo: a versão da régua
    mora em requirements-qa.txt e em lugar nenhum mais."""
    assert _valida_controle({
        "kind": "standard_symbol", "ref": "webqa/gates.py::require_discovery",
        "standard": "webqa-suite", "version_source": "pyproject.toml",
    }), "standard_symbol aceitou fonte de versão que não é a única"


# ══════════════════════════════════════════════════════════════════════════════════════════
# (2) A isenção de apoio de teste
# ══════════════════════════════════════════════════════════════════════════════════════════

def _roda_orfaos(modulos: list[dict], exemptions: list[dict]) -> list[str]:
    vm.errors.clear()
    inv = {"modulos": modulos}
    comps = {"components": [], "exemptions": exemptions}
    vm.check_orphan_code(inv, comps)
    vm.check_orphan_tests(inv, comps, {}, {"items": []})
    vm.check_dead_exemptions()
    achados = list(vm.errors)
    vm.errors.clear()
    return achados


ISENCAO = [{"path": "tests/conftest.py",
            "justification": "Apoio de teste: provê fixtures e não exercita componente algum. " * 2}]


def test_apoio_de_teste_DECLARADO_para_de_ser_orfao():
    """O que era impossível até a CP-039. Declarar a isenção de um arquivo de apoio produzia DOIS
    achados — 'isenção morta' mais 'teste órfão' — em vez de zero. Líquido: +1 por declaração
    honesta, e a trava recusava a declaração que ela própria prescrevia como remédio."""
    assert _roda_orfaos([{"kind": "test", "path": "tests/conftest.py"}], ISENCAO) == []


def test_apoio_de_teste_NAO_declarado_continua_orfao():
    """O par. A isenção precisa custar declaração: sem ela, o arquivo continua sendo achado, que é
    o comportamento que faz a cobertura significar alguma coisa."""
    achados = _roda_orfaos([{"kind": "test", "path": "tests/conftest.py"}], [])
    assert len(achados) == 1 and "teste órfão" in achados[0], achados


def test_isencao_que_nao_casa_NADA_continua_morta():
    """A propriedade que torna a isenção honesta sobrevive ao alargamento: declarar a isenção de um
    arquivo que não existe faz a próxima parecer revisada."""
    achados = _roda_orfaos([{"kind": "test", "path": "tests/outro.py"}],
                           [{"path": "tests/sumiu.py", "justification": "x" * 60}])
    assert any("isenção morta" in a for a in achados), achados


def test_a_isencao_morta_so_e_declarada_depois_dos_DOIS_lados():
    """A borda que a separação em `check_dead_exemptions` existe para cobrir: uma isenção que casa
    do lado do TESTE não pode ser acusada de morta pelo lado do CÓDIGO. Antes da CP-039 o contador
    era local a check_orphan_code, e era exatamente isso que acontecia."""
    achados = _roda_orfaos(
        [{"kind": "code", "path": "src/a.py"}, {"kind": "test", "path": "tests/conftest.py"}],
        ISENCAO)
    assert not any("isenção morta" in a for a in achados), achados


# ══════════════════════════════════════════════════════════════════════════════════════════
# (3) A âncora no FATO — a parte mecanizável do padrão
# ══════════════════════════════════════════════════════════════════════════════════════════

def _self_match(assertions: list[dict]) -> list:
    import audit_governance as ag
    findings, errors = hl.Findings(), hl.Errors()
    ag.check_assertion_self_match({"adrs": [{"id": "ADR-999", "assertions": assertions}]},
                                  findings, errors)
    return [f for f in findings.items if f.get("origin") == "assertion_self_match"]


IDX = "architecture/adr/index.yaml"


def test_assercao_que_casa_a_PROPRIA_declaracao_e_acusada():
    """A lição da ADR-028, virando fiscal. Uma asserção que mira o index com um padrão que o index
    contém fica verde por EXISTIR: enquanto ela estiver escrita lá, o padrão estará lá."""
    achados = _self_match([{"id": "ADR-999-A1", "kind": "file_matches",
                            "files": [IDX], "pattern": "schema_version"}])
    assert achados and "casa o próprio" in achados[0]["summary"], achados


def test_assercao_que_mira_o_index_com_padrao_AUSENTE_nao_e_acusada():
    """O par, e ele importa: mirar o index não é o defeito. O defeito é o padrão casar o texto que
    o declara. Uma asserção que exige do index algo que ele ainda não tem é uma asserção que morde."""
    assert _self_match([{"id": "ADR-999-A2", "kind": "file_matches", "files": [IDX],
                         "pattern": "coisa-que-nao-existe-neste-index-xyzzy"}]) == []


def test_assercao_que_NAO_mira_o_index_nunca_e_acusada():
    """A linha que a primeira versão deste fiscal não tinha, e cuja ausência produziu 40 acusações
    de uma vez: `pattern: "COCKPIT_SRC"` está escrito no index, então TODO padrão casa a própria
    linha `pattern:` trivialmente. Escrevi um fiscal contra a âncora-na-menção e ele ancorou na
    menção — sexta ocorrência, e a mais instrutiva das seis."""
    assert _self_match([{"id": "ADR-999-A3", "kind": "file_matches",
                         "files": ["ci/catraca.py"], "pattern": "schema_version"}]) == []


def test_o_index_REAL_deste_molde_esta_limpo():
    """Contra o repositório, não contra fixture."""
    import yaml
    import audit_governance as ag
    idx = yaml.safe_load((RAIZ / IDX).read_text(encoding="utf-8"))
    findings, errors = hl.Findings(), hl.Errors()
    ag.check_assertion_self_match(idx, findings, errors)
    achados = [f for f in findings.items if f.get("origin") == "assertion_self_match"]
    assert not achados, [f["summary"] for f in achados]


def test_a_politica_nomeia_o_padrao_e_o_antidoto():
    """A seção não é decoração: é o que resta do padrão depois que a parte mecanizável virou
    fiscal. Se ela sumir, sobra um fiscal estreito sem a regra que ele representa."""
    texto = (RAIZ / "harness/policies/conformance.md").read_text(encoding="utf-8")
    assert "âncora no FATO" in texto.replace("Âncora", "âncora"), "a seção sumiu da política"
    for pergunta in ("quem CRIA", "quem o EXECUTA", "quem o CONFIGURA"):
        assert pergunta in texto, f"o antídoto perdeu '{pergunta}'"
    assert "check_assertion_self_match" in texto, "a política não aponta para o fiscal que morde"
