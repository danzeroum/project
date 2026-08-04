#!/usr/bin/env python3
"""Frescor da VALIDAÇÃO semântica, e o diff de ingestão contra o alvo.

Duas perguntas diferentes vivem neste repositório, e confundi-las é o erro que este arquivo
existe para evitar:

  VERIFICAÇÃO  "está conforme o declarado?"  — os fiscais determinísticos. Executam, reprovam.
  VALIDAÇÃO    "ainda faz o que deveria?"    — o agente `conformance`. Julga, propõe, nunca corrige.

Este script é da primeira espécie e fiscaliza a segunda: ele não julga se a descrição de um
componente ainda condiz com o código — confere que ALGUÉM julgou, e que o julgamento cobre este
estado. Mesmo desenho de ci/audit_lgpd.py::check_judgment_currency, e pela mesma razão: fiscal
determinístico não sabe ler prosa, mas sabe muito bem dizer se a prosa é velha.

O fingerprint inclui o SHA de target.lock. É o que faz "cobre este estado" significar algo num
derivado — sem ele o alvo inteiro pode ser reescrito e a revisão continua se declarando fresca.

Uso:  python ci/audit_conformance.py [--print-fingerprint] [--sync-diff] [--quiet]
Sai:  0 conforme · 1 divergência · 2 não conseguiu avaliar.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone

import harness_lib as hl
from harness_lib import Errors, Findings, HarnessError, build_report, emit_report

REVIEW = "governance/conformance-review.yaml"
LAUDO = "harness/reports/conformance-audit.json"
WORKSPACE = "workspace/target"


def check_review_currency(findings: Findings) -> None:
    """A revisão existe e cobre o estado atual — incluindo o commit do alvo."""
    atual = hl.conformance_fingerprint()
    if not hl.rel_exists(REVIEW):
        findings.add(
            key="CONF-REVIEW-MISSING", origin="conformance_review", severity="high",
            risk="RISK-CONF-002", location=REVIEW,
            summary="Não há registro de validação semântica: a conformidade é verificada "
                    "(os fiscais rodam) mas nunca validada (ninguém perguntou se ainda faz "
                    "o que deveria).",
            remediation="Rodar o agente `conformance` e registrar o resultado em " + REVIEW,
        )
        return

    review = (hl.read_yaml(REVIEW) or {}).get("review", {})
    if review.get("scope_fingerprint") != atual:
        findings.add(
            key="CONF-REVIEW-STALE", origin="conformance_review", severity="high",
            risk="RISK-CONF-002", location=REVIEW,
            summary="A validação semântica não cobre o estado atual: o metadado governável ou o "
                    "SHA do alvo mudaram desde que ela foi produzida, então ela fala de outro "
                    "sistema.",
            evidence=f"registrado={review.get('scope_fingerprint')} atual={atual}",
            remediation="Rodar o agente `conformance` e regravar scope_fingerprint com: "
                        "python ci/audit_conformance.py --print-fingerprint",
        )

    for achado in review.get("findings", []):
        if achado.get("disposition") == "change_proposal" and not achado.get("ref"):
            findings.add(
                key=f"CONF-DANGLING-{achado.get('id', '?')}", origin="conformance_review",
                severity="medium", risk="RISK-CONF-002", location=REVIEW,
                summary=f"{achado.get('id', '?')} foi encaminhado para change-proposal e não diz "
                        f"qual — encaminhamento sem destino é achado arquivado com outro nome.",
            )


# --------------------------------------------------------------------------------------
# Diff de ingestão
# --------------------------------------------------------------------------------------

def _mudados(de: str, para: str) -> list[str]:
    """Arquivos do alvo que mudaram entre dois commits, lidos do workspace materializado."""
    ws = hl.REPO / WORKSPACE
    if not (ws / ".git").exists():
        raise HarnessError(f"{WORKSPACE} não materializado — rode python ci/bootstrap.py")
    proc = subprocess.run(["git", "diff", "--name-only", de, para],
                          cwd=ws, capture_output=True, text=True)
    if proc.returncode != 0:
        raise HarnessError(f"git diff {de[:8]}..{para[:8]} falhou: {proc.stderr.strip()}")
    return [linha for linha in proc.stdout.splitlines() if linha]


def sync_diff(remoto: str) -> dict:
    """Quais metadados ficam velhos se o lock avançar para `remoto`.

    É o que transforma drift em trabalho concreto: em vez de "o alvo andou 40 commits", a resposta
    é "estes seis itens descrevem arquivos que mudaram". A lista é o insumo da change-proposal —
    nunca uma correção automática, porque decidir se um item ainda vale é julgamento.
    """
    lock = hl.read_yaml("target.lock") or {}
    atual = lock.get("target_sha")
    if not atual:
        raise HarnessError("target.lock não ancora commit algum: nada a comparar")

    mudados = set(_mudados(atual, remoto))
    afetados: list[dict] = []
    import validate_metadata as vm

    for rel, chave in vm.DERIVAVEIS:
        if not hl.rel_exists(rel):
            continue
        for item in (hl.read_yaml(rel) or {}).get(chave, []) or []:
            proc = item.get("derived_from")
            if proc and proc.get("path") in mudados:
                afetados.append({"doc": rel, "id": item.get("id", "?"),
                                 "path": proc["path"], "sha_registrado": proc.get("sha")})
    return {"de": atual, "para": remoto, "arquivos_mudados": sorted(mudados),
            "metadados_afetados": afetados}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frescor da validação semântica e diff de ingestão.")
    parser.add_argument("--print-fingerprint", action="store_true",
                        help="imprime o fingerprint atual e sai")
    parser.add_argument("--sync-diff", metavar="SHA",
                        help="lista os metadados que ficam velhos se o lock avançar para SHA")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.print_fingerprint:
        print(hl.conformance_fingerprint())
        return 0

    findings, errors = Findings(), Errors()
    try:
        if args.sync_diff:
            d = sync_diff(args.sync_diff)
            print(f"• {len(d['arquivos_mudados'])} arquivo(s) do alvo mudaram entre "
                  f"{d['de'][:12]} e {d['para'][:12]}")
            if not d["metadados_afetados"]:
                print("• Nenhum metadado com proveniência aponta para eles.")
            for item in d["metadados_afetados"]:
                print(f"  · {item['id']} ({item['doc']}) descreve {item['path']}, que mudou")
            print("\nO lock NÃO avança aqui: avançá-lo é decisão declarada em change-proposal.")
            return 1 if d["metadados_afetados"] else 0

        check_review_currency(findings)
        emit_report(LAUDO, build_report(
            auditor="ci/audit_conformance.py", auditor_version="1.0", findings=findings,
            stages_covered=["STAGE-GOVERNANCE"],
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            scope_fingerprint=hl.conformance_fingerprint()))
    except HarnessError as exc:
        print(f"✗ conformidade contínua: {exc}", file=sys.stderr)
        return 2

    hl.print_summary("conformidade contínua", findings, errors, quiet=args.quiet)
    if errors:
        return 2
    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
