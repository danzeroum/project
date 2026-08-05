"""Mordidas do ledger append-only com allowlist estrutural (CP-026 / ADR-021).

O teste que substitui o antigo "test_ledger_recusa_PII" é `test_ledger_recusa_campos_nao_allowlisted`,
e a troca de nome carrega a correção inteira: não se testa que o schema DETECTA dado pessoal — ele
não detecta e não pode detectar. Testa-se que não existe campo onde dado pessoal caiba. A diferença
entre "proibido" e "inexpressável" é a diferença entre uma regra e uma trava.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import audit_ledger as al  # noqa: E402
import harness_lib as hl  # noqa: E402
from harness_lib import Findings, HarnessError  # noqa: E402

SHA = "a" * 40


def _linha(**over) -> dict:
    d = {
        "schema_version": "1.0",
        "recorded_at": "2026-08-05T12:00:00+00:00",
        "event": "validation",
        "commit_sha": SHA,
        "result": "pass",
    }
    d.update(over)
    return d


def test_linha_minima_valida():
    """O par positivo: o que o ledger existe para registrar precisa caber nele."""
    assert hl.schema_errors("ledger", "ledger.schema.json", _linha()) == []


@pytest.mark.parametrize("campo,valor", [
    ("author", "Fulano de Tal"),
    ("email", "fulano@exemplo.com"),
    ("login", "@fulano"),
    ("prompt", "texto livre qualquer"),
    ("report_body", "conteúdo do laudo"),
    ("note", "observação"),
])
def test_ledger_recusa_campos_nao_allowlisted(campo, valor):
    """Substitui o teste de 'PII' da versão anterior do plano, e a substituição é a correção.

    JSON Schema não detecta dado pessoal em texto livre — prometer isso seria uma trava que não
    encontra o que vigia. O que ele faz, e faz de forma absoluta, é recusar QUALQUER propriedade
    que não esteja na allowlist. Não há PII a detectar quando não há campo que a aceite.
    """
    erros = hl.schema_errors("ledger", "ledger.schema.json", _linha(**{campo: valor}))
    assert erros, f"o campo {campo!r} entrou no ledger"


@pytest.mark.parametrize("valor", [
    "https://github.com/org/repo/actions/runs/1",   # URL carrega organização e repositório
    "run 42",                                       # espaço abre a porta para texto
    "org/repo:run",                                 # ':' e '/' idem
])
def test_run_id_nao_aceita_url_nem_texto(valor):
    """`run_id` exclui '/', ':' e espaço de propósito: sem isso ele aceitaria uma URL, e uma URL
    carrega organização, repositório e às vezes autor."""
    assert hl.schema_errors("ledger", "ledger.schema.json", _linha(run_id=valor))


@pytest.mark.parametrize("valor", ["@fulano", "fulano@exemplo.com", "anon:xyz", "anon:" + "a" * 15])
def test_actor_ref_so_aceita_pseudonimo(valor):
    """O prefixo e o tamanho fixo tornam impossível escrever um login onde deveria haver pseudônimo."""
    assert hl.schema_errors("ledger", "ledger.schema.json", _linha(actor_ref=valor))


def test_actor_ref_pseudonimizado_passa():
    assert hl.schema_errors("ledger", "ledger.schema.json",
                            _linha(actor_ref="anon:" + "0" * 16)) == []


def test_evento_fora_do_enum_reprova():
    """Um campo 'tipo de evento' aberto seria a primeira porta por onde texto livre entraria."""
    assert hl.schema_errors("ledger", "ledger.schema.json", _linha(event="qualquer coisa"))


# --------------------------------------------------------------------------------------
# Append-only
# --------------------------------------------------------------------------------------

def test_ledger_nao_aceita_reescrita():
    """A linha que alguém quer mudar é sempre a que anotou um vermelho."""
    anterior = [json.dumps(_linha(result="fail"), sort_keys=True)]
    atual = [json.dumps(_linha(result="pass"), sort_keys=True)]
    f = Findings()
    al.check_append_only(atual, anterior, f)
    assert any("REESCRITO" in x["id"] for x in f.sorted_items()), f.sorted_items()


def test_ledger_nao_aceita_truncamento():
    f = Findings()
    al.check_append_only([], [json.dumps(_linha(), sort_keys=True)], f)
    assert any("TRUNCADO" in x["id"] for x in f.sorted_items()), f.sorted_items()


def test_acrescentar_linha_passa():
    """O par positivo do append-only: crescer é exatamente o que o ledger deve permitir."""
    velha = json.dumps(_linha(), sort_keys=True)
    f = Findings()
    al.check_append_only([velha, json.dumps(_linha(event="release"), sort_keys=True)], [velha], f)
    assert not f.sorted_items(), f.sorted_items()


def test_linha_invalida_no_arquivo_reprova(repo_copy: Path, run_auditor, monkeypatch):
    import importlib

    caminho = repo_copy / "harness/state/ledger.jsonl"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(_linha(author="Fulano")) + "\n", encoding="utf-8")

    monkeypatch.setenv("HARNESS_REPO_ROOT", str(repo_copy))
    importlib.reload(hl)
    modulo = importlib.reload(al)
    assert modulo.main(["--quiet"]) == 1


def test_commit_ficticio_nao_e_escrito(repo_copy: Path, monkeypatch):
    """Uma linha de ledger com commit fictício ocupa o lugar do registro verdadeiro e passa por ele.

    O default de zeros que este teste impede era o mesmo defeito que a CP-022 evita ao só exigir
    prova quando o fato existe: campo que ninguém consegue preencher direito é preenchido com
    qualquer coisa.
    """
    import importlib

    monkeypatch.setenv("HARNESS_REPO_ROOT", str(repo_copy))
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    importlib.reload(hl)
    modulo = importlib.reload(al)
    monkeypatch.setattr(modulo, "commit_corrente", lambda: None)
    # hl.HarnessError acessado APÓS o reload, nunca o nome importado no topo: recarregar
    # harness_lib cria uma classe nova, e o `except`/`raises` contra a classe antiga não pega
    # nada. É o bug que o conftest chama de "duas classes HarnessError vivas", e ele já custou
    # caro nesta suíte antes.
    with pytest.raises(hl.HarnessError, match="commit fictício"):
        modulo.append("validation")


def test_ripd_registra_a_excecao():
    """A condição de entrada da fase: mudar uma medida de proteção declarada exige tocar o
    documento que a declara. Sem isto, o `.gitignore` e o RIPD diriam coisas diferentes."""
    ripd = (REPO / "governance/ripd.md").read_text(encoding="utf-8")
    assert "ledger.jsonl" in ripd
    assert "pseudonimizado" in ripd or "pseudonimização" in ripd
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "!harness/state/ledger.jsonl" in gitignore


def test_laudo_schema_11_continua_valido():
    """Não-retroatividade: nenhuma evidência existente vira inválida por uma versão nova de schema."""
    doc = {
        "schema_version": "1.1",
        "standard": {"package": "webqa-suite", "version": "1.0.0",
                     "sensitive_paths_hash": "sha256:" + "0" * 64},
        "consumer_project": {"id": "x", "commit": "b" * 40},
        "execution": {"mode": "inventory", "runner_kind": "ci",
                      "started_at": "2026-08-05T12:00:00+00:00"},
    }
    erros = hl.schema_errors("prov", "provenance.schema.json", doc)
    assert not any("attestation" in e for e in erros), erros


def test_laudo_sem_atestacao_com_schema_12_reprova():
    doc = {
        "schema_version": "1.2",
        "standard": {"package": "webqa-suite", "version": "1.0.0",
                     "sensitive_paths_hash": "sha256:" + "0" * 64},
        "consumer_project": {"id": "x", "commit": "b" * 40},
        "execution": {"mode": "inventory", "runner_kind": "ci",
                      "started_at": "2026-08-05T12:00:00+00:00"},
    }
    erros = hl.schema_errors("prov", "provenance.schema.json", doc)
    assert any("attestation" in e for e in erros), erros
