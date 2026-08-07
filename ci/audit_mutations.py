#!/usr/bin/env python3
"""Prova de fogo 4 — toda regra bloqueante reprova a mutação canônica que a nega.

A PERGUNTA QUE ESTE FISCAL FAZ é diferente de todas as outras: não "o repositório está conforme?",
mas "as travas ainda mordem?". Um repositório verde com travas que não mordem é indistinguível de
um repositório verde — e é o único estado que este sistema inteiro existe para impedir.

COMO A MUTAÇÃO É OBTIDA, e aqui houve uma decisão. O plano pede que "cada controle bloqueante
declare nos metadados a mutação mínima que deve reprovar" e, na mesma frase, que a suíte seja
"derivada dos metadados, nunca de lista duplicada". Escrever um bloco `mutation:` à mão para cada
asserção SERIA a lista duplicada — ela derivaria da asserção real no primeiro dia em que alguém
mudasse um `pattern` e esquecesse o bloco.

(O número de asserções provadas NÃO é restatado em lugar nenhum, e a razão é uma correção: as
contagens escritas na prosa — deste módulo, da política e do workflow — diziam 118 quando o real
já era 163. É a doutrina do "não restatar a versão da régua" aplicada ao próprio fiscal; número
copiado deriva, e este derivou. O fiscal IMPRIME quantas provou, e quem quiser o número lê o
laudo.)

A leitura adotada: **a mutação é DERIVADA da asserção**, porque cada tipo de asserção tem um
inverso bem definido (o que existe passa a não existir; o padrão exigido some; a trava de schema
muda de valor). Uma asserção pode DECLARAR `mutation` explicitamente, e a declaração vence — é o
escape para os casos que a derivação não alcança.

E a parte que dá dentes: **a mutação derivada é VERIFICADA**. O fiscal aplica a mutação e exige
que a asserção correspondente fique vermelha. Se não ficar, o achado não é sobre o repositório —
é sobre a própria asserção, que passa a ser decorativa. É a regra bloqueante reprovando a si
mesma, como o plano pede.

O QUE SOBROU AQUI, e por quê. O MOTOR — derivar o inverso, aplicar, desfazer — mora em
`harness/suite-contract/mutation-engine/` desde o CP-041 e é consumido POR PIN, com sha256 no
`contract-manifest.json` da contract-v1. Ele não sabe nada deste repositório e por isso serve
tanto ao molde quanto a qualquer suíte que queira provar as próprias travas.

Este arquivo guarda o que é IRREDUTIVELMENTE daqui: o índice de ADRs como fonte das asserções, o
fiscal de conformidade como juiz, o protocolo `HARNESS_REPO_ROOT` e a cópia do repositório. A
divisão não é estética — é a fronteira entre "como se nega uma asserção" (qualquer um) e "quais
asserções existem e quem as julga" (só este repositório).

Uso:  python ci/audit_mutations.py [--quiet] [--json] [--only ADR-XXX-AN]
Saída: 0 todas mordem · 1 alguma não morde ou não tem mutação · 2 não foi possível provar.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AUDITOR_VERSION = "1.1"
REPORT_PATH = "harness/reports/mutation-audit.json"

MOTOR_DIR = "harness/suite-contract/mutation-engine"


def _motor(raiz: Path | None = None):
    """Importa o motor compartilhado a partir da árvore REAL, nunca da cópia mutada.

    A distinção é a única sutileza deste import. `provar()` aponta `HARNESS_REPO_ROOT` para uma
    cópia e recarrega os fiscais contra ela — é o que faz a mutação ser julgada no lugar certo.
    O motor NÃO acompanha esse movimento: ele é a régua que mede, e uma régua que se deixa mutar
    junto com o medido carimbaria qualquer coisa. Uma mutação que apagasse um operador do motor
    faria as asserções seguintes pararem de morder, e o fiscal culparia as ASSERÇÕES.
    """
    origem = raiz or Path(__file__).resolve().parent.parent
    caminho = str((origem / MOTOR_DIR).resolve())
    if caminho not in sys.path:
        sys.path.insert(0, caminho)
    import mutation_engine

    return mutation_engine


def _asserções_bloqueantes(doc: dict) -> list[tuple[str, dict]]:
    out = []
    for adr in (doc or {}).get("adrs", []):
        for a in adr.get("assertions") or []:
            if a.get("kind") == "manual":
                continue  # existe para dizer que NÃO é verificável; mutá-la não prova nada
            out.append((adr.get("id", "?"), a))
    return out


def provar(raiz: Path, apenas: str | None = None) -> tuple[list[dict], int]:
    """Aplica cada mutação e exige que a asserção correspondente fique vermelha."""
    import importlib
    import os

    motor = _motor()

    os.environ["HARNESS_REPO_ROOT"] = str(raiz)
    import harness_lib as hl
    importlib.reload(hl)
    import audit_governance as ag
    importlib.reload(ag)

    doc = hl.read_yaml("architecture/adr/index.yaml")
    achados: list[dict] = []
    provadas = 0

    for adr_id, a in _asserções_bloqueantes(doc):
        aid = a.get("id", "?")
        if apenas and aid != apenas:
            continue
        mut = motor.derivar_mutacao(a)
        if mut is None:
            achados.append({
                "assertion": aid, "adr": adr_id, "problema": "mutacao_nao_derivavel",
                "detalhe": f"o inverso de {a.get('kind')} com este padrão não é mecanicamente "
                           f"derivável, e a asserção não declara `mutation` — uma regra bloqueante "
                           f"sem mutação não pode provar que morde.",
            })
            continue

        antes = motor.aplicar(mut, raiz)
        if not antes:
            achados.append({
                "assertion": aid, "adr": adr_id, "problema": "alvo_inexistente",
                "detalhe": f"a mutação não encontrou '{mut['alvo']}' — asserção que vigia o que "
                           f"não existe está quebrada, não satisfeita (ADR-006).",
            })
            continue
        try:
            findings, errors = hl.Findings(), hl.Errors()
            ag.check_adr_conformance(hl.read_yaml("architecture/adr/index.yaml"), findings, errors)
            mordeu = any(f.get("assertion") == aid for f in findings.blocking())
        finally:
            motor.restaurar(antes, raiz)

        if mordeu:
            provadas += 1
        else:
            achados.append({
                "assertion": aid, "adr": adr_id, "problema": "nao_morde",
                "detalhe": f"a mutação canônica ({mut['op']} em {mut['alvo']}) foi aplicada e "
                           f"{aid} continuou verde — a asserção é decorativa.",
            })
    return achados, provadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prova de mutação canônica.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--only", help="prova uma asserção só (ex.: ADR-001-A1)")
    parser.add_argument("--report", default=REPORT_PATH)
    args = parser.parse_args(argv)

    origem = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="mutacao-") as tmp:
        copia = Path(tmp) / "repo"
        shutil.copytree(origem, copia, ignore=shutil.ignore_patterns(*_motor().SKIP))
        try:
            achados, provadas = provar(copia, args.only)
        except Exception as exc:  # noqa: BLE001 - não conseguir provar é exit 2, nunca 0
            print(f"✗ mutação: não foi possível provar ({exc})", file=sys.stderr)
            return 2

    laudo = {
        "schema_version": "1.0",
        "auditor": "ci/audit_mutations.py",
        "auditor_version": AUDITOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assertions_proved": provadas,
        "findings": achados,
        "result": "fail" if achados else "pass",
    }
    destino = origem / args.report
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(laudo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(laudo, indent=2, ensure_ascii=False))
    elif achados:
        print(f"✗ mutação: {len(achados)} regra(s) bloqueante(s) não provaram que mordem "
              f"({provadas} provadas):", file=sys.stderr)
        for a in achados:
            print(f"  - [{a['problema']}] {a['assertion']} ({a['adr']}): {a['detalhe']}",
                  file=sys.stderr)
    elif not args.quiet:
        print(f"✓ mutação: {provadas} regra(s) bloqueante(s) reprovaram sua mutação canônica.")

    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
