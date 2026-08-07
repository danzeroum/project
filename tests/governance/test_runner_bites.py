"""Mordidas do runner genérico e do kit de conformidade (CP-042).

A pergunta que estes testes respondem não é "o runner roda?", e sim **"ele recusa o que deve?"**.
A mais importante é a do veredito: o defeito que o runner existe para pegar é um `exit 0` que
significa *não consegui medir*, e um teste que só exercitasse o caminho feliz não o veria.
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

LAUDO_BASE = {
    # 1.3 e `verdict` DECLARADO: a régua assumiu o veredito, e o runner deixou de inferir.
    # Um laudo base mudo continuaria exercitando uma inferência que não existe mais — e um
    # teste que exercita código apagado passa pela razão errada.
    "schema_version": "1.3",
    "standard": {"name": "webqa-suite", "version": "1.0.0", "commit": "abc",
                 "sensitive_paths_hash": "sha256:aa"},
    "consumer_project": {"repository": "x", "commit": "y"},
    "execution": {"run_id": "r", "mode": "passive", "network_used": False,
                  "active_gates": [], "runner_kind": "ci"},
    "result": "ok", "verdict": "conforme", "findings": [],
}


def roda(root: Path, argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / "ci/suite_runner.py"), *argv],
                          cwd=root, capture_output=True, text=True,
                          env=dict(os.environ, HARNESS_REPO_ROOT=str(root)))


def edita_ficha(root: Path, muda, rel: str = FICHA_QA) -> None:
    caminho = root / rel
    doc = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    muda(doc["suite"])
    caminho.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def escreve_laudo(root: Path, **campos) -> None:
    doc = {**LAUDO_BASE, **campos}
    alvo = root / "harness/reports/qa-report.json"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def usa_laudo_pronto(root: Path) -> None:
    """Faz o comando do modo ser um no-op: o laudo já está no lugar, e o runner o julga.

    Sem isto, o teste dependeria de a régua estar instalada — e o que se quer medir é a TRADUÇÃO
    do veredito, não a régua.
    """
    edita_ficha(root, lambda s: s.__setitem__(
        "modes", [{"nome": "passive", "requires_gate": False,
                   "command": [sys.executable, "-c", "pass"]}]))


# --------------------------------------------------------------------------------------
# A tradução do veredito — o defeito que o runner existe para pegar
# --------------------------------------------------------------------------------------

def test_laudo_exit_zero_com_inconclusivo_nao_e_verde_sem_gap(repo_copy):
    """O CORAÇÃO DA CP-B: sem gap vigente, 'não consegui medir' reprova.

    Este é o gap `GAP-QA-EXIT-ZERO` da qa-suite, exercido com o gap REMOVIDO — provando que o
    contrato pega o defeito, e que o que segura a linha aberta hoje é a data declarada, não a
    ausência de trava.
    """
    usa_laudo_pronto(repo_copy)
    edita_ficha(repo_copy, lambda s: s.__setitem__(
        "gaps", [g for g in s["gaps"] if g["clause"] != "envelope-com-3-estados"]))
    escreve_laudo(repo_copy, result="suite_not_installed", verdict="inconclusivo",
                  verdict_reason="a régua não está instalada")
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "passive", "--sem-ledger"])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "INCONCLUSIVO" in proc.stderr


def test_o_mesmo_laudo_avisa_sem_reprovar_enquanto_o_gap_vigora(repo_copy):
    """O par positivo: o gap datado é o que segura a linha, e ele aparece no aviso.

    Sem este teste, o de cima passaria mesmo que o runner reprovasse SEMPRE — e a preservação do
    comportamento atual, que a CP-042 promete, não estaria provada.
    """
    usa_laudo_pronto(repo_copy)
    escreve_laudo(repo_copy, result="suite_not_installed", verdict="inconclusivo",
                  verdict_reason="a régua não está instalada")
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "passive", "--sem-ledger"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GAP-QA-EXIT-ZERO" in proc.stderr


def test_gap_vencido_faz_o_inconclusivo_reprovar(repo_copy):
    """E a borda que fecha a tolerância: vencido o prazo, o mesmo laudo muda de cor."""
    usa_laudo_pronto(repo_copy)
    ontem = (date.today() - timedelta(days=1)).isoformat()

    def vence(suite):
        for gap in suite["gaps"]:
            if gap["clause"] == "envelope-com-3-estados":
                gap["due"] = ontem

    edita_ficha(repo_copy, vence)
    escreve_laudo(repo_copy, result="suite_not_installed", verdict="inconclusivo",
                  verdict_reason="a régua não está instalada")
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "passive", "--sem-ledger"])
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_verdict_declarado_pela_regua_vence_a_inferencia(repo_copy):
    """Quando a régua declara `verdict`, a declaração vence — e o gap do envelope pode fechar."""
    usa_laudo_pronto(repo_copy)
    escreve_laudo(repo_copy, schema_version="1.3", result="findings", verdict="nao_conforme",
                  findings=[{"id": "F1", "severity": "high", "dimension": "d"}])
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "passive", "--sem-ledger"])
    assert proc.returncode == 1
    assert "NÃO CONFORME" in proc.stderr


def test_laudo_fora_do_envelope_declarado_e_config_invalid(repo_copy):
    """O laudo é validado contra o envelope que a PRÓPRIA ficha declara."""
    usa_laudo_pronto(repo_copy)
    escreve_laudo(repo_copy, result="talvez", verdict="inconclusivo",
                  verdict_reason="result desconhecido")
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "passive", "--sem-ledger"])
    assert proc.returncode == 40, proc.stdout + proc.stderr
    assert "CONFIG_INVALID" in proc.stderr


# --------------------------------------------------------------------------------------
# Autorização
# --------------------------------------------------------------------------------------

def test_modo_com_gate_recusa_sem_autorizacao(repo_copy):
    """Modo pesado é disparado por pessoa, nunca por um agente que decidiu sozinho."""
    edita_ficha(repo_copy, lambda s: s.__setitem__(
        "modes", [{"nome": "load", "requires_gate": True,
                   "command": [sys.executable, "-c", "pass"]}]))
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "load", "--sem-ledger"])
    assert proc.returncode == 11, proc.stdout + proc.stderr
    assert "MODE_FORBIDDEN" in proc.stderr


def test_modo_nao_declarado_recusa(repo_copy):
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "active_discovery", "--sem-ledger"])
    assert proc.returncode == 11


def test_ficha_planned_nao_executa(repo_copy):
    """Régua que ainda não existe não pode produzir laudo, e fingir que produziu é o verde por
    não olhar."""
    proc = roda(repo_copy, ["--suite", "privacy-suite", "--mode", "passive", "--sem-ledger"])
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_placeholder_desconhecido_e_erro_e_nao_literal(repo_copy):
    """Substituição silenciosa produziria um comando que roda e mede OUTRA COISA."""
    edita_ficha(repo_copy, lambda s: s.__setitem__(
        "modes", [{"nome": "passive", "requires_gate": False,
                   "command": ["echo", "{inexistente}"]}]))
    proc = roda(repo_copy, ["--suite", "qa-suite", "--mode", "passive", "--dry-run"])
    assert proc.returncode == 2
    assert "placeholder desconhecido" in proc.stderr


# --------------------------------------------------------------------------------------
# O kit, dos dois lados
# --------------------------------------------------------------------------------------

def test_kit_como_suite_acusa_laudo_sem_verdict(tmp_path):
    """O lado da RÉGUA — o que faz disto um contrato e não uma checagem de uma parte só.

    O `verdict` é REMOVIDO do laudo base de propósito: desde que a régua passou a declará-lo, o
    base o traz, e um teste que reaproveitasse o base sem tirá-lo estaria exercitando o caminho
    verde com o nome do vermelho.
    """
    laudo = tmp_path / "laudo.json"
    laudo.write_text(json.dumps({k: v for k, v in LAUDO_BASE.items() if k != "verdict"}),
                     encoding="utf-8")
    proc = subprocess.run([sys.executable, "ci/suite_conformance.py", "--as-suite", str(laudo)],
                          cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "cláusula 3" in proc.stderr


def test_kit_como_suite_aceita_laudo_conforme(tmp_path):
    laudo = tmp_path / "laudo.json"
    laudo.write_text(json.dumps({**LAUDO_BASE, "schema_version": "1.3", "verdict": "conforme"}),
                     encoding="utf-8")
    proc = subprocess.run([sys.executable, "ci/suite_conformance.py", "--as-suite", str(laudo),
                           "--quiet"], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_kit_como_suite_acusa_fingerprint_incompleto(tmp_path):
    laudo = tmp_path / "laudo.json"
    doc = {**LAUDO_BASE, "schema_version": "1.3", "verdict": "conforme"}
    doc["standard"] = {k: v for k, v in doc["standard"].items() if k != "sensitive_paths_hash"}
    laudo.write_text(json.dumps(doc), encoding="utf-8")
    proc = subprocess.run([sys.executable, "ci/suite_conformance.py", "--as-suite", str(laudo)],
                          cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "catalog_hash" in proc.stderr


def test_kit_como_consumidor_aprova_o_estado_atual():
    proc = subprocess.run([sys.executable, "ci/suite_conformance.py", "--as-consumer", "qa-suite",
                           "--quiet"], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --------------------------------------------------------------------------------------
# A promessa da padronização
# --------------------------------------------------------------------------------------

def test_qa_yml_nao_invoca_mais_a_regua_diretamente():
    """Se acrescentar uma suíte voltar a exigir mexer no workflow, a padronização não aconteceu."""
    texto = (REPO / ".github/workflows/qa.yml").read_text(encoding="utf-8")
    job = texto.split("segregated-load-or-active")[0]
    assert "webqa inventario" not in job
    assert "webqa auditar" not in job
    assert "ci/suite_runner.py --suite qa-suite --mode inventory" in job
    assert "ci/suite_runner.py --suite qa-suite --mode passive" in job


def test_o_passo_que_stages_yaml_cita_continua_existindo():
    """`stages.yaml` resolve o nome do passo LITERALMENTE: renomeá-lo desligaria a cobertura da
    etapa sem que nada acusasse — verde por não olhar, de novo."""
    sys.path.insert(0, str(REPO / "ci"))
    import harness_lib as hl

    importlib.reload(hl)
    nomes = hl.workflow_step_names(".github/workflows/qa.yml")
    stages = hl.read_yaml("harness/stages.yaml")
    citados = [e["step"] for s in stages["stages"] for e in s["enforced_by"]
               if e.get("ref") == ".github/workflows/qa.yml" and e.get("step")]
    assert citados, "nenhuma etapa cita qa.yml — o teste deixou de medir o que promete"
    for passo in citados:
        assert passo in nomes, f"stages.yaml cita o passo {passo!r}, que qa.yml não tem mais"


def test_schema_ref_resolve_sem_rede():
    """O envelope compõe provenance por $ref. Resolver isso pela REDE faria o veredito do fiscal
    depender de quem responde — a família de sequestro que o CP-025 fecha para pip e import."""
    sys.path.insert(0, str(REPO / "ci"))
    import harness_lib as hl

    importlib.reload(hl)
    problemas = hl.schema_errors("laudo", "report.schema.json",
                                 {**LAUDO_BASE, "schema_version": "1.3", "verdict": "conforme"})
    assert problemas == [], problemas
