#!/usr/bin/env python3
"""Runner genérico — executa uma régua A PARTIR DA FICHA, e traduz o veredito ao CI.

A CP-041 fez a ficha DESCREVER; esta faz a ficha EXECUTAR. Sem isto o registro é um catálogo:
ele diz que a qa-suite tem modos, perfil, laudo e veredito, e nada disso é lido por quem realmente
roda a régua. Uma ficha que ninguém executa é documentação com schema.

O DEFEITO QUE ESTE ARQUIVO EXISTE PARA PEGAR está na tradução do veredito. Hoje, suíte ausente
produz `::warning::` e exit 0 — "não consegui medir" sai com a mesma cor de "medi e está bom", e a
cor mais barata vence por hábito. Aqui, `inconclusivo` **não é verde**. Enquanto o gap
`GAP-QA-EXIT-ZERO` vigora, ele avisa sem reprovar; vencida a data do gap, o mesmo código reprova.
O que fecha a tolerância é a data declarada, nunca o esquecimento.

NÃO CONHECE SUÍTE ALGUMA. Não há `if nome == …` aqui. O que ele sabe fazer vem da ficha: modos,
comando por modo, perfil, envelope do laudo, evento de ledger. Acrescentar uma régua não edita
este arquivo — se editar, a padronização não aconteceu e o achado é sobre este runner.

Uso:  python ci/suite_runner.py --suite NOME --mode MODO [--dry-run] [--quiet]
Saída (os códigos do WEBQA_CONSUMER_CONTRACT, §6, deliberadamente):
  0  conforme (o veredito vem DECLARADO no laudo; este runner não infere mais)
  1  não-conforme (a régua mediu e reprovou, ou o veredito é inconclusivo com o gap vencido)
  2  o runner não conseguiu rodar (ficha ilegível, envelope ausente)
  11 MODE_FORBIDDEN — modo exige gate humano e ele não foi dado
  40 CONFIG_INVALID — laudo fora do envelope que a própria ficha declara
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import harness_lib as hl
from harness_lib import HarnessError

MODE_FORBIDDEN = 11
CONFIG_INVALID = 40

RUNNER_VERSION = "1.0"


class Autorizacao(Exception):
    """O modo não é permitido por esta ficha. Distinto de erro e de achado: vira exit 11."""


def carregar_ficha(nome: str) -> dict:
    rel = f"harness/suites/{nome}.yaml"
    if not hl.rel_exists(rel):
        raise HarnessError(
            f"não existe ficha para '{nome}' em {rel}. Uma régua entra por ficha — se ela não "
            f"está no registro, ela não é consumida por este projeto.")
    doc = hl.read_yaml(rel)
    problemas = hl.schema_errors(rel, "suite-registry.schema.json", doc)
    if problemas:
        raise HarnessError(f"{rel} não satisfaz o schema do registro:\n  " + "\n  ".join(problemas))
    return doc["suite"]


def resolver_modo(suite: dict, modo: str, autorizado: bool) -> dict:
    """Encontra o modo na ficha e recusa o que a ficha não autoriza.

    A recusa vem ANTES de qualquer execução, e o código é o do contrato do consumidor (11), não um
    genérico: quem lê o log precisa distinguir "a régua reprovou" de "eu não tinha direito de
    rodar isto", porque as duas reações são diferentes.
    """
    for m in suite.get("modes") or []:
        if m["nome"] == modo:
            if m["requires_gate"] and not autorizado:
                raise Autorizacao(
                    f"o modo '{modo}' de {suite['nome']} exige gate humano (requires_gate: true) e "
                    f"--gate-autorizado não foi dado. Modos pesados são disparados por pessoa, em "
                    f"job segregado — nunca por um agente que decidiu sozinho.")
            return m
    disponiveis = ", ".join(sorted(m["nome"] for m in suite.get("modes") or [])) or "nenhum"
    raise Autorizacao(
        f"{suite['nome']} não declara o modo '{modo}' (declara: {disponiveis}). Rodar um modo que "
        f"a ficha não oferece é agir fora do que foi autorizado, não um erro de digitação.")


def montar_comando(suite: dict, modo: dict) -> list[str]:
    """Substitui os placeholders. Desconhecido é ERRO, jamais texto literal.

    Substituição silenciosa produziria um comando que roda e mede outra coisa — e um laudo de
    outra coisa é pior que laudo nenhum, porque parece resposta.
    """
    valores = {
        "entrypoint": suite.get("entrypoint", ""),
        "perfil": suite.get("perfil_path", ""),
        "laudo": (suite.get("laudo") or {}).get("path", ""),
    }
    argv: list[str] = []
    for bruto in modo["command"]:
        peca = bruto
        for chave, valor in valores.items():
            peca = peca.replace("{" + chave + "}", valor)
        if "{" in peca and "}" in peca:
            raise HarnessError(
                f"placeholder desconhecido em {suite['nome']}/{modo['nome']}: {bruto!r}. "
                f"Conhecidos: {sorted(valores)}. Deixá-lo passar como literal faria o comando "
                f"rodar e medir outra coisa.")
        argv.append(peca)
    return argv


def traduzir_veredito(laudo: dict) -> tuple[str, str]:
    """(veredito, razão) LIDOS do laudo. A inferência foi APAGADA, e é essa a notícia.

    Esta função inferia. Com a régua emitindo `schema_version: 1.0` sem `verdict`, alguém
    precisava dizer o que aquele laudo significava, e um código auditável era melhor que o
    silêncio de um exit 0 — era a ponte declarada do `GAP-QA-ENVELOPE`.

    A régua assumiu o defeito na origem: emite `verdict`, `verdict_reason` e o fingerprint
    completo (contract-v1, schema 1.3), com o veredito carimbado pela mesma função que decide o
    código de saída do `webqa-veredicto`, e roda o kit da contract-v1 no CI DELA sobre o laudo
    que acabou de emitir. Com isso a inferência deixou de ser ponte: ela passaria a ser um
    SEGUNDO lugar onde o veredito é decidido, e o primeiro dia em que os dois discordassem seria
    o dia em que ninguém saberia qual está certo.

    Laudo sem `verdict` agora é erro, e a assimetria é deliberada: um laudo que não diz o que
    significa não é um laudo mais fraco — é um laudo que exige adivinhação, e este consumidor
    prefere ficar vermelho a adivinhar. O STUB desta casa (régua ausente) declara o dele: ele é
    construído aqui, então tem obrigação de dizer o que quer dizer.
    """
    if "verdict" not in laudo:
        raise HarnessError(
            "o laudo não declara `verdict`. Quem mede é quem sabe: a régua emite o veredito no "
            "envelope (contract-v1, schema 1.3), e este runner não infere mais.")
    return laudo["verdict"], laudo.get("verdict_reason", "declarado pela régua")


def gap_vigente(suite: dict, clausula: str, hoje: date) -> dict | None:
    """O gap que ainda segura a linha aberta — None se não há, ou se venceu."""
    for gap in suite.get("gaps") or []:
        if gap["clause"] != clausula:
            continue
        try:
            if date.fromisoformat(gap["due"]) >= hoje:
                return gap
        except ValueError:
            continue
    return None


def validar_envelope(suite: dict, laudo: dict) -> list[str]:
    esquema = (suite.get("laudo") or {}).get("schema", "")
    nome = Path(esquema).name
    return hl.schema_errors((suite.get("laudo") or {}).get("path", "?"), nome, laudo)


def registrar_no_ledger(suite: dict, veredito: str, laudo: dict) -> None:
    """Um evento por execução — o veredito vira evidência que não se reescreve.

    É o que faz `inconclusivo` deixar de sumir: mesmo quando o gap segura o CI verde, o estado
    fica registrado no ledger, e alguém pode contar quantas vezes não se conseguiu medir.
    """
    import audit_ledger

    evento = {
        "schema_version": "1.0",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": suite["ledger_event_kind"],
        "commit_sha": os.environ.get("GITHUB_SHA", "0" * 40),
        "result": {"conforme": "pass", "nao_conforme": "fail"}.get(veredito, "unverifiable"),
        "fiscal": "ci/suite_runner.py",
    }
    achados = laudo.get("findings") or []
    if achados:
        evento["findings_count"] = len(achados)
        evento["findings_digest"] = "sha256:" + hl.sha256_canonical(achados)
    audit_ledger.main(["--append", json.dumps(evento), "--quiet"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa uma régua a partir da ficha.")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--gate-autorizado", action="store_true",
                        help="a pessoa autorizou este modo; só o CI segregado deve passar isto")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve a ficha e imprime o comando, sem executar")
    parser.add_argument("--sem-ledger", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        suite = carregar_ficha(args.suite)
    except HarnessError as exc:
        print(f"✗ runner: {exc}", file=sys.stderr)
        return 2

    if suite["status"] != "active":
        print(f"✗ runner: {args.suite} está '{suite['status']}', não 'active'. Uma régua que ainda "
              f"não existe não pode produzir laudo, e fingir que produziu é o verde por não olhar.",
              file=sys.stderr)
        return 2

    try:
        modo = resolver_modo(suite, args.mode, args.gate_autorizado)
        comando = montar_comando(suite, modo)
    except Autorizacao as exc:
        print(f"✗ MODE_FORBIDDEN: {exc}", file=sys.stderr)
        return MODE_FORBIDDEN
    except HarnessError as exc:
        print(f"✗ runner: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({"suite": args.suite, "mode": args.mode, "comando": comando},
                         ensure_ascii=False))
        return 0

    laudo_rel = (suite.get("laudo") or {}).get("path")
    laudo_abs = hl.REPO / laudo_rel
    laudo_abs.parent.mkdir(parents=True, exist_ok=True)

    hoje = date.today()

    if shutil.which(comando[0]) is None:
        # Régua não instalada. ANTES isto era ::warning:: e exit 0; agora é um laudo de verdade,
        # com veredito inconclusivo, que o resto desta função trata como qualquer outro.
        # O stub DECLARA o veredito dele. Antes ele emitia `schema_version: 1.0` sem `verdict` e
        # a tradução inferia — e a inferência morreu quando a régua passou a declarar. Um stub
        # que continuasse mudo obrigaria a inferência a sobreviver só para ele, o que é o mesmo
        # que dizer que ela nunca morreu: quem constrói o laudo tem obrigação de dizer o que ele
        # quer dizer, e aqui quem constrói é esta casa.
        laudo = {
            "schema_version": "1.3",
            "standard": {"name": suite["nome"], "version": "UNINSTALLED",
                         "commit": "UNINSTALLED", "sensitive_paths_hash": "UNINSTALLED"},
            "consumer_project": {"repository": os.environ.get("GITHUB_REPOSITORY", "local"),
                                 "commit": os.environ.get("GITHUB_SHA", "unknown")},
            "execution": {"run_id": os.environ.get("GITHUB_RUN_ID", "local"), "mode": args.mode,
                          "network_used": False, "active_gates": [], "runner_kind": "ci"},
            "result": "suite_not_installed",
            "verdict": "inconclusivo",
            "verdict_reason": (f"'{comando[0]}' não está no PATH: a régua não foi instalada, "
                               f"então nada foi medido. Não medir não é medir e passar."),
            "findings": [],
        }
        laudo_abs.write_text(json.dumps(laudo, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    else:
        # Sem shell, de propósito: `--config $ARQUIVO` num shell deixa de ser um argumento e vira
        # uma oportunidade. O argv já vem separado da ficha.
        proc = subprocess.run(comando, cwd=hl.REPO, capture_output=True, text=True)
        if not args.quiet:
            sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if not laudo_abs.exists():
            print(f"✗ runner: {comando[0]} rodou (exit {proc.returncode}) e não deixou laudo em "
                  f"{laudo_rel}. Execução sem laudo é execução que ninguém pode auditar.",
                  file=sys.stderr)
            return 2
        try:
            laudo = json.loads(laudo_abs.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"✗ CONFIG_INVALID: laudo ilegível em {laudo_rel}: {exc}", file=sys.stderr)
            return CONFIG_INVALID

    problemas = validar_envelope(suite, laudo)
    if problemas:
        print(f"✗ CONFIG_INVALID: o laudo de {args.suite} não satisfaz o envelope que a própria "
              f"ficha declara:", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        return CONFIG_INVALID

    try:
        veredito, razao = traduzir_veredito(laudo)
    except HarnessError as exc:
        print(f"✗ CONFIG_INVALID: {exc}", file=sys.stderr)
        return CONFIG_INVALID

    if not args.sem_ledger:
        try:
            registrar_no_ledger(suite, veredito, laudo)
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::não foi possível registrar no ledger: {exc}", file=sys.stderr)

    if veredito == "conforme":
        if not args.quiet:
            print(f"✓ {args.suite}/{args.mode}: conforme ({razao}).")
        return 0

    if veredito == "nao_conforme":
        print(f"✗ {args.suite}/{args.mode}: NÃO CONFORME — {razao}.", file=sys.stderr)
        return 1

    # inconclusivo: o estado que antes saía 0. O gap datado é o que decide a cor, e ele expira.
    gap = gap_vigente(suite, "envelope-com-3-estados", hoje)
    if gap:
        print(f"::warning::{args.suite}/{args.mode}: INCONCLUSIVO — {razao}. Não reprova porque "
              f"{gap['id']} vigora até {gap['due']}; o veredito está no ledger. Vencido o gap, "
              f"isto passa a reprovar.", file=sys.stderr)
        return 0

    print(f"✗ {args.suite}/{args.mode}: INCONCLUSIVO — {razao}. Sem gap vigente cobrindo a "
          f"cláusula do envelope, 'não consegui medir' não pode sair verde: um verde que significa "
          f"'não olhei' encerra a investigação com a convicção de quem olhou.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
