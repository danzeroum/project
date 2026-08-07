"""Mordidas do Contrato de Régua (CP-041).

Cada teste injeta UMA violação numa cópia do repositório e exige que o fiscal reprove. O idioma é
o de `conftest.py`: nenhum teste toca a árvore de trabalho, e o fiscal é apontado para a cópia por
`HARNESS_REPO_ROOT`.

Três famílias, e a terceira é a que justifica a extração:
  - a ficha (higiene, contract_version, gap vencido);
  - as cláusulas (envelope, pin, release, cobertura de env_prefix);
  - o MOTOR COMPARTILHADO — que precisa reprovar nos DOIS consumidores, senão provamos que a
    extração não quebrou o molde sem provar que ela serve a quem a justificou.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
FICHA_QA = "harness/suites/qa-suite.yaml"
MANIFESTO = "harness/suite-contract/contract-v1/contract-manifest.json"
MOTOR = "harness/suite-contract/mutation-engine/mutation_engine.py"


# --------------------------------------------------------------------------------------
# Auxiliares
# --------------------------------------------------------------------------------------

def roda_suites(root: Path, monkeypatch) -> tuple[int, list[dict]]:
    """Roda ci/audit_suites.py contra uma cópia e devolve (exit, achados)."""
    monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
    import harness_lib

    importlib.reload(harness_lib)
    import audit_suites

    importlib.reload(audit_suites)
    codigo = audit_suites.main(["--quiet", "--skip-autoprova"])
    laudo = root / "harness/reports/suites-audit.json"
    achados = json.loads(laudo.read_text(encoding="utf-8"))["findings"] if laudo.exists() else []
    return codigo, achados


def ids(achados: list[dict]) -> set[str]:
    return {a["id"] for a in achados}


def escreve_ficha(root: Path, rel: str, muda) -> None:
    caminho = root / rel
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    muda(doc["suite"])
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def reemite_digests(root: Path) -> None:
    """Reemite o manifesto depois de mexer no conteúdo — senão o digest acusa antes da cláusula.

    Sem isto, todo teste desta suíte reprovaria por CONTRATO-DIGEST-DIVERGENTE e provaria apenas
    que o digest funciona. Um teste que passa pela razão errada é pior que um teste ausente.
    """
    import hashlib

    caminho = root / MANIFESTO
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    for item in doc["contract"]["files"]:
        alvo = root / item["path"]
        if alvo.is_file():
            item["sha256"] = hashlib.sha256(alvo.read_bytes()).hexdigest()
    caminho.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                       encoding="utf-8")


@pytest.fixture(autouse=True)
def _restaura_repo_root():
    yield
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib

    importlib.reload(harness_lib)


# --------------------------------------------------------------------------------------
# A ficha
# --------------------------------------------------------------------------------------

def test_ficha_sem_env_prefix_reprova(repo_copy, run_metadata):
    """Cláusula de higiene: sem env_prefix, os gates fail-closed da régua ficam alcançáveis."""
    escreve_ficha(repo_copy, FICHA_QA, lambda s: s.pop("env_prefix"))
    codigo, erros = run_metadata(repo_copy)
    assert codigo == 1
    assert any("env_prefix" in e for e in erros), erros


def test_ficha_com_contract_version_inexistente_reprova(repo_copy, run_metadata):
    """O enum é FECHADO: um contrato inexistente é inexpressável, não apenas detectável."""
    escreve_ficha(repo_copy, FICHA_QA, lambda s: s.__setitem__("contract_version", "v9"))
    codigo, erros = run_metadata(repo_copy)
    assert codigo == 1
    assert any("contract_version" in e or "v9" in e for e in erros), erros


def test_duas_fichas_com_o_mesmo_env_prefix_reprovam(repo_copy, run_metadata):
    """Prefixo repetido torna ambíguo de quem é a variável — e remover uma ficha descobre a outra."""
    escreve_ficha(repo_copy, "harness/suites/privacy-suite.yaml",
                  lambda s: s.__setitem__("env_prefix", "WEBQA_"))
    codigo, erros = run_metadata(repo_copy)
    assert codigo == 1
    assert any("env_prefix" in e and "WEBQA_" in e for e in erros), erros


def test_ficha_ativa_sem_install_reprova(repo_copy, run_metadata):
    """A outra metade da cláusula 1: `pin_source` diz onde a versão mora, `install` de onde vem.

    O defeito que a trava existe para pegar já tinha acontecido: a qa-suite era consumida por um
    pin que NÃO RESOLVIA, e o caminho que funciona vivia num comentário. Comentário não é
    declaração — nada o valida, nada o executa, e ele envelhece sem ficar vermelho.
    """
    escreve_ficha(repo_copy, FICHA_QA, lambda s: s.pop("install"))
    codigo, erros = run_metadata(repo_copy)
    assert codigo == 1
    assert any("install" in e for e in erros), erros


def test_install_de_referencia_direta_sem_placeholder_de_origem_reprova(repo_copy, run_metadata):
    """O spec declara a FORMA; os dois valores moram fora da ficha.

    Sem `{origin}`, o spec ou está incompleto — e o caminho não resolve — ou traz a URL literal,
    que é a de repositório sob `harness/` que o ADR-008-A5 recusa por cravar um alvo no molde.
    """
    escreve_ficha(repo_copy, FICHA_QA, lambda s: s["install"].__setitem__(
        "spec", "webqa-suite @ git+https://exemplo.invalid/x/y@v{version}#subdirectory=x"))
    codigo, erros = run_metadata(repo_copy)
    assert codigo == 1
    assert any("spec" in e or "origin" in e for e in erros), erros


def test_gap_vencido_acusa(repo_copy, monkeypatch):
    """A borda: prazo que passa sem nada acontecer é prazo decorativo."""
    ontem = (date.today() - timedelta(days=1)).isoformat()

    def vence(suite):
        suite["gaps"][0]["due"] = ontem

    escreve_ficha(repo_copy, FICHA_QA, vence)
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("GAP-VENCIDO" in i for i in ids(achados)), ids(achados)


def test_gap_no_prazo_nao_acusa(repo_copy, monkeypatch):
    """O simétrico, sem o qual o teste acima passaria mesmo com o fiscal sempre vermelho."""
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 0, ids(achados)


# --------------------------------------------------------------------------------------
# As cláusulas
# --------------------------------------------------------------------------------------

def test_release_sem_gap_reprova(repo_copy, monkeypatch):
    """`anchored: false` é legítimo — calado, não. Cláusula 2.

    A mutação mudou de FORMA quando a v1.0.0 foi publicada: antes havia um gap cobrindo a
    cláusula, e negá-la era mover o gap; agora a régua ancora de verdade, e negá-la é
    DESANCORAR. O achado cobrado é o mesmo, e é isso que a mantém a mesma mordida.
    """
    escreve_ficha(repo_copy, FICHA_QA,
                  lambda s: s["release"].__setitem__("anchored", False))
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("RELEASE-SEM-GAP" in i for i in ids(achados)), ids(achados)


def test_manifesto_da_release_ausente_reprova(repo_copy, monkeypatch):
    """Âncora que não encontra o que ancora está quebrada, não satisfeita."""
    (repo_copy / "harness/suites/qa-suite.manifesto.json").unlink()
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("RELEASE-MANIFESTO-AUSENTE" in i for i in ids(achados)), ids(achados)


def test_manifesto_da_release_com_digest_divergente_reprova(repo_copy, monkeypatch):
    """A âncora é o DIGEST, não o caminho.

    `manifest_path` existir prova que há um arquivo, não que é AQUELE arquivo. Sem esta mordida,
    mover a tag da régua e trazer o manifesto novo passaria calado — exatamente o evento que
    "tag é ponteiro móvel, digest não" existe para tornar visível.
    """
    (repo_copy / "harness/suites/qa-suite.manifesto.json").write_text(
        '{"tag": "v1.0.0", "editado": true}\n', encoding="utf-8")
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("RELEASE-DIGEST-DIVERGENTE" in i for i in ids(achados)), ids(achados)


def test_release_ancorada_com_digest_correto_nao_acusa(repo_copy, monkeypatch):
    """O simétrico, sem o qual os dois acima passariam mesmo com o fiscal sempre vermelho.

    Sobre a ficha REAL, sem fabricar estado: a v1.0.0 está publicada e o digest declarado é o
    do manifesto que veio da tag. Se este teste precisar de encenação um dia, é sinal de que a
    âncora deixou de valer no repositório — e é isso que ele existe para acusar.
    """
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 0, ids(achados)


def test_envelope_sem_um_dos_tres_estados_reprova(repo_copy, monkeypatch):
    """Cláusula 3: sem os três estados, 'não medi' e 'medi e passou' saem com a mesma cor."""
    esquema = repo_copy / "harness/schemas/report.schema.json"
    doc = json.loads(esquema.read_text(encoding="utf-8"))
    doc["properties"]["verdict"]["enum"] = ["conforme", "nao_conforme"]
    esquema.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("ENVELOPE-SEM-ESTADO" in i for i in ids(achados)), ids(achados)


def test_fingerprint_incompleto_reprova(repo_copy, monkeypatch):
    """Cláusula 4: faltando um campo, dois laudos parecem comparáveis sem serem."""
    escreve_ficha(repo_copy, FICHA_QA,
                  lambda s: s.__setitem__("fingerprint_fields", ["name", "version"]))
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("FINGERPRINT-INCOMPLETO" in i for i in ids(achados)), ids(achados)


def test_pin_restatado_na_ficha_reprova(repo_copy, monkeypatch):
    """Cláusula 1: a ficha diz ONDE a versão mora, nunca QUAL."""
    escreve_ficha(repo_copy, FICHA_QA, lambda s: s.__setitem__("entrypoint", "webqa==1.0.0"))
    reemite_digests(repo_copy)
    codigo, achados = roda_suites(repo_copy, monkeypatch)
    assert codigo == 1
    assert any("PIN-RESTATADO" in i for i in ids(achados)), ids(achados)


def test_registro_ausente_e_indeterminacao_nunca_verde(repo_copy, monkeypatch):
    """Some o registro, some a denylist derivada. Isso é exit 2, jamais 'nenhuma régua'."""
    import shutil

    shutil.rmtree(repo_copy / "harness/suites")
    codigo, _ = roda_suites(repo_copy, monkeypatch)
    assert codigo == 2, "registro ausente tem que ser 'não consegui fiscalizar', nunca conforme"


# --------------------------------------------------------------------------------------
# A denylist derivada — prova cruzada com o CP-025
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("variavel", ["WEBQA_LEAK", "PRIVSUITE_LEAK"])
def test_env_prefix_da_ficha_entra_na_denylist(variavel):
    """Os dois prefixos são negados POR DERIVAÇÃO — nenhum está hard-coded em harness.yaml.

    PRIVSUITE_ é o mais eloquente: a régua não existe, e a variável já é negada. É a diferença
    entre uma denylist que cresce à mão e uma que nasce coberta.
    """
    ambiente = dict(os.environ, **{variavel: "1"})
    r = subprocess.run([sys.executable, "ci/env_guard.py", "--quiet"],
                       cwd=REPO, capture_output=True, text=True, env=ambiente)
    assert r.returncode == 10, r.stderr
    assert variavel in r.stderr


def test_harness_yaml_nao_restata_prefixo_de_regua():
    """A fonte única, do outro lado: o prefixo mora na ficha, e só nela."""
    texto = (REPO / "harness/harness.yaml").read_text(encoding="utf-8")
    bloco = texto.split("env_denylist_prefix:")[1].split("\n")[0]
    assert "WEBQA_" not in bloco, "WEBQA_ voltou a ser literal em harness.yaml — a segunda cópia"


def test_denylist_e_fail_closed_sem_registro(tmp_path):
    """Registro ilegível não pode devolver a lista curta: seria a trava se desligando sozinha."""
    import shutil

    copia = tmp_path / "repo"
    shutil.copytree(REPO, copia, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"))
    shutil.rmtree(copia / "harness/suites")
    r = subprocess.run([sys.executable, str(copia / "ci/env_guard.py"), "--quiet"],
                       cwd=copia, capture_output=True, text=True,
                       env=dict(os.environ, HARNESS_REPO_ROOT=str(copia)))
    assert r.returncode == 2, "sem registro o guard tem que sair 2, nunca 0"
    assert "FISCAL_CEGO" in r.stderr


# --------------------------------------------------------------------------------------
# O motor compartilhado — os DOIS consumidores
# --------------------------------------------------------------------------------------

def test_motor_nao_importa_nada_do_molde():
    """A fronteira de dados: o motor recebe a asserção como DADO e não arrasta harness_lib.

    É a condição de possibilidade do segundo consumidor. Uma suíte que precisasse de harness_lib
    para provar as próprias travas receberia meio molde junto com a peça — e a extração falharia
    exatamente em quem a justifica.
    """
    import ast

    arvore = ast.parse((REPO / MOTOR).read_text(encoding="utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
    assert importados <= {"__future__", "json", "re", "pathlib"}, (
        f"o motor passou a importar {importados - {'__future__', 'json', 're', 'pathlib'}} — "
        f"deixou de ser consumível por quem não é este repositório")


def test_mutacao_plantada_no_motor_reprova_no_consumidor_molde(tmp_path):
    """Consumidor 1 (o molde): enfraquecer um operador faz as asserções pararem de morder."""
    import shutil

    copia = tmp_path / "repo"
    shutil.copytree(REPO, copia, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"))

    motor = copia / MOTOR
    texto = motor.read_text(encoding="utf-8")
    # O defeito histórico REAL: apagar UMA ocorrência em vez de todas. Com count=1, cinco
    # asserções ficaram verdes depois de mutadas e o fiscal as acusou de decorativas.
    assert 're.sub(mut["pattern"], f"# {_MARCA}", texto, flags=re.MULTILINE)' in texto
    motor.write_text(texto.replace(
        're.sub(mut["pattern"], f"# {_MARCA}", texto, flags=re.MULTILINE)',
        're.sub(mut["pattern"], f"# {_MARCA}", texto, count=1, flags=re.MULTILINE)'),
        encoding="utf-8")

    r = subprocess.run([sys.executable, "ci/audit_mutations.py", "--quiet"],
                       cwd=copia, capture_output=True, text=True,
                       env=dict(os.environ, HARNESS_REPO_ROOT=str(copia)))
    assert r.returncode == 1, "motor enfraquecido tem que fazer o molde reprovar"
    assert "nao_morde" in r.stderr


def test_mutacao_plantada_no_motor_reprova_no_consumidor_por_pin(tmp_path):
    """Consumidor 2 (quem consome POR PIN): o digest do manifesto acusa o motor adulterado.

    É a razão inteira de o motor ser pinado em vez de copiado. Uma suíte que o consumisse por
    cópia poderia ter um operador enfraquecido e a prova diria 'todas mordem' — o selo falso que
    a política prova-de-mutacao.md chama de pior que fiscal nenhum.
    """
    import shutil

    copia = tmp_path / "repo"
    shutil.copytree(REPO, copia, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"))
    motor = copia / MOTOR
    motor.write_text(motor.read_text(encoding="utf-8") + "\n# operador enfraquecido\n",
                     encoding="utf-8")

    r = subprocess.run([sys.executable, "ci/audit_suites.py", "--quiet"],
                       cwd=copia, capture_output=True, text=True,
                       env=dict(os.environ, HARNESS_REPO_ROOT=str(copia)))
    assert r.returncode == 1, "motor adulterado tem que reprovar pelo pin"
    assert "DIGEST-DIVERGENTE" in r.stdout + r.stderr


def test_os_tres_pontos_de_invocacao_continuam_chamando_a_prova():
    """A guarda contra a regressão silenciosa: verde por NÃO RODAR é o pior verde.

    A prova de mutação é invocada em três lugares. Se a extração tivesse mudado o caminho de
    invocação e um dos três não fosse atualizado, aquele ponto ficaria verde por não olhar — e
    ninguém teria como distinguir isso de 'rodou e passou'.
    """
    pontos = [
        (".github/workflows/governance.yml", 1),
        (".github/workflows/release.yml", 2),
    ]
    for arquivo, esperado in pontos:
        texto = (REPO / arquivo).read_text(encoding="utf-8")
        assert texto.count("python ci/audit_mutations.py") == esperado, (
            f"{arquivo} deixou de invocar a prova de mutação o número esperado de vezes")

    # E o entrypoint continua existindo com o nome que os três invocam.
    assert (REPO / "ci/audit_mutations.py").is_file()


def test_extracao_preservou_o_conjunto_de_operadores():
    """O motor extraído implementa exatamente os operadores que o schema de ADR promete."""
    sys.path.insert(0, str(REPO / "harness/suite-contract/mutation-engine"))
    import mutation_engine

    schema = json.loads(
        (REPO / "harness/schemas/adr-index.schema.json").read_text(encoding="utf-8"))
    do_schema = set(
        schema["$defs"]["assertion"]["properties"]["mutation"]["properties"]["op"]["enum"])
    assert set(mutation_engine.OPERADORES) == do_schema, (
        "o motor e o schema discordam sobre quais mutações existem")
