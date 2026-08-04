"""Prova que a validação semântica vence, e que o drift vira trabalho em vez de número.

O teste central é test_avancar_o_lock_vence_a_revisao. É o único mecanismo que impede um derivado
de envelhecer em silêncio: sem o SHA do alvo dentro do fingerprint, o alvo inteiro pode ser
reescrito enquanto o metadado fica byte a byte idêntico — e a revisão continuaria se declarando
fresca sobre um sistema que não existe mais.

O segundo é test_sync_diff_nao_avanca_o_lock. Um comando que "resolve" o drift atualizando o lock
troca um drift visível por um metadado errado, que é estritamente pior porque some.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

CI = Path(__file__).resolve().parent.parent.parent / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture
def conformance(monkeypatch):
    def _run(root: Path, argv: list[str] | None = None) -> tuple[int, object]:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        import harness_lib
        importlib.reload(harness_lib)
        import validate_metadata
        importlib.reload(validate_metadata)
        import audit_conformance
        importlib.reload(audit_conformance)
        return audit_conformance.main(list(argv or []) + ["--quiet"]), audit_conformance

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


def _ler(root: Path, rel: str) -> dict:
    return yaml.safe_load((root / rel).read_text(encoding="utf-8"))


def _gravar(root: Path, rel: str, doc: dict) -> None:
    (root / rel).write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")


def _refresca(root: Path, mod) -> None:
    """Regrava o fingerprint como o agente faria depois de revisar."""
    review = _ler(root, "governance/conformance-review.yaml")
    import harness_lib
    review["review"]["scope_fingerprint"] = harness_lib.conformance_fingerprint()
    _gravar(root, "governance/conformance-review.yaml", review)


@pytest.fixture
def alvo_com_dois_commits(tmp_path: Path) -> tuple[Path, str, str]:
    alvo = tmp_path / "alvo"
    (alvo / "app").mkdir(parents=True)
    _git("init", "--quiet", "-b", "principal", str(alvo), cwd=tmp_path)
    _git("config", "user.email", "teste@invalido", cwd=alvo)
    _git("config", "user.name", "teste", cwd=alvo)
    (alvo / "app" / "servico.py").write_text("def executar():\n    return 1\n", encoding="utf-8")
    (alvo / "app" / "estavel.py").write_text("CONSTANTE = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=alvo)
    _git("commit", "-qm", "primeiro", cwd=alvo)
    antigo = _git("rev-parse", "HEAD", cwd=alvo)
    (alvo / "app" / "servico.py").write_text("def executar():\n    return 2\n", encoding="utf-8")
    _git("add", "-A", cwd=alvo)
    _git("commit", "-qm", "segundo", cwd=alvo)
    return alvo, antigo, _git("rev-parse", "HEAD", cwd=alvo)


# --------------------------------------------------------------------------------------
# Frescor da validação semântica
# --------------------------------------------------------------------------------------

def test_baseline_tem_revisao_fresca(repo_copy, conformance):
    code, _ = conformance(repo_copy)
    assert code == 0


def test_revisao_ausente_e_achado(repo_copy, conformance):
    """Verificado sem validado: os fiscais rodam e ninguém pergunta se ainda faz o que deveria."""
    (repo_copy / "governance/conformance-review.yaml").unlink()
    code, _ = conformance(repo_copy)
    assert code == 1


def test_metadado_alterado_vence_a_revisao(repo_copy, conformance):
    _gravar(repo_copy, "business/capabilities.yaml",
            {**_ler(repo_copy, "business/capabilities.yaml"), "metadata_version": "1.2"})
    code, _ = conformance(repo_copy)
    assert code == 1


def test_avancar_o_lock_vence_a_revisao(repo_copy, conformance):
    """O metadado não mudou uma vírgula — só o commit do alvo. Sem o SHA no fingerprint, a
    revisão continuaria se declarando fresca sobre um sistema reescrito por inteiro."""
    lock = _ler(repo_copy, "target.lock")
    lock.update(kind="derived", target_sha="a" * 40)
    _gravar(repo_copy, "target.lock", lock)
    proj = _ler(repo_copy, "project.yaml")
    proj["project"]["kind"] = "derived"
    proj["target"] = {"repo": "sintetico/alvo", "ref": "principal", "lock_source": "target.lock",
                      "code_roots": ["src"], "test_roots": ["tests/unit"], "languages": ["python"]}
    _gravar(repo_copy, "project.yaml", proj)

    code, _ = conformance(repo_copy)
    assert code == 1, "avançar o lock tem de vencer a revisão semântica"


def test_regravar_o_fingerprint_refresca(repo_copy, conformance):
    """O caminho de volta existe e é barato — senão a trava vira obstáculo permanente."""
    _gravar(repo_copy, "business/capabilities.yaml",
            {**_ler(repo_copy, "business/capabilities.yaml"), "metadata_version": "1.2"})
    code, mod = conformance(repo_copy)
    assert code == 1
    _refresca(repo_copy, mod)
    code, _ = conformance(repo_copy)
    assert code == 0


def test_encaminhamento_sem_destino_e_achado(repo_copy, conformance):
    """change_proposal sem ref é achado arquivado com outro nome."""
    review = _ler(repo_copy, "governance/conformance-review.yaml")
    review["review"]["findings"].append({
        "id": "CONF-099", "severity": "medium",
        "summary": "achado injetado pelo teste, encaminhado para lugar nenhum",
        "disposition": "change_proposal",
    })
    _gravar(repo_copy, "governance/conformance-review.yaml", review)
    import harness_lib
    code, _ = conformance(repo_copy)
    assert code == 1


# --------------------------------------------------------------------------------------
# Diff de ingestão
# --------------------------------------------------------------------------------------

def _preparar_derivado(root: Path, alvo: Path, sha: str) -> None:
    proj = _ler(root, "project.yaml")
    proj["project"]["kind"] = "derived"
    proj["target"] = {"repo": "sintetico/alvo", "ref": "principal", "lock_source": "target.lock",
                      "code_roots": ["app"], "test_roots": [], "languages": ["python"]}
    _gravar(root, "project.yaml", proj)
    lock = _ler(root, "target.lock")
    lock.update(kind="derived", target_sha=sha)
    _gravar(root, "target.lock", lock)

    ws = root / "workspace/target"
    ws.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", str(alvo), str(ws)], check=True,
                   capture_output=True)

    comps = _ler(root, "architecture/components.yaml")
    comps["source_of_truth"] = False
    comps["generated_from"] = "harness/pipeline/ingest.yaml#ING-03-CARTOGRAFIA"
    comps["components"] = [
        {"id": "CMP-SERVICO", "kind": "domain-module", "capability": "CAP-PRICING",
         "status": "proposed", "source_paths": ["workspace/target/app/servico.py"],
         "tested_by": [], "owner": "engineering",
         "derived_from": {"repo": "sintetico/alvo", "sha": sha, "path": "app/servico.py"}},
        {"id": "CMP-ESTAVEL", "kind": "domain-module", "capability": "CAP-CATALOG",
         "status": "proposed", "source_paths": ["workspace/target/app/estavel.py"],
         "tested_by": [], "owner": "engineering",
         "derived_from": {"repo": "sintetico/alvo", "sha": sha, "path": "app/estavel.py"}},
    ]
    comps["exemptions"] = []
    _gravar(root, "architecture/components.yaml", comps)


def test_sync_diff_aponta_so_o_metadado_afetado(repo_copy, alvo_com_dois_commits, conformance):
    """A resposta útil não é 'o alvo andou'; é QUAL item descreve arquivo que mudou."""
    alvo, antigo, novo = alvo_com_dois_commits
    _preparar_derivado(repo_copy, alvo, antigo)

    code, mod = conformance(repo_copy, ["--sync-diff", novo])
    assert code == 1, "há metadado afetado: o comando sinaliza trabalho pendente"
    d = mod.sync_diff(novo)
    afetados = {i["id"] for i in d["metadados_afetados"]}
    assert afetados == {"CMP-SERVICO"}, d
    assert "app/estavel.py" not in d["arquivos_mudados"]


def test_sync_diff_nao_avanca_o_lock(repo_copy, alvo_com_dois_commits, conformance):
    """Avançar o lock sozinho trocaria um drift visível por um metadado errado — que some."""
    alvo, antigo, novo = alvo_com_dois_commits
    _preparar_derivado(repo_copy, alvo, antigo)
    conformance(repo_copy, ["--sync-diff", novo])
    assert _ler(repo_copy, "target.lock")["target_sha"] == antigo


def test_sync_diff_sem_metadado_afetado_sai_0(repo_copy, alvo_com_dois_commits, conformance):
    alvo, antigo, novo = alvo_com_dois_commits
    _preparar_derivado(repo_copy, alvo, antigo)
    comps = _ler(repo_copy, "architecture/components.yaml")
    comps["components"] = [c for c in comps["components"] if c["id"] == "CMP-ESTAVEL"]
    comps["exemptions"] = [{
        "path": "workspace/target/app/servico.py",
        "justification": "isenção injetada pelo teste para isolar o caso em que nenhum metadado "
                         "com proveniência aponta para arquivo alterado",
    }]
    _gravar(repo_copy, "architecture/components.yaml", comps)
    code, _ = conformance(repo_copy, ["--sync-diff", novo])
    assert code == 0


def test_canal_de_retorno_ao_alvo_nasce_desligado(repo_copy):
    """Escrita em repositório que não se governa começa fechada (decision_policy.default: deny)."""
    harness = yaml.safe_load((repo_copy / "harness/harness.yaml").read_text(encoding="utf-8"))
    assert harness["target_feedback"]["open_issues_on_target"] is False
    assert harness["target_feedback"]["requires_human_approval"] is True
