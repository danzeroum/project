#!/usr/bin/env python3
"""Fiscal do ledger — evidência durável que não se reescreve.

Duas invariantes, e as duas existem porque a alternativa é sutil demais para ser notada:

  APPEND-ONLY. Um ledger que se pode reescrever não é ledger. O fiscal compara as linhas com as
  do commit anterior: qualquer linha preexistente alterada ou removida reprova. É o modo de falha
  mais tentador de todos, porque a linha que incomoda é sempre a que registra um vermelho.

  ALLOWLIST ESTRUTURAL. Cada linha valida contra ledger.schema.json, que não tem NENHUM campo
  textual livre. Não é "proibido escrever PII": é que não existe campo que a aceite. A diferença
  entre proibido e inexpressável é a diferença entre uma regra e uma trava — e a promessa
  anterior ("o schema proíbe PII") era infactível, porque JSON Schema valida estrutura e não
  detecta dado pessoal em texto livre.

Uso:  python ci/audit_ledger.py [--quiet] [--json]
      python ci/audit_ledger.py --append release --commit-sha SHA --fiscal ci/mold_release.py \\
          [--run-id ID] [--artifact-ref harness/...] [--result pass|fail|unverifiable]
Saída: 0 conforme · 1 reescrita ou linha inválida · 2 o fiscal não conseguiu fiscalizar.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

import harness_lib as hl
from harness_lib import Errors, Findings, HarnessError

AUDITOR_VERSION = "1.0"
LEDGER = "harness/state/ledger.jsonl"
REPORT_PATH = "harness/reports/ledger-audit.json"
SCHEMA = "ledger.schema.json"


def _linhas(texto: str) -> list[str]:
    return [l for l in texto.splitlines() if l.strip()]


def check_append_only(atual: list[str], anterior: list[str], findings: Findings) -> None:
    """Toda linha do commit anterior continua lá, na mesma ordem e byte a byte.

    Função pura, com o estado anterior recebido como argumento. Quem consulta o git é o chamador —
    a mesma divisão dos outros fiscais desta série, e aqui ela também torna o teste possível sem
    montar um repositório git de mentira.
    """
    if len(atual) < len(anterior):
        findings.add(
            key="LEDGER-TRUNCADO", origin="ledger", severity="critical", risk="RISK-META-001",
            location=LEDGER,
            summary=f"O ledger perdeu linhas: {len(anterior)} antes, {len(atual)} agora. "
                    f"Append-only significa que o passado não encolhe.",
        )
        return
    for i, (velha, nova) in enumerate(zip(anterior, atual), start=1):
        if velha != nova:
            findings.add(
                key=f"LEDGER-REESCRITO-{i}", origin="ledger", severity="critical",
                risk="RISK-META-001", location=f"{LEDGER}:{i}",
                summary=f"A linha {i} do ledger mudou. Um registro que se reescreve não registra "
                        f"nada — e a linha que alguém quer mudar é sempre a que anotou um vermelho.",
                remediation="Acrescentar uma linha nova que corrija o entendimento; nunca editar "
                            "a antiga. O registro é o que aconteceu, não o que se preferia.",
            )


def check_linhas_validas(atual: list[str], findings: Findings, errors: Errors) -> None:
    for i, linha in enumerate(atual, start=1):
        try:
            doc = json.loads(linha)
        except json.JSONDecodeError as exc:
            findings.add(
                key=f"LEDGER-JSON-{i}", origin="ledger", severity="high", risk="RISK-META-001",
                location=f"{LEDGER}:{i}", summary=f"linha {i} não é JSON válido: {exc}",
            )
            continue
        for msg in hl.schema_errors(f"{LEDGER}:{i}", SCHEMA, doc):
            findings.add(
                key=f"LEDGER-SCHEMA-{i}", origin="ledger", severity="high",
                risk="RISK-PRIV-001", location=f"{LEDGER}:{i}",
                summary=msg,
                remediation="O ledger não tem campo textual livre, por decisão: ele é versionado e "
                            "append-only, e minimização insuficiente aqui vira exposição permanente "
                            "(CP-026, item 5 do RIPD).",
            )


def _anterior_do_git() -> list[str] | None:
    """As linhas do ledger no commit anterior. None = não foi possível olhar (indeterminação)."""
    try:
        saida = subprocess.run(["git", "show", f"HEAD:{LEDGER}"], cwd=hl.REPO,
                               capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return None
    if saida.returncode != 0:
        # Arquivo novo no HEAD, ou sem git: não há passado com que comparar. Não é violação —
        # o primeiro commit de um ledger não reescreve nada.
        return []
    return _linhas(saida.stdout)


def commit_corrente() -> str | None:
    """O commit REAL, de GITHUB_SHA ou do git. None se não der para saber.

    Sem isto, o default seria uma constante de zeros — e uma linha de ledger com commit fictício é
    pior que linha nenhuma: ela ocupa o lugar do registro verdadeiro e passa por ele. É o mesmo
    defeito que a CP-022 evita ao só exigir prova quando o fato existe.
    """
    import os

    sha = os.environ.get("GITHUB_SHA")
    if sha and len(sha) == 40:
        return sha
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=hl.REPO,
                           capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return None
    saida = r.stdout.strip()
    return saida if r.returncode == 0 and len(saida) == 40 else None


def append(evento: str, *, result: str = "pass", commit_sha: str | None = None,
           fiscal: str = "ci/validate_all.py", **extra) -> dict:
    """Monta e acrescenta uma linha. Nunca reescreve — abre o arquivo em modo 'a', e é deliberado."""
    sha = commit_sha or commit_corrente()
    if sha is None:
        raise HarnessError(
            "não foi possível resolver o commit corrente — uma linha de ledger com commit "
            "fictício ocupa o lugar do registro verdadeiro e passa por ele")
    linha = {
        "schema_version": "1.0",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": evento,
        "commit_sha": sha,
        "result": result,
        "fiscal": fiscal,
        **extra,
    }
    problemas = hl.schema_errors(LEDGER, SCHEMA, linha)
    if problemas:
        raise HarnessError("; ".join(problemas))
    destino = hl.REPO / LEDGER
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n")
    return linha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fiscal do ledger append-only.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", default=REPORT_PATH)
    parser.add_argument("--append", metavar="EVENTO",
                        help="acrescenta uma linha (uso do CI, não do fiscal)")
    # O evento `release` é o primeiro que NÃO fala do commit corrente: ele registra o commit
    # TAGGEADO, e é gravado num commit filho dele — porque um commit não pode conter o registro de
    # si mesmo, a mesma aritmética que fez o manifesto declarar o pai. Sem --commit-sha o default
    # continua sendo commit_corrente(), que é o certo para `validation`.
    parser.add_argument("--commit-sha", dest="commit_sha", metavar="SHA")
    parser.add_argument("--fiscal", default="ci/validate_all.py")
    parser.add_argument("--run-id", dest="run_id", metavar="ID")
    parser.add_argument("--artifact-ref", dest="artifact_ref", metavar="CAMINHO")
    parser.add_argument("--result", default="pass", choices=["pass", "fail", "unverifiable"])
    args = parser.parse_args(argv)

    findings, errors = Findings(), Errors()

    if args.append:
        extra = {k: v for k, v in (("run_id", args.run_id),
                                   ("artifact_ref", args.artifact_ref)) if v}
        try:
            linha = append(args.append, result=args.result, commit_sha=args.commit_sha,
                           fiscal=args.fiscal, **extra)
        except HarnessError as exc:
            print(f"✗ ledger: linha recusada pelo schema — {exc}", file=sys.stderr)
            return 1
        print(f"✓ ledger: linha acrescentada ({linha['event']}).")
        return 0

    atual = _linhas(hl.read_text(LEDGER)) if hl.rel_exists(LEDGER) else []
    anterior = _anterior_do_git()

    check_linhas_validas(atual, findings, errors)
    if anterior is None:
        # Indeterminação: sem git, não dá para afirmar que nada foi reescrito. Não é violação.
        if not args.quiet:
            print("• ledger: não foi possível ler o estado anterior (sem git) — append-only "
                  "indeterminado nesta execução.", file=sys.stderr)
    else:
        check_append_only(atual, anterior, findings)

    report = hl.build_report(
        auditor="ci/audit_ledger.py", auditor_version=AUDITOR_VERSION,
        findings=findings, stages_covered=["STAGE-GOVERNANCE"],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if errors:
        report["result"] = "error"
    try:
        hl.emit_report(args.report, report)
    except HarnessError as exc:
        print(f"✗ ledger: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        hl.print_summary("ledger", findings, errors, quiet=args.quiet)

    if errors:
        return 2
    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
