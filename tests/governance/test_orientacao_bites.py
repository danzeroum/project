"""Prova que a orientação DERIVA em vez de descrever — e que não vira o oitavo fiscal.

Os dois testes que mais importam são test_etapa_nova_aparece_sem_editar_a_skill e
test_skill_com_id_de_etapa_reprova. Juntos eles são a trava inteira: o primeiro mostra que a
orientação acompanha o repositório sozinha, o segundo impede alguém de "melhorar" a skill
listando as etapas — que é como uma segunda descrição nasce, sempre com boa intenção.

O terceiro é test_orient_nunca_reprova. Um orientador que reprovasse viraria um fiscal sem
política e sem teste de mordida, e seria o primeiro lugar onde alguém tentaria afrouxar algo,
justamente por não parecer um fiscal.
"""

from __future__ import annotations

import importlib
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

from conftest import ids_of, recarregar_fiscais

CI = Path(__file__).resolve().parent.parent.parent / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))

SKILL = ".claude/skills/desenvolver/SKILL.md"


@pytest.fixture
def orientar(monkeypatch):
    def _run(root: Path, argv: list[str] | None = None) -> tuple[int, str, object]:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        recarregar_fiscais()
        import orient
        importlib.reload(orient)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = orient.main(list(argv or []))
        return code, buf.getvalue(), orient

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    recarregar_fiscais()


def _editar(root: Path, rel: str, mutate) -> None:
    p = root / rel
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    mutate(doc)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


# --------------------------------------------------------------------------------------
# Deriva, não descreve
# --------------------------------------------------------------------------------------

def test_panorama_responde_o_papel_e_o_proximo_passo(repo_copy, orientar):
    code, saida, _ = orientar(repo_copy)
    assert code == 0
    assert "mold" in saida and "/adotar" in saida


def test_etapa_nova_aparece_sem_editar_a_skill(repo_copy, orientar):
    """O teste central: mudar stages.yaml muda a orientação, e nenhum markdown foi tocado."""
    (repo_copy / "novo_departamento").mkdir()
    (repo_copy / "novo_departamento/coisa.yaml").write_text("a: 1\n", encoding="utf-8")
    _editar(repo_copy, "harness/stages.yaml", lambda d: d["stages"].append({
        "id": "STAGE-INVENTADA", "order": 99, "name": "Etapa inventada pelo teste",
        "artifacts": ["novo_departamento"],
        "enforced_by": [{"kind": "ci_script", "ref": "ci/validate_metadata.py",
                         "symbol": "check_capabilities"}],
        "privacy_lens": {"scan": False, "question": "Pergunta injetada pelo teste?"},
    }))
    _, saida, _ = orientar(repo_copy, ["--tocar", "novo_departamento/coisa.yaml"])
    assert "STAGE-INVENTADA" in saida, saida
    assert "check_capabilities" in saida, saida
    assert "Pergunta injetada pelo teste?" in saida, saida


def test_caminho_protegido_manda_declarar_change_proposal(repo_copy, orientar):
    _, saida, _ = orientar(repo_copy, ["--tocar", "ci/validate_metadata.py"])
    assert "protected_path" in saida and "change-proposal" in saida


def test_caminho_novo_avisa_que_nenhuma_etapa_o_reivindica(repo_copy, orientar):
    _, saida, _ = orientar(repo_copy, ["--tocar", "departamento/que/nao/existe.yaml"])
    assert "nenhuma etapa o reivindica" in saida


def test_caminho_com_ponto_inicial_resolve(repo_copy, orientar):
    """`.claude/…` não pode virar `claude/…`: lstrip remove caracteres, não prefixo — e a
    orientação passaria a falar de um arquivo que não existe."""
    _, saida, _ = orientar(repo_copy, ["--tocar", ".claude/settings.json"])
    assert ".claude/settings.json" in saida
    assert "nenhuma etapa o reivindica" not in saida


def test_cobertura_conta_orfaos(repo_copy, orientar):
    (repo_copy / "src/project/solto.py").write_text("VALOR = 1\n", encoding="utf-8")
    _, saida, mod = orientar(repo_copy)
    cob = mod.cobertura_do_alvo()
    assert "src/project/solto.py" in cob["orfaos"], cob
    assert cob["com_dono"] < cob["arquivos_de_codigo"]


def test_relata_fiscal_vermelho_sem_repetir_o_laudo(repo_copy, orientar):
    """Códigos, não laudos: repetir a saída criaria duas versões da mesma resposta."""
    _editar(repo_copy, "business/capabilities.yaml",
            lambda d: d["capabilities"][0].update(source_paths=["src/nao/existe.py"]))
    _, saida, _ = orientar(repo_copy)
    assert "divergência" in saida
    assert "source_path inexistente" not in saida, "o laudo do fiscal vazou para o painel"


# --------------------------------------------------------------------------------------
# Não vira o oitavo fiscal
# --------------------------------------------------------------------------------------

def test_orient_nunca_reprova(repo_copy, orientar):
    """Sai 0 mesmo com o repositório quebrado: orientar não é fiscalizar."""
    _editar(repo_copy, "business/capabilities.yaml",
            lambda d: d["capabilities"][0].update(source_paths=["src/nao/existe.py"]))
    code, _, _ = orientar(repo_copy)
    assert code == 0


def test_orient_sem_workspace_no_derivado_nao_estoura(repo_copy, orientar):
    """Derivado sem bootstrap é estado comum, não erro de orientação."""
    _editar(repo_copy, "project.yaml", lambda d: (
        d["project"].update(kind="derived"),
        d.update(target={"repo": "sintetico/alvo", "ref": "principal",
                         "lock_source": "target.lock", "code_roots": ["app"],
                         "test_roots": [], "languages": ["python"]})))
    _editar(repo_copy, "target.lock", lambda d: d.update(kind="derived", target_sha="0" * 40))
    code, saida, _ = orientar(repo_copy)
    assert code == 0
    assert "/bootstrap" in saida


# --------------------------------------------------------------------------------------
# A skill não pode restatar
# --------------------------------------------------------------------------------------

def test_skill_com_id_de_etapa_reprova(repo_copy, run_auditor):
    """É assim que uma segunda descrição nasce: alguém 'melhora' a skill listando as etapas."""
    p = repo_copy / SKILL
    p.write_text(p.read_text(encoding="utf-8")
                 + "\n## Etapas\n\n- STAGE-VISION — visão e métricas\n", encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-014-A3" in ids_of(findings), ids_of(findings)


def test_orient_que_mantem_copia_da_lista_de_fiscais_reprova(repo_copy, run_auditor):
    """Uma cópia da lista derivaria: fiscal novo em validate_all e o painel não saberia."""
    p = repo_copy / "ci/orient.py"
    p.write_text(p.read_text(encoding="utf-8").replace("validate_all._steps()",
                                                       "[('metadados', None, [])]"),
                 encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert "FIND-ADR-014-A2" in ids_of(findings), ids_of(findings)
