#!/usr/bin/env python3
"""Alinhamento entre departamentos e cobertura REVERSA de risco.

Os fiscais existentes verificam uma direção: todo controle aponta para algo real, todo id resolve.
Este verifica a inversa, que é a que faltava — todo ativo relevante é apontado por algum risco, e
todo nó do grafo se conecta a alguma coisa. A diferença não é acadêmica: os riscos deste
repositório eram todos sobre a própria harness, e ninguém percebia, porque nenhuma trava pergunta
"o que ficou de fora?".

Quatro regras, e cada uma existe por um modo de falha concreto:

  R1  capacidade high/critical sem RISK-* que a referencie
      → risco reconhecido em campo e invisível na governança
  R2  risco 'open' sem treatment, owner e prazo
      → risco aberto sem prazo é risco aceito sem ninguém ter aceitado
  R3  superfície de UI órfã (sem satisfies)
      → interface que não serve requisito nenhum: ou o requisito sumiu, ou a tela não deveria existir
  R4  componente concreto sem requisito nem regra verificada que o justifique
      → código maduro cuja razão de existir ninguém registrou

Reusa risk_level DE PROPÓSITO em vez de criar 'criticality': duas escalas para a mesma pergunta
começam espelhadas e terminam discordando, sem que nada reprove.

Uso:  python ci/alignment_report.py [--check] [--quiet]
Sai:  0 alinhado · 1 divergência · 2 não conseguiu avaliar.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import harness_lib as hl
from harness_lib import Errors, Findings, HarnessError, build_report, emit_report

DOC = "docs/alignment.md"
LAUDO = "harness/reports/alignment-audit.json"
CONCRETO = {"implemented", "verified"}
ALTO = {"high", "critical"}


def _load(rel: str) -> dict:
    return hl.read_yaml(rel) or {} if hl.rel_exists(rel) else {}


def coletar() -> dict:
    caps = _load("business/capabilities.yaml").get("capabilities", []) or []
    comps = _load("architecture/components.yaml").get("components", []) or []
    ifcs = _load("architecture/interfaces.yaml").get("interfaces", []) or []
    uis = _load("design/ui-surfaces.yaml").get("ui_surfaces", []) or []
    reqs = _load("business/requirements/backlog.yaml").get("items", []) or []
    riscos_doc = _load("governance/risk-register.yaml")
    regras = []
    for path in sorted((hl.REPO / "business" / "rules").glob("*.yaml")):
        regras.append(hl.read_yaml(hl.rel(path)) or {})
    return {"caps": caps, "comps": comps, "ifcs": ifcs, "uis": uis, "reqs": reqs,
            "riscos": riscos_doc.get("risks", []) or [],
            "isencoes": riscos_doc.get("risk_exemptions", []) or [], "regras": regras}


def cobertos(riscos: list[dict]) -> set[str]:
    return {ref for r in riscos for ref in r.get("related", []) or []}


def r1_capacidade_de_alto_risco_sem_risco(d: dict, f: Findings) -> None:
    cob, isentos = cobertos(d["riscos"]), {e["ref"] for e in d["isencoes"]}
    for cap in d["caps"]:
        cid = cap.get("id", "?")
        if cap.get("risk_level") in ALTO and cid not in cob and cid not in isentos:
            f.add(key=f"ALIGN-R1-{cid}", origin="alignment_risk", severity="high",
                  risk="RISK-ALIGN-001", location="business/capabilities.yaml",
                  summary=f"{cid} é risk_level '{cap.get('risk_level')}' e nenhum RISK-* a "
                          f"referencia em 'related' — risco reconhecido em campo e invisível na "
                          f"governança.",
                  remediation="Acrescentar o id a related[] de um risco, ou declarar a isenção "
                              "com justificativa em governance/risk-register.yaml:risk_exemptions.")


def r2_risco_aberto_sem_prazo(d: dict, f: Findings) -> None:
    for risco in d["riscos"]:
        if risco.get("status") != "open":
            continue
        faltando = [c for c in ("treatment", "owner", "due") if not risco.get(c)]
        if faltando:
            f.add(key=f"ALIGN-R2-{risco.get('id', '?')}", origin="alignment_risk",
                  severity="high", risk="RISK-ALIGN-001",
                  location="governance/risk-register.yaml",
                  summary=f"{risco.get('id', '?')} está 'open' sem {', '.join(faltando)} — "
                          f"risco aberto sem prazo é risco aceito sem ninguém ter aceitado.")


def r3_superficie_orfa(d: dict, f: Findings) -> None:
    isentos = {e["ref"] for e in d["isencoes"]}
    for ui in d["uis"]:
        uid = ui.get("id", "?")
        if not ui.get("satisfies") and uid not in isentos:
            f.add(key=f"ALIGN-R3-{uid}", origin="alignment_orphan", severity="medium",
                  risk="RISK-ALIGN-001", location="design/ui-surfaces.yaml",
                  summary=f"{uid} não satisfaz requisito algum — ou o requisito sumiu, ou a tela "
                          f"não deveria existir. As duas respostas são acionáveis; o silêncio não.")


def r4_componente_sem_justificativa(d: dict, f: Findings) -> None:
    """Componente concreto tem de nascer de um requisito ou de uma regra verificada."""
    isentos = {e["ref"] for e in d["isencoes"]}
    cap_regras: dict[str, set[str]] = {}
    for doc in d["regras"]:
        cap = doc.get("capability")
        for regra in doc.get("rules", []) or []:
            if regra.get("status") == "verified":
                cap_regras.setdefault(cap, set()).update(regra.get("verified_by", []) or [])

    for comp in d["comps"]:
        cid = comp.get("id", "?")
        if comp.get("status") not in CONCRETO or cid in isentos:
            continue
        if comp.get("implements"):
            continue
        testes = set(comp.get("tested_by", []) or [])
        if testes & cap_regras.get(comp.get("capability"), set()):
            continue
        f.add(key=f"ALIGN-R4-{cid}", origin="alignment_orphan", severity="medium",
              risk="RISK-ALIGN-001", location="architecture/components.yaml",
              summary=f"{cid} está '{comp.get('status')}' e não implementa requisito nem é "
                      f"coberto por regra verificada da sua capacidade — código maduro cuja razão "
                      f"de existir ninguém registrou.")


def isencao_morta(d: dict, f: Findings) -> None:
    """Isenção que não casa ativo algum só serve para a cobertura parecer fechada."""
    reais = {x.get("id") for grupo in ("caps", "comps", "ifcs", "uis", "reqs") for x in d[grupo]}
    for entrada in d["isencoes"]:
        if entrada["ref"] not in reais:
            f.add(key=f"ALIGN-EXEMPT-{entrada['ref']}", origin="alignment_risk", severity="low",
                  risk="RISK-ALIGN-001", location="governance/risk-register.yaml",
                  summary=f"Isenção morta: '{entrada['ref']}' não é um ativo deste repositório.")


# --------------------------------------------------------------------------------------

def render(d: dict, f: Findings) -> str:
    cob = cobertos(d["riscos"])
    linhas = [
        # Cabeçalho CANÔNICO (CP-029) — mesmo formato de ci/generate_graph.py.
        "<!-- GENERATED: não editar; rodar ci/alignment_report.py -->",
        "<!-- O --check do CI contradiz qualquer edição manual: edita-se a FONTE, não o derivado. -->",
        "# Alinhamento entre departamentos",
        "",
        "Matriz derivada do metadado declarado. Ela responde a pergunta que os demais fiscais não",
        "fazem: **o que ficou de fora?**",
        "",
        "## Cobertura de risco por capacidade",
        "",
        "| Capacidade | risk_level | Riscos que a cobrem |",
        "|---|---|---|",
    ]
    for cap in sorted(d["caps"], key=lambda c: c.get("id", "")):
        cid = cap.get("id", "?")
        riscos = sorted(r["id"] for r in d["riscos"] if cid in (r.get("related") or []))
        linhas.append(f"| `{cid}` | {cap.get('risk_level')} | "
                      f"{', '.join(f'`{r}`' for r in riscos) or '—'} |")

    linhas += ["", "## Componentes", "",
               "| Componente | Status | Capacidade | Implementa | Coberto por risco |",
               "|---|---|---|---|---|"]
    for comp in sorted(d["comps"], key=lambda c: c.get("id", "")):
        cid = comp.get("id", "?")
        linhas.append(f"| `{cid}` | {comp.get('status')} | `{comp.get('capability')}` | "
                      f"{', '.join(comp.get('implements') or []) or '—'} | "
                      f"{'sim' if cid in cob else 'não'} |")

    linhas += ["", "## Riscos por área", "", "| Área | Total | Abertos |", "|---|---|---|"]
    areas = sorted({r.get("area") for r in d["riscos"]})
    for area in areas:
        do_area = [r for r in d["riscos"] if r.get("area") == area]
        linhas.append(f"| {area} | {len(do_area)} | "
                      f"{sum(1 for r in do_area if r.get('status') == 'open')} |")

    pendentes = f.blocking()
    linhas += ["", "## Pendências de alinhamento", ""]
    if not pendentes:
        linhas.append("Nenhuma. Todo ativo relevante está coberto ou tem isenção declarada.")
    else:
        for item in f.sorted_items():
            if item["severity"] == "info":
                continue
            linhas.append(f"- **[{item['severity']}]** `{item['id']}` — {item['summary']}")
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alinhamento e cobertura reversa de risco.")
    parser.add_argument("--check", action="store_true",
                        help="não escreve; falha se docs/alignment.md estiver desatualizado")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    findings, errors = Findings(), Errors()
    try:
        d = coletar()
        for regra in (r1_capacidade_de_alto_risco_sem_risco, r2_risco_aberto_sem_prazo,
                      r3_superficie_orfa, r4_componente_sem_justificativa, isencao_morta):
            regra(d, findings)
        conteudo = render(d, findings)
        emit_report(LAUDO, build_report(
            auditor="ci/alignment_report.py", auditor_version="1.0", findings=findings,
            stages_covered=["STAGE-GOVERNANCE"],
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds")))
    except HarnessError as exc:
        print(f"✗ alinhamento: {exc}", file=sys.stderr)
        return 2

    atual = hl.read_text(DOC) if hl.rel_exists(DOC) else None
    if args.check:
        if atual != conteudo:
            print(f"✗ {DOC} desatualizado — rode: python ci/alignment_report.py", file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"✓ {DOC} em dia.")
    else:
        (hl.REPO / DOC).write_text(conteudo, encoding="utf-8")
        if not args.quiet:
            print(f"✓ escrito {DOC}")

    hl.print_summary("alinhamento", findings, errors, quiet=args.quiet)
    if errors:
        return 2
    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
