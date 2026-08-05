#!/usr/bin/env python3
"""Fiscal de atrito, estágio 1 — o único fiscal desta casa que NUNCA reprova.

A pergunta que ele faz não é "o repositório está errado?", é "as travas estão custando caro demais
no mesmo lugar?". Um sistema de governança que só mede violações otimiza para mais travas, porque
trava nova sempre parece barata para quem a escreve e nunca para quem a atravessa. Este fiscal é o
contrapeso: ele mede o CUSTO, e entrega ao comitê, que decide.

Ele nunca é gate, e essa é uma decisão, não uma limitação. Um medidor de atrito que reprovasse
criaria o incentivo de não declarar propostas para manter o número baixo — destruindo exatamente o
registro de onde ele tira o sinal.

DOIS SINAIS:

  (1) DRIFT REPETIDO (definição inicial, ajustável por CP futura, §9 do plano): mesmo `risk_level`
      + mesmo path afetado + menos de 7 dias entre propostas. Duas propostas de mesmo risco
      batendo no mesmo arquivo em menos de uma semana não é produtividade — é uma trava restritiva
      demais ou um processo que não converge.

  (2) VERMELHO TRANSITÓRIO (Adendo A2): os achados de uma validação executada enquanto há CP
      `high` aberta. É a evidência mais rica de atrito e a que hoje escapa de todo registro — runs
      vermelhos de transição não chegam a lugar nenhum. Se a MESMA capacidade aparece como ponto
      de quebra em CPs consecutivas de natureza diferente, o mal-fatorado é a capacidade, não as
      CPs que a tocam.

Uso:  python ci/audit_friction.py [--quiet] [--json] [--snapshot]
Saída: SEMPRE 0. Achado de atrito é informação para o comitê, jamais gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import harness_lib as hl
from harness_lib import HarnessError

AUDITOR_VERSION = "1.0"
REPORT_PATH = "harness/reports/friction-audit.json"
PROPOSALS_DIR = "harness/change-proposals"

# A janela do critério. Nomeada e num lugar só para que ajustá-la seja um ato visível, com CP —
# e não um número trocado no meio de uma condição.
JANELA_DRIFT_DIAS = 7

# Estados em que uma proposta ainda está "aberta": o trabalho dela não terminou, então um vermelho
# concomitante pode ser transição em vez de regressão.
ABERTAS = {"draft", "approved", "deferred"}


def _propostas() -> list[dict]:
    """Lidas do diretório, com o caminho junto. Nunca de uma lista mantida à mão."""
    out = []
    d = hl.REPO / PROPOSALS_DIR
    if not d.exists():
        return out
    for path in sorted(d.glob("*.yaml")):
        try:
            doc = hl.read_yaml(hl.rel(path)) or {}
        except HarnessError:
            continue
        p = doc.get("proposal")
        if p:
            out.append({**p, "_file": hl.rel(path)})
    return out


def _quando(proposta: dict) -> datetime | None:
    bruto = proposta.get("created_at")
    if not bruto:
        return None
    try:
        return datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return None


def detectar_drift(propostas: list[dict], janela_dias: int = JANELA_DRIFT_DIAS) -> list[dict]:
    """Pares de propostas que satisfazem o critério. Função pura: entra lista, sai lista.

    Compara PARES em vez de agrupar por path e contar, porque o intervalo é parte do critério: três
    propostas sobre o mesmo arquivo ao longo de um ano não são drift, e um agrupador que só contasse
    diria que sim.
    """
    sinais: list[dict] = []
    for i, a in enumerate(propostas):
        for b in propostas[i + 1:]:
            nivel_a = (a.get("risk_assessment") or {}).get("level")
            nivel_b = (b.get("risk_assessment") or {}).get("level")
            if nivel_a != nivel_b or nivel_a is None:
                continue
            comuns = sorted(set(a.get("paths_affected") or []) & set(b.get("paths_affected") or []))
            if not comuns:
                continue
            qa, qb = _quando(a), _quando(b)
            if qa is None or qb is None:
                continue
            dias = abs((qb - qa).days)
            if dias >= janela_dias:
                continue
            sinais.append({
                "kind": "drift_repetido",
                "proposals": sorted([a.get("id", "?"), b.get("id", "?")]),
                "risk_level": nivel_a,
                "paths": comuns,
                "days_apart": dias,
                "reading": "mesmo risco, mesmo caminho, menos de "
                           f"{janela_dias} dias — sinal de trava restritiva demais ou de processo "
                           "que não converge. Informação para o comitê, nunca gate.",
            })
    return sinais


def capturar_vermelho_transitorio(propostas: list[dict], achados: list[dict]) -> list[dict]:
    """Snapshot dos achados enquanto há CP `high` ABERTA (Adendo A2).

    Sem isto, o vermelho de uma cascata em andamento não chega a registro algum: ele é resolvido e
    esquecido, e a informação de QUAL artefato quebra sempre se perde junto. Associar o snapshot ao
    ID da CP é o que torna a pergunta seguinte respondível — a mesma CAP aparece como ponto de
    quebra em CPs de natureza diferente?
    """
    abertas = [p for p in propostas
               if p.get("status") in ABERTAS
               and (p.get("risk_assessment") or {}).get("level") in ("high", "critical")]
    if not abertas or not achados:
        return []
    return [{
        "kind": "vermelho_transitorio",
        "under_proposals": sorted(p.get("id", "?") for p in abertas),
        "finding_count": len(achados),
        "breaking_points": sorted({a.get("location") or a.get("stage") or a.get("adr") or "?"
                                   for a in achados}),
        "reading": "achados registrados durante cascata sob CP aberta. Vermelho de transição é "
                   "mapa da mudança; o que importa aqui é se o MESMO ponto quebra em CPs de "
                   "natureza diferente.",
    }]


def _achados_correntes() -> list[dict]:
    """Lê o laudo de conformidade já emitido. Não roda fiscal nenhum: um medidor de atrito que
    disparasse a validação inteira passaria a custar exatamente aquilo que ele mede."""
    laudo = hl.REPO / "harness/reports/governance-audit.json"
    if not laudo.exists():
        return []
    try:
        return json.loads(laudo.read_text(encoding="utf-8")).get("findings", [])
    except (json.JSONDecodeError, OSError):
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fiscal de atrito (informativo, nunca gate).")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--snapshot", action="store_true",
                        help="captura o vermelho transitório junto do drift")
    parser.add_argument("--report", default=REPORT_PATH)
    args = parser.parse_args(argv)

    propostas = _propostas()
    sinais = detectar_drift(propostas)
    if args.snapshot:
        sinais.extend(capturar_vermelho_transitorio(propostas, _achados_correntes()))

    laudo = {
        "schema_version": "1.0",
        "auditor": "ci/audit_friction.py",
        "auditor_version": AUDITOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proposals_read": len(propostas),
        "window_days": JANELA_DRIFT_DIAS,
        "signals": sinais,
        "gate": False,
    }
    destino = hl.REPO / args.report
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(laudo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(laudo, indent=2, ensure_ascii=False))
    elif not args.quiet:
        if sinais:
            print(f"• atrito: {len(sinais)} sinal(is) sobre {len(propostas)} proposta(s) — "
                  f"informação para o comitê, nunca gate.")
            for s in sinais:
                print(f"  - {s['kind']}: {s.get('proposals') or s.get('under_proposals')}")
        else:
            print(f"• atrito: nenhum sinal sobre {len(propostas)} proposta(s).")

    # SEMPRE 0. Ver o cabeçalho: um medidor de atrito que reprova cria o incentivo de não declarar
    # propostas, destruindo o registro de onde ele tira o sinal.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
