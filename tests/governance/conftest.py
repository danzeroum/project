"""Base dos testes de mordida dos fiscais.

Cada teste copia o repositório para tmp_path, injeta UMA violação e exige que o fiscal reprove.
É o idioma do passo negativo de .github/workflows/qa.yml (injeta WEBQA_LEAK=1 e falha se a
detecção não disparar): "o fiscal existe" e "o fiscal morde" são afirmações diferentes, e só a
segunda importa.

O fiscal é apontado para a cópia por HARNESS_REPO_ROOT — nenhum teste toca a árvore de trabalho.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
CI = REPO / "ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))

# Diretórios que não precisam ser copiados para o fiscal funcionar (e que só custariam tempo).
SKIP = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules",
        ".ruff_cache", ".mypy_cache", "build", "dist"}


# Ordem de dependência: harness_lib primeiro (resolve HARNESS_REPO_ROOT), depois quem o importa.
# Recarregar pela metade deixa DUAS classes HarnessError vivas e um REPO congelado do teste
# anterior — os dois bugs mais caros desta suíte, e ambos já aconteceram.
MODULOS_DOS_FISCAIS = (
    "harness_lib", "adapters", "inventory_code", "validate_metadata",
    "generate_graph", "audit_governance", "alignment_report", "audit_conformance",
    "audit_lgpd", "validate_all",
)


def recarregar_fiscais() -> None:
    """Recarrega o GRAFO INTEIRO de módulos dos fiscais contra o HARNESS_REPO_ROOT atual."""
    import importlib
    for nome in MODULOS_DOS_FISCAIS:
        try:
            modulo = importlib.import_module(nome)
        except ImportError:  # pragma: no cover - módulo opcional ausente
            continue
        importlib.reload(modulo)


@pytest.fixture
def repo_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(REPO, dest, ignore=shutil.ignore_patterns(*SKIP))
    return dest


@pytest.fixture
def run_auditor(monkeypatch):
    """Roda um fiscal contra uma cópia, recarregando os módulos para que REPO aponte para ela."""

    def _run(module_name: str, root: Path, argv: list[str] | None = None) -> tuple[int, list[dict]]:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        import harness_lib
        importlib.reload(harness_lib)
        module = importlib.import_module(module_name)
        importlib.reload(module)
        code = module.main(list(argv or []) + ["--quiet"])
        report_path = root / (
            "harness/reports/governance-audit.json"
            if module_name == "audit_governance"
            else "harness/reports/lgpd-audit.json"
        )
        findings = []
        if report_path.exists():
            import json
            findings = json.loads(report_path.read_text(encoding="utf-8"))["findings"]
        return code, findings

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


@pytest.fixture
def run_metadata(monkeypatch):
    """Roda o fiscal de metadados contra uma cópia e devolve (exit_code, erros).

    Fixture própria porque validate_metadata não emite laudo: ele acumula strings em err() e as
    imprime. Reaproveitar run_auditor exigiria inventar um laudo que não existe — e um laudo
    inventado para o teste passar é exatamente o que este repositório recusa em toda parte.
    """

    def _run(root: Path, argv: list[str] | None = None) -> tuple[int, list[str]]:
        monkeypatch.setenv("HARNESS_REPO_ROOT", str(root))
        recarregar_fiscais()
        import validate_metadata
        code = validate_metadata.main(list(argv or []))
        return code, list(validate_metadata.errors)

    yield _run
    os.environ.pop("HARNESS_REPO_ROOT", None)
    import harness_lib
    importlib.reload(harness_lib)


def ids_of(findings: list[dict]) -> set[str]:
    return {f["id"] for f in findings}


def origins_of(findings: list[dict]) -> set[str]:
    return {f["origin"] for f in findings}
