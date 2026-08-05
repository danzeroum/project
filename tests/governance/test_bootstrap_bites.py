"""Prova que o cold start é idempotente e que a tolerância a clone cru é assimétrica.

O teste que mais importa é test_sem_dependencias_fora_de_summary_sai_2. A tolerância existe
para que o SessionStart não estoure num clone fresco — mas se ela vazasse para os outros modos,
um repositório sem dependências passaria a "validar" com exit 0, e nenhuma mudança seria
necessária para desligar todos os fiscais de uma vez. É a trava que o vigiado desliga sem
precisar tocar em nada.

O alvo sintético é um repositório git de verdade criado em tmp_path: materializar de mentira
provaria que o mock funciona, não que o bootstrap funciona.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SHA_INEXISTENTE = "0123456789abcdef0123456789abcdef01234567"


def _git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


@pytest.fixture
def alvo_sintetico(tmp_path: Path) -> tuple[Path, str]:
    """Um repositório git descartável com dois commits. Devolve (caminho, sha-do-primeiro).

    O caminho termina em '.git' e mora sob 'sintetico/' porque bootstrap.py monta a URL como
    f"{HOST}/{repo}.git" — o layout do alvo de teste imita o do host real em vez de pedir que a
    produção ganhe um caso especial para ser testável.
    """
    alvo = tmp_path / "host" / "sintetico" / "alvo.git"
    (alvo / "src").mkdir(parents=True)
    _git("init", "--quiet", "-b", "principal", str(alvo), cwd=tmp_path)
    _git("config", "user.email", "teste@invalido", cwd=alvo)
    _git("config", "user.name", "teste", cwd=alvo)
    (alvo / "src" / "app.py").write_text("VALOR = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=alvo)
    _git("commit", "-qm", "primeiro", cwd=alvo)
    primeiro = _git("rev-parse", "HEAD", cwd=alvo)
    (alvo / "src" / "app.py").write_text("VALOR = 2\n", encoding="utf-8")
    _git("add", "-A", cwd=alvo)
    _git("commit", "-qm", "segundo", cwd=alvo)
    return alvo, primeiro


@pytest.fixture
def run_bootstrap(monkeypatch):
    def _run(root: Path, argv: list[str] | None = None,
             host: str | None = None) -> tuple[int, dict]:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        import bootstrap
        importlib.reload(bootstrap)
        if host:  # depois do reload: recarregar o módulo restauraria o host de produção
            bootstrap.HOST = host
        code = bootstrap.main(list(argv or []) + ["--skip-deps", "--quiet"])
        laudo = root / "harness/state/bootstrap.json"
        return code, (json.loads(laudo.read_text(encoding="utf-8")) if laudo.exists() else {})

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)


def _vira_derivado(root: Path, alvo: Path, sha: str) -> str:
    """Ancora a cópia no alvo sintético e devolve o host a usar (o diretório que contém 'sintetico/')."""
    p = root / "project.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["project"]["kind"] = "derived"
    doc["target"] = {"repo": "sintetico/alvo", "ref": "principal",
                     "lock_source": "target.lock", "code_roots": ["src"], "test_roots": ["tests/unit"], "languages": ["python"]}
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    lock = root / "target.lock"
    ldoc = yaml.safe_load(lock.read_text(encoding="utf-8"))
    ldoc.update(kind="derived", target_sha=sha)
    lock.write_text(yaml.safe_dump(ldoc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(alvo.parent.parent)  # .../host, que contém sintetico/alvo.git


def test_molde_nao_materializa_nada(repo_copy, run_bootstrap):
    code, laudo = run_bootstrap(repo_copy)
    assert code == 0, laudo
    assert laudo["kind"] == "mold"
    assert laudo["etapas"]["workspace"]["acao"] == "nao-aplicavel"


def test_papeis_divergentes_nao_levantam(repo_copy, run_bootstrap):
    p = repo_copy / "project.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["project"]["kind"] = "derived"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, laudo = run_bootstrap(repo_copy)
    assert code == 2, laudo
    assert "papel do repositório" in laudo["erro"]


def test_derivado_sem_sha_nao_levanta(repo_copy, run_bootstrap):
    for rel, upd in (("project.yaml", {"kind": "derived"}), ("target.lock", {"kind": "derived"})):
        p = repo_copy / rel
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        (doc["project"] if rel == "project.yaml" else doc).update(upd)
        if rel == "project.yaml":
            doc["target"] = {"repo": "a/b", "ref": "principal", "lock_source": "target.lock",
                             "code_roots": ["src"], "test_roots": ["tests/unit"], "languages": ["python"]}
        p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, laudo = run_bootstrap(repo_copy)
    assert code == 2
    assert "target_sha" in laudo["erro"]


def test_materializa_no_sha_do_lock_e_e_idempotente(repo_copy, alvo_sintetico, run_bootstrap):
    """A segunda execução não refaz o clone — é o que permite chamá-lo em toda sessão."""
    alvo, primeiro = alvo_sintetico
    host = _vira_derivado(repo_copy, alvo, primeiro)

    code, laudo = run_bootstrap(repo_copy, host=host)
    assert laudo["etapas"]["workspace"]["acao"] == "materializado", laudo
    ws = repo_copy / "workspace/target"
    assert _git("rev-parse", "HEAD", cwd=ws) == primeiro
    # Ancorado no PRIMEIRO commit, não no HEAD do alvo: o lock é a fonte da versão.
    assert (ws / "src/app.py").read_text(encoding="utf-8") == "VALOR = 1\n"

    _, laudo2 = run_bootstrap(repo_copy, host=host)
    assert laudo2["etapas"]["workspace"]["acao"] == "ja-no-sha", laudo2
    assert _git("rev-parse", "HEAD", cwd=ws) == primeiro


def test_check_drift_reporta_atraso_sem_corrigir(repo_copy, alvo_sintetico, run_bootstrap):
    """O alvo andou dois commits; o lock não. O drift é reportado, e o lock NÃO avança sozinho:
    movê-lo sem revisar o metadado troca um drift visível por um metadado errado."""
    alvo, primeiro = alvo_sintetico
    host = _vira_derivado(repo_copy, alvo, primeiro)

    code, laudo = run_bootstrap(repo_copy, ["--check-drift"], host=host)
    assert code == 0
    drift = laudo["etapas"]["drift"]
    assert drift["estado"] == "atrasado", drift
    assert drift["lock"] == primeiro and drift["remoto"] != primeiro

    lock = yaml.safe_load((repo_copy / "target.lock").read_text(encoding="utf-8"))
    assert lock["target_sha"] == primeiro, "o lock não pode avançar como efeito colateral"


def test_check_drift_em_dia_quando_lock_casa_o_remoto(repo_copy, alvo_sintetico, run_bootstrap):
    alvo, _ = alvo_sintetico
    topo = _git("rev-parse", "HEAD", cwd=alvo)
    host = _vira_derivado(repo_copy, alvo, topo)
    code, laudo = run_bootstrap(repo_copy, ["--check-drift"], host=host)
    assert code == 0
    assert laudo["etapas"]["drift"]["estado"] == "em-dia"


def test_sha_ausente_no_remoto_nao_levanta(repo_copy, alvo_sintetico, run_bootstrap):
    alvo, _ = alvo_sintetico
    host = _vira_derivado(repo_copy, alvo, SHA_INEXISTENTE)
    code, laudo = run_bootstrap(repo_copy, host=host)
    assert code == 2, laudo
    assert laudo["resultado"] == "erro"


def _validate_all_sem_dependencias(root: Path, argv: list[str]) -> subprocess.CompletedProcess:
    """Roda validate_all num interpretador cujo sys.path não enxerga pyyaml/jsonschema."""
    stub = root / "_stub_sem_deps"
    stub.mkdir(exist_ok=True)
    for mod in ("yaml", "jsonschema"):
        (stub / f"{mod}.py").write_text("raise ImportError('ausente por teste')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(stub), "HARNESS_REPO_ROOT": str(root)}
    return subprocess.run([sys.executable, str(root / "ci/validate_all.py"), *argv],
                          capture_output=True, text=True, env=env, cwd=root)


def test_sem_dependencias_com_summary_sai_0(repo_copy):
    """SessionStart nunca bloqueia: a falta de dependência é estado a reportar."""
    proc = _validate_all_sem_dependencias(repo_copy, ["--summary"])
    assert proc.returncode == 0, proc.stderr
    assert "bootstrap" in proc.stdout


def test_sem_dependencias_fora_de_summary_sai_2(repo_copy):
    """E nunca 0: um validador que passa por não ter conseguido rodar desliga tudo de uma vez."""
    proc = _validate_all_sem_dependencias(repo_copy, [])
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)


# --------------------------------------------------------------------------------------
# CP-016: no CI, materializar e validar são passos SEPARADOS
# --------------------------------------------------------------------------------------

def _quebra_o_metadado(root: Path) -> None:
    """Uma divergência qualquer, para distinguir 'o mundo falhou' de 'o repositório divergiu'."""
    p = root / "business/capabilities.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["capabilities"][0]["source_paths"] = ["src/inexistente.py"]
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_only_workspace_nao_roda_os_fiscais(repo_copy, run_bootstrap, alvo_sintetico):
    """A separação que o CP-016 existe para criar, e o teste que mais importa aqui.

    Se --only-workspace rodasse os fiscais, um repositório com divergência de metadado sairia
    vermelho no passo de MATERIALIZAÇÃO — e o CI passaria a dizer "o clone falhou" quando o que
    falhou foi a governança. Colapsar os dois ensina a ler vermelho de governança como problema
    de rede, e o gate fica desligado por hábito, sem ninguém ter decidido desligá-lo.
    """
    alvo, sha = alvo_sintetico
    host = _vira_derivado(repo_copy, alvo, sha)
    _quebra_o_metadado(repo_copy)
    code, laudo = run_bootstrap(repo_copy, ["--only-workspace"], host=host)
    assert code == 0, laudo
    assert laudo["etapas"]["workspace"]["acao"] == "materializado", laudo


def test_only_workspace_no_molde_sai_limpo(repo_copy, run_bootstrap):
    """No molde target_sha é null: o passo tem de sair 0 e dizer que não se aplica — nem falhar,
    nem virar no-op mudo, que é onde a próxima regressão se esconde."""
    code, laudo = run_bootstrap(repo_copy, ["--only-workspace"])
    assert code == 0, laudo
    assert laudo["etapas"]["workspace"]["acao"] == "nao-aplicavel", laudo


def test_bootstrap_completo_ainda_reprova_divergencia(repo_copy, run_bootstrap, alvo_sintetico):
    """O contrapeso: a separação é escolha do CI, não afrouxamento embutido.

    Sem a flag, o bootstrap continua validando e continua reprovando — sem isto, --only-workspace
    seria uma porta para nunca rodar fiscal algum.
    """
    alvo, sha = alvo_sintetico
    host = _vira_derivado(repo_copy, alvo, sha)
    _quebra_o_metadado(repo_copy)
    code, _ = run_bootstrap(repo_copy, host=host)
    assert code == 1
