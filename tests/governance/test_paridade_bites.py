"""Mordidas da paridade local e dos erros acionáveis (CP-028 / ADR-023).

O teste que NÃO existe aqui é tão importante quanto os que existem: não há teste de duração de CI.
O gate de "≥30% em 5 runs" foi revogado (R-12) porque um threshold de tempo mistura cold/warm,
fila e rede num critério de merge — e um teste que o reintroduzisse aqui seria a mesma decisão
voltando pela porta dos fundos.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import harness_lib as hl  # noqa: E402
import pr_checklist  # noqa: E402
from harness_lib import Findings  # noqa: E402

LOCKFILE = REPO / "requirements-ci.txt"
WORKFLOW = REPO / ".github/workflows/governance.yml"
LOCAL = REPO / "harness/local_validate.sh"


# --------------------------------------------------------------------------------------
# Lockfile e paridade
# --------------------------------------------------------------------------------------

def test_lockfile_sem_hashes_reprova():
    """Toda linha de requisito carrega hash.

    Sem hash, um cache envenenado ou um índice trocado entrega outro artefato com o mesmo nome e
    versão, e os fiscais rodam em cima dele reportando verde com convicção.
    """
    linhas = [l for l in LOCKFILE.read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.lstrip().startswith("#")]
    requisitos = [l for l in linhas if "==" in l]
    assert requisitos, "o lockfile não declara requisito algum"
    for req in requisitos:
        assert req.rstrip().endswith("\\"), f"requisito sem continuação de hash: {req}"
    hashes = [l for l in linhas if "--hash=sha256:" in l]
    assert len(hashes) >= len(requisitos), f"{len(requisitos)} requisitos, {len(hashes)} hashes"


def test_hashes_sao_sha256_completos():
    """Hash truncado ou de outro algoritmo passaria no olho e não no pip."""
    for h in re.findall(r"--hash=(\S+)", LOCKFILE.read_text(encoding="utf-8")):
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", h), h


def test_local_validate_instala_lockfile_do_ci():
    """A paridade é o ponto: os dois lados instalam do MESMO arquivo, com a MESMA exigência."""
    local = LOCAL.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "requirements-ci.txt" in local and "--require-hashes" in local
    assert "requirements-ci.txt" in workflow and "--require-hashes" in workflow


def test_local_validate_roda_os_mesmos_comandos_do_ci():
    """Instalar igual e rodar diferente seria paridade pela metade — e a metade que não vale."""
    local = LOCAL.read_text(encoding="utf-8")
    assert "python ci/validate_all.py" in local
    assert "pytest tests/governance" in local


def test_falha_de_hash_explica_a_causa_de_plataforma():
    """O custo declarado precisa estar onde a falha acontece.

    `--require-hashes` fixa artefatos, e wheel é específico de plataforma: quem rodar em macOS vai
    falhar. A mensagem tem que dizer isso, senão a limitação é descoberta como se fosse um bug.
    """
    local = LOCAL.read_text(encoding="utf-8")
    assert "plataforma" in local
    assert "comportamento CERTO" in local or "comportamento certo" in local


def test_chave_de_cache_inclui_lockfile_e_runtime():
    """Uma chave que ignorasse o lock serviria um ambiente que não corresponde ao declarado."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "hashFiles('requirements-ci.txt')" in workflow
    assert "py3.11" in workflow


def test_nenhum_gate_de_duracao_voltou():
    """R-12 é revogação registrada. Este teste é o que impede o gate de voltar sem enfrentar o
    registro — e um threshold de tempo como critério de merge é um fiscal instável por construção."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"(duration|elapsed|SECONDS)\s*(-lt|-gt|<|>)\s*\d+", workflow)


# --------------------------------------------------------------------------------------
# Erros acionáveis
# --------------------------------------------------------------------------------------

def test_fiscal_emite_correcao_acionavel():
    """Achado sem remediação deixou de ser representável."""
    f = Findings()
    f.add(key="X", origin="stage_coverage", severity="high", summary="qualquer coisa")
    assert f.items[0].get("remediation"), f.items[0]


def test_remediacao_especifica_vence_o_padrao():
    """O mapa é fallback, não substituto: quem tem algo melhor a dizer continua dizendo."""
    f = Findings()
    f.add(key="X", origin="stage_coverage", severity="high", summary="s", remediation="faça isto")
    assert f.items[0]["remediation"] == "faça isto"


def test_toda_origem_conhecida_tem_remediacao():
    """Origem sem entrada no mapa volta a produzir achado mudo — e o schema do laudo é a lista
    autoritativa de origens, então derivá-la de lá é o que faz uma origem nova nascer coberta."""
    schema = hl.read_json("harness/schemas/audit-report.schema.json")

    origens: set[str] = set()

    def varrer(node):
        if isinstance(node, dict):
            if node.get("enum") and "adr_assertion" in node["enum"]:
                origens.update(node["enum"])
            for v in node.values():
                varrer(v)
        elif isinstance(node, list):
            for v in node:
                varrer(v)

    varrer(schema)
    # 'manual_assertion' é informativa por natureza: ela existe para dizer que algo NÃO é
    # verificável por máquina, e prescrever um comando ali seria prometer o que não há.
    faltando = origens - set(hl.REMEDIACAO_POR_ORIGEM) - {"manual_assertion"}
    assert not faltando, f"origens sem remediação declarada: {sorted(faltando)}"


def test_nenhum_achado_bloqueante_fica_sem_o_que_fazer(repo_copy: Path, run_auditor):
    """A prova ponta a ponta, sobre um repositório de fato mutado."""
    (repo_copy / "harness/prompts/fantasma-task.md").write_text("# fantasma\n", encoding="utf-8")
    (repo_copy / "arquivo-sem-etapa.txt").write_text("x\n", encoding="utf-8")
    _, findings = run_auditor("audit_governance", repo_copy)
    mudos = [f["id"] for f in findings
             if f["severity"] != "info" and not f.get("remediation")]
    assert not mudos, mudos


def test_fiscal_nao_executa_a_correcao_que_sugere():
    """A fronteira do R-01: um fiscal que conserta o que acusa é juiz e parte, e o diff entra sem
    que ninguém tenha revisado o julgamento que o originou."""
    fonte = (REPO / "ci/harness_lib.py").read_text(encoding="utf-8")
    bloco = fonte.split("REMEDIACAO_POR_ORIGEM = {")[1].split("\n}")[0]
    assert "subprocess" not in bloco and "os.system" not in bloco


# --------------------------------------------------------------------------------------
# Checklist — ergonomia declarada, nunca trava
# --------------------------------------------------------------------------------------

def test_checklist_cobre_etapas_dos_arquivos_modificados(capsys):
    saida_code = pr_checklist.main(["business/capabilities.yaml", "ci/orient.py"])
    texto = capsys.readouterr().out
    assert saida_code == 0
    assert "STAGE-CAPABILITIES" in texto and "STAGE-CI-HARNESS" in texto
    assert "lente de privacidade" in texto


def test_checklist_avisa_sobre_caminho_protegido(capsys):
    pr_checklist.main(["ci/audit_governance.py"])
    texto = capsys.readouterr().out
    assert "Caminho protegido" in texto and "change-proposal" in texto


def test_checklist_nunca_reprova(capsys):
    """Um checklist que reprovasse viraria o nono fiscal, sem política e sem teste de mordida."""
    assert pr_checklist.main(["caminho/que/nao/existe.txt"]) == 0
    capsys.readouterr()


def test_checklist_fora_da_validacao_total():
    """Ergonomia declarada não entra no gate — é o que a mantém ergonomia."""
    assert "pr_checklist" not in (REPO / "ci/validate_all.py").read_text(encoding="utf-8")
