#!/usr/bin/env python3
"""Fiscal genérico do Contrato de Régua — as cinco cláusulas, cobradas por ficha.

A PERGUNTA. `WEBQA_CONSUMER_CONTRACT.md` responde "o que este consumidor promete à suíte?".
Este fiscal responde a outra, que não tinha onde ser feita: **"o que a suíte entrega em troca?"**.
Sem ela, um defeito da régua — sem tag, laudo que sai 0 declarando-se inconclusivo — não tinha
lugar onde aparecer como achado, e defeito sem lugar onde aparecer é indistinguível de ausência
de defeito.

O QUE ELE NÃO FAZ, e é o critério de sucesso do CP-041: ele não conhece suíte alguma. Não há
`if nome == "qa-suite"` aqui, nem caminho de régua cravado. Ele lê `harness/suites/*.yaml`, e uma
régua nova entra por FICHA — se acrescentar uma exigir editar este arquivo, a padronização não
aconteceu e o achado é sobre este fiscal.

A AUTOPROVA (cláusula 5, padrão do CP-030). Antes de julgar suite alguma, ele exige que cada
cláusula do contrato declare a mutação canônica que a nega e o achado que ela deve produzir. Sem
isso ele **reprova a si mesmo**: um fiscal que não sabe como seria negado não sabe se está
funcionando. A prova roda sobre uma CÓPIA do repositório e usa o mesmo motor compartilhado que
`ci/audit_mutations.py` consome — por pin, nunca copiado.

Uso:  python ci/audit_suites.py [--quiet] [--skip-autoprova]
Saída: 0 conforme · 1 divergência · 2 o fiscal não conseguiu fiscalizar.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import harness_lib as hl
from harness_lib import HarnessError

AUDITOR_VERSION = "1.0"
REPORT_PATH = "harness/reports/suites-audit.json"

SUITES_DIR = "harness/suites"
CONTRACT_DIR = "harness/suite-contract"
MOTOR_DIR = f"{CONTRACT_DIR}/mutation-engine"

# As cinco cláusulas da contract-v1. Restatadas aqui de propósito E conferidas contra o manifesto:
# o fiscal precisa saber o que cobrar antes de ler o manifesto, senão um manifesto com quatro
# cláusulas passaria por completo. Restatar sem conferir seria deriva; conferir é o que torna a
# segunda cópia uma trava em vez de um risco.
CLAUSULAS = (
    "pin-fonte-unica",
    "release-com-manifesto",
    "envelope-com-3-estados",
    "fingerprint",
    "autoprova-de-mordida",
)

FINGERPRINT_CANONICO = ("name", "version", "commit", "catalog_hash", "schema_version")


def contract_dir(versao: str) -> str:
    return f"{CONTRACT_DIR}/contract-{versao}"


def manifest_path(versao: str) -> str:
    return f"{contract_dir(versao)}/contract-manifest.json"


def _motor():
    """O motor compartilhado, importado da árvore real. Ver ci/audit_mutations.py::_motor."""
    caminho = str((hl.REPO / MOTOR_DIR).resolve())
    if caminho not in sys.path:
        sys.path.insert(0, caminho)
    import mutation_engine

    return mutation_engine


# --------------------------------------------------------------------------------------
# Leitura do registro
# --------------------------------------------------------------------------------------

def carregar_fichas(errors: hl.Errors) -> dict[str, dict]:
    """Lê o registro. Diretório ausente é INDETERMINAÇÃO, jamais 'nenhuma suite'.

    A assimetria é a mesma de `ci/env_guard.py::_exigida`, e pela mesma razão: um registro que
    some faria este fiscal reportar "0 suites, todas conformes" — um tique verde afirmando que
    zero réguas não violaram nada. Some com ele a denylist derivada, que é o efeito caro.
    """
    diretorio = hl.REPO / SUITES_DIR
    if not diretorio.is_dir():
        errors.err(f"{SUITES_DIR}/ não existe. Registro ausente é 'não consegui fiscalizar', "
                   f"jamais 'nenhuma régua a conferir' — e é dele que a denylist de ambiente "
                   f"deriva, então o silêncio aqui desliga uma trava lá.")
        return {}

    fichas: dict[str, dict] = {}
    for caminho in sorted(diretorio.glob("*.yaml")):
        rel = hl.rel(caminho)
        try:
            doc = hl.read_yaml(rel)
        except HarnessError as exc:
            errors.err(str(exc))
            continue
        problemas = hl.schema_errors(rel, "suite-registry.schema.json", doc)
        if problemas:
            for p in problemas:
                errors.err(p)
            continue
        fichas[rel] = doc
    return fichas


def env_prefixes(errors: hl.Errors | None = None) -> list[str]:
    """Os prefixos de ambiente DERIVADOS do registro — a prova cruzada com o CP-025.

    Ponto de entrada usado por `ci/env_guard.py` e pelo hook de Bash. Ele levanta em vez de
    devolver lista vazia: o chamador precisa distinguir "nenhuma suite declara prefixo" de "não
    consegui ler o registro", e as duas leituras produzem denylists muito diferentes.
    """
    locais = hl.Errors()
    fichas = carregar_fichas(locais)
    if locais:
        if errors is not None:
            for e in locais.items:
                errors.err(e)
        raise HarnessError("; ".join(locais.items))
    return sorted({d["suite"]["env_prefix"] for d in fichas.values()})


# --------------------------------------------------------------------------------------
# As cinco cláusulas
# --------------------------------------------------------------------------------------

def check_clausula_pin(rel: str, suite: dict, findings: hl.Findings) -> None:
    """Cláusula 1 — a versão mora num lugar só, e a ficha diz ONDE, nunca QUAL."""
    nome = suite["nome"]
    pin_source = suite["pin_source"]

    if not hl.rel_exists(pin_source):
        # Régua PLANEJADA ainda não tem pin, e isso é o estado correto — o que a ficha declara é
        # o LUGAR da versão, decidido antes do conteúdo justamente para que a v0.1 não nasça com
        # a versão espalhada. Mas "ainda não" só é aceitável DECLARADO: exige gap cobrindo esta
        # cláusula, pela mesma regra da cláusula 2. Sem o gap, 'planned' viraria o rótulo que
        # dispensa a cláusula 1 para sempre.
        coberto = any(g["clause"] == "pin-fonte-unica" for g in suite.get("gaps") or [])
        if suite["status"] == "planned" and coberto:
            return
        findings.add(
            key=f"SUITE-{nome}-PIN-INEXISTENTE", origin="suite_contract", severity="critical",
            summary=f"{nome}: pin_source '{pin_source}' não existe. Ficha que aponta para o vazio "
                    f"declara uma fonte única que ninguém pode ler — quebrada, não satisfeita.",
            location=rel, risk="RISK-DEP-001",
            remediation=f"Criar {pin_source} com o pin exato, corrigir pin_source, ou — se a "
                        f"régua ainda não existe — declarar um gap com clause: pin-fonte-unica.")
        return

    # A versão NÃO pode aparecer na ficha: seria o segundo lugar, e o segundo lugar deriva.
    import re

    texto = hl.read_text(rel)
    for linha in texto.splitlines():
        despido = linha.split("#", 1)[0]
        if re.search(r"\b\d+\.\d+\.\d+\b", despido):
            findings.add(
                key=f"SUITE-{nome}-PIN-RESTATADO", origin="suite_contract", severity="high",
                summary=f"{nome}: a ficha restata um semver ({despido.strip()!r}). A versão mora "
                        f"só em {pin_source}; um segundo lugar deriva, e o primeiro a divergir é "
                        f"o que ninguém está olhando.",
                location=rel, risk="RISK-DEP-001",
                remediation=f"Remover a versão da ficha; declarar apenas pin_source.")
            break


def check_clausula_release(rel: str, suite: dict, findings: hl.Findings) -> None:
    """Cláusula 2 — release ancorável, ou um gap aberto dizendo que ainda não."""
    nome = suite["nome"]
    release = suite["release"]
    gaps_da_clausula = [g for g in suite.get("gaps") or []
                        if g["clause"] == "release-com-manifesto"]

    if not release["anchored"]:
        if not gaps_da_clausula:
            findings.add(
                key=f"SUITE-{nome}-RELEASE-SEM-GAP", origin="suite_contract", severity="high",
                summary=f"{nome}: release.anchored é false e nenhum gap cobre a cláusula "
                        f"release-com-manifesto. 'Ainda não' declarado é dívida com data; 'ainda "
                        f"não' calado é a lacuna que ninguém volta a olhar.",
                location=rel, risk="RISK-WEBQA-001",
                remediation="Declarar um gap com clause: release-com-manifesto e due, ou ancorar "
                            "a release.")
        return

    caminho = release.get("manifest_path")
    if caminho and not hl.rel_exists(caminho):
        findings.add(
            key=f"SUITE-{nome}-RELEASE-MANIFESTO-AUSENTE", origin="suite_contract",
            severity="critical",
            summary=f"{nome}: declara release ancorada em '{caminho}', que não existe. Âncora que "
                    f"não encontra o que ancora está quebrada, não satisfeita (ADR-006).",
            location=rel, risk="RISK-WEBQA-001")
        return

    # O digest, que é a âncora de verdade. A cláusula 2 sempre disse "`manifest_sha` que não bate
    # ⇒ achado" e nada conferia: `manifest_path` existir prova que há um arquivo, não que é AQUELE
    # arquivo. Sem esta linha, mover a tag da régua e trazer o manifesto novo passaria calado —
    # exatamente o evento que "tag é ponteiro móvel, digest não" existe para tornar visível.
    declarado = release.get("manifest_sha")
    if caminho and declarado:
        import hashlib

        medido = hashlib.sha256((hl.REPO / caminho).read_bytes()).hexdigest()
        if medido != declarado:
            findings.add(
                key=f"SUITE-{nome}-RELEASE-DIGEST-DIVERGENTE", origin="suite_contract",
                severity="critical",
                summary=f"{nome}: manifest_sha declara {declarado[:12]}… e {caminho} tem "
                        f"{medido[:12]}…. Ou o manifesto da régua mudou sob os pés, ou o pin foi "
                        f"atualizado sem que ninguém olhasse o que mudou — e as duas leituras "
                        f"pedem reações diferentes.",
                location=rel, risk="RISK-WEBQA-001",
                remediation="Conferir o que mudou no manifesto da régua e, se a mudança for "
                            "aceita, atualizar manifest_sha no mesmo PR que a aceita.")


def check_clausula_envelope(rel: str, suite: dict, findings: hl.Findings,
                            errors: hl.Errors) -> None:
    """Cláusula 3 — o envelope declarado sabe representar os três estados."""
    nome = suite["nome"]
    laudo = suite.get("laudo")
    if not laudo:
        return  # status: planned — o schema já dispensa, e cobrar aqui seria cobrar duas vezes

    schema_rel = laudo["schema"]
    if not hl.rel_exists(schema_rel):
        findings.add(
            key=f"SUITE-{nome}-ENVELOPE-INEXISTENTE", origin="suite_contract", severity="critical",
            summary=f"{nome}: laudo.schema '{schema_rel}' não existe.",
            location=rel, risk="RISK-WEBQA-001")
        return

    try:
        schema = hl.read_json(schema_rel)
    except HarnessError as exc:
        errors.err(str(exc))
        return

    estados = (((schema.get("properties") or {}).get("verdict") or {}).get("enum")) or []
    faltando = [e for e in ("conforme", "nao_conforme", "inconclusivo") if e not in estados]
    if faltando:
        findings.add(
            key=f"SUITE-{nome}-ENVELOPE-SEM-ESTADO", origin="suite_contract", severity="critical",
            summary=f"{nome}: o envelope {schema_rel} não representa {', '.join(faltando)}. Sem os "
                    f"três estados, 'não consegui medir' sai com a mesma cor de 'medi e está "
                    f"bom' — e a cor mais barata vence por hábito.",
            location=schema_rel, risk="RISK-WEBQA-001",
            remediation="Acrescentar o enum verdict com conforme, nao_conforme e inconclusivo.")


def check_clausula_fingerprint(rel: str, suite: dict, findings: hl.Findings) -> None:
    """Cláusula 4 — os cinco campos que dizem com o que um laudo é comparável."""
    nome = suite["nome"]
    declarados = suite.get("fingerprint_fields") or list(FINGERPRINT_CANONICO)
    faltando = [c for c in FINGERPRINT_CANONICO if c not in declarados]
    if faltando:
        findings.add(
            key=f"SUITE-{nome}-FINGERPRINT-INCOMPLETO", origin="suite_contract", severity="high",
            summary=f"{nome}: fingerprint sem {', '.join(faltando)}. Faltando um campo, dois "
                    f"laudos parecem comparáveis sem serem — e a diferença entre eles deixa de "
                    f"significar o que se pensa que significa.",
            location=rel, risk="RISK-WEBQA-001",
            remediation=f"Declarar fingerprint_fields com {list(FINGERPRINT_CANONICO)}.")


def check_higiene_e_gaps(rel: str, suite: dict, findings: hl.Findings, hoje: date) -> None:
    """Higiene da ficha e vencimento dos gaps — o que impede a dívida de envelhecer calada."""
    nome = suite["nome"]

    esperado = Path(rel).stem
    if nome != esperado:
        findings.add(
            key=f"SUITE-{nome}-NOME-DIVERGENTE", origin="suite_contract", severity="high",
            summary=f"ficha {rel} declara nome '{nome}'. Nome interno diferente do arquivo faz "
                    f"duas fichas poderem descrever a mesma régua sem que nada acuse.",
            location=rel, risk="RISK-META-001")

    for gap in suite.get("gaps") or []:
        try:
            vence = date.fromisoformat(gap["due"])
        except ValueError:
            findings.add(
                key=f"SUITE-{nome}-GAP-DATA-INVALIDA-{gap['id']}", origin="suite_contract",
                severity="high", summary=f"{nome}/{gap['id']}: due '{gap['due']}' não é data ISO.",
                location=rel)
            continue
        if vence < hoje:
            findings.add(
                key=f"SUITE-{nome}-GAP-VENCIDO-{gap['id']}", origin="suite_contract",
                severity="high",
                summary=f"{nome}: o gap {gap['id']} ({gap['clause']}) venceu em {gap['due']}. "
                        f"Vencido, ele deixa de ser dívida declarada e vira dívida esquecida — o "
                        f"achado força RE-DECISÃO: ou a régua cumpriu a cláusula, ou alguém "
                        f"renegocia o prazo com nome e data.",
                location=rel, risk=gap.get("risk"),
                remediation="Fechar o gap, ou mover `due` numa change-proposal — nunca apagá-lo.")


def check_modos(rel: str, suite: dict, findings: hl.Findings, harness: dict) -> None:
    """Os modos da ficha existem na harness, e o gate de cada um não afrouxa o declarado lá."""
    nome = suite["nome"]
    modos_harness = harness.get("execution_modes") or {}
    for modo in suite.get("modes") or []:
        decl = modos_harness.get(modo["nome"])
        if decl is None:
            findings.add(
                key=f"SUITE-{nome}-MODO-DESCONHECIDO-{modo['nome']}", origin="suite_contract",
                severity="high",
                summary=f"{nome}: oferece o modo '{modo['nome']}', que harness.yaml não enumera — "
                        f"modo sem natureza de risco declarada é chamada ambígua roteada como "
                        f"operação de baixo risco.",
                location=rel, risk="RISK-SEC-001")
            continue
        # A harness diz que o agente NÃO pode disparar; a ficha não pode dizer que dispensa gate.
        if decl.get("agent_may_trigger") is False and not modo["requires_gate"]:
            findings.add(
                key=f"SUITE-{nome}-MODO-SEM-GATE-{modo['nome']}", origin="suite_contract",
                severity="critical",
                summary=f"{nome}: o modo '{modo['nome']}' é human_only em harness.yaml, e a ficha "
                        f"declara requires_gate: false. É a autorização se afrouxando pela porta "
                        f"lateral — a ficha não pode conceder o que a harness recusa.",
                location=rel, risk="RISK-SEC-001",
                remediation=f"Declarar requires_gate: true para o modo {modo['nome']}.")


# --------------------------------------------------------------------------------------
# O contrato e a autoprova (cláusula 5)
# --------------------------------------------------------------------------------------

def check_contrato(versao: str, findings: hl.Findings, errors: hl.Errors) -> dict | None:
    """O manifesto fecha a versão: cláusulas completas e digests batendo."""
    rel = manifest_path(versao)
    if not hl.rel_exists(rel):
        errors.err(f"contract_version '{versao}' não tem manifesto em {rel}. Um contrato de "
                   f"rastreabilidade não-rastreável não pode julgar rastreabilidade alheia.")
        return None
    try:
        doc = hl.read_json(rel)
    except HarnessError as exc:
        errors.err(str(exc))
        return None

    problemas = hl.schema_errors(rel, "suite-contract-manifest.schema.json", doc)
    if problemas:
        for p in problemas:
            errors.err(p)
        return None

    contrato = doc["contract"]
    if contrato["version"] != versao:
        findings.add(
            key=f"CONTRATO-{versao}-VERSAO-DIVERGENTE", origin="suite_contract", severity="critical",
            summary=f"o manifesto em {rel} declara version '{contrato['version']}'. Três formas de "
                    f"dizer a mesma coisa — diretório, manifesto e enum da ficha — e uma delas "
                    f"discorda.",
            location=rel, risk="RISK-META-001")

    # Digests: um arquivo do contrato que mudou sem release nova.
    for item in contrato["files"]:
        caminho = item["path"]
        alvo = hl.REPO / caminho
        if not alvo.is_file():
            findings.add(
                key=f"CONTRATO-{versao}-ARQUIVO-AUSENTE", origin="suite_contract",
                severity="critical",
                summary=f"o manifesto lista '{caminho}', que não existe. A v1 promete um conteúdo "
                        f"que não está aqui.",
                location=rel, risk="RISK-META-001")
            continue
        real = hl.sha256_file(alvo)
        if real != item["sha256"]:
            findings.add(
                key=f"CONTRATO-{versao}-DIGEST-DIVERGENTE", origin="suite_contract",
                severity="critical",
                summary=f"'{caminho}' mudou sem que a versão do contrato mudasse "
                        f"(esperado {item['sha256'][:12]}…, real {real[:12]}…). A âncora é o "
                        f"digest justamente para que isto seja detectável.",
                location=caminho, risk="RISK-META-001",
                remediation="Reemitir o manifesto numa versão nova do contrato, ou reverter a "
                            "edição — nunca atualizar o digest em silêncio.")

    # Partição nos dois sentidos: arquivo do contrato fora do manifesto pode mudar sem acusar.
    #
    # O próprio manifesto é a única exceção, e é a mesma que ci/mold_release.py enfrentou ao
    # declarar o commit PAI: um arquivo não pode conter o hash do arquivo que o contém. O que o
    # protege não é um digest interno — é a release do molde, cujo artifact_digest cobre a árvore
    # inteira, e o fato de qualquer edição dele reprovar aqui por outro caminho (cláusula faltando,
    # versão divergente, digest de outro arquivo que não bate).
    listados = {i["path"] for i in contrato["files"]} | {rel}
    for caminho in sorted((hl.REPO / contract_dir(versao)).rglob("*")):
        if caminho.is_file() and hl.rel(caminho) not in listados:
            findings.add(
                key=f"CONTRATO-{versao}-NAO-LISTADO", origin="suite_contract", severity="high",
                summary=f"'{hl.rel(caminho)}' está no contrato mas fora do manifesto — pode mudar "
                        f"sem que digest algum acuse.",
                location=hl.rel(caminho), risk="RISK-META-001")

    # Cláusula 5, primeiro dever: nenhuma cláusula sem mutação canônica, e o fiscal REPROVA A SI
    # MESMO se faltar. Vem antes de julgar suite alguma, de propósito.
    declaradas = {c["id"] for c in contrato["clauses"]}
    for esperada in CLAUSULAS:
        if esperada not in declaradas:
            findings.add(
                key=f"FISCAL-SEM-AUTOPROVA-{esperada}", origin="suite_contract", severity="critical",
                summary=f"a cláusula '{esperada}' não está no manifesto da {versao}. Um fiscal que "
                        f"não sabe como uma cláusula seria negada não sabe se ela está "
                        f"funcionando — e este achado é sobre o fiscal, não sobre régua alguma.",
                location=rel, risk="RISK-CONF-001")

    # O `op` declarado tem que existir no motor real, não na memória de quem escreveu o schema.
    motor = _motor()
    for clausula in contrato["clauses"]:
        op = clausula["canonical_mutation"]["op"]
        if op not in motor.OPERADORES:
            findings.add(
                key=f"FISCAL-AUTOPROVA-OP-INEXISTENTE-{clausula['id']}", origin="suite_contract",
                severity="critical",
                summary=f"a cláusula '{clausula['id']}' declara o operador '{op}', que o motor "
                        f"compartilhado não implementa. A autoprova falharia por erro de escrita, "
                        f"e o achado mandaria consertar o lugar errado.",
                location=rel, risk="RISK-CONF-001")

        alvo = clausula["assertion"]
        arquivo, _, simbolo = alvo.partition("::")
        if not hl.rel_exists(arquivo):
            findings.add(
                key=f"FISCAL-AUTOPROVA-FISCAL-AUSENTE-{clausula['id']}", origin="suite_contract",
                severity="critical",
                summary=f"a cláusula '{clausula['id']}' aponta para {alvo}, e {arquivo} não "
                        f"existe. Cláusula cujo fiscal não existe é prosa.",
                location=rel, risk="RISK-CONF-001")
        elif simbolo and simbolo not in hl.defined_names(hl.REPO / arquivo):
            findings.add(
                key=f"FISCAL-AUTOPROVA-SIMBOLO-AUSENTE-{clausula['id']}", origin="suite_contract",
                severity="critical",
                summary=f"a cláusula '{clausula['id']}' aponta para {alvo}, e o símbolo "
                        f"'{simbolo}' não existe em {arquivo}.",
                location=rel, risk="RISK-CONF-001")

    return contrato


def provar_autoprova(contrato: dict, findings: hl.Findings, errors: hl.Errors) -> int:
    """Aplica cada mutação canônica numa CÓPIA e exige o achado específico que ela promete.

    Exigir o achado ESPECÍFICO, e não apenas 'algum vermelho', é o que impede a autoprova de ser
    satisfeita por um erro não relacionado. É a lição que `harness/policies/prova-de-mutacao.md`
    tirou do próprio fiscal: quando a mutação e a asserção compartilham a mesma string, o acordo
    entre elas pode não ser sobre o mundo.
    """
    import importlib
    import os

    motor = _motor()
    origem = hl.REPO
    provadas = 0

    with tempfile.TemporaryDirectory(prefix="autoprova-") as tmp:
        copia = Path(tmp) / "repo"
        shutil.copytree(origem, copia, ignore=shutil.ignore_patterns(*motor.SKIP))
        anterior = os.environ.get("HARNESS_REPO_ROOT")
        os.environ["HARNESS_REPO_ROOT"] = str(copia)
        try:
            importlib.reload(hl)
            for clausula in contrato["clauses"]:
                mut = dict(clausula["canonical_mutation"])
                espera = mut.pop("espera_achado")
                antes = motor.aplicar(mut, copia)
                if not antes:
                    findings.add(
                        key=f"FISCAL-AUTOPROVA-ALVO-INEXISTENTE-{clausula['id']}",
                        origin="suite_contract", severity="critical",
                        summary=f"a mutação da cláusula '{clausula['id']}' não encontrou "
                                f"'{mut['alvo']}' — trava que não acha o que vigia está quebrada, "
                                f"não satisfeita (ADR-006).",
                        risk="RISK-CONF-001")
                    continue
                try:
                    f2, e2 = hl.Findings(), hl.Errors()
                    _auditar(f2, e2, autoprova=False)
                    mordeu = (any(espera in i["id"] for i in f2.blocking())
                              or any(espera in msg for msg in e2.items))
                finally:
                    motor.restaurar(antes, copia)

                if mordeu:
                    provadas += 1
                else:
                    findings.add(
                        key=f"FISCAL-NAO-MORDE-{clausula['id']}", origin="suite_contract",
                        severity="critical",
                        summary=f"a mutação canônica de '{clausula['id']}' ({mut['op']} em "
                                f"{mut['alvo']}) foi aplicada e nenhum achado contendo "
                                f"'{espera}' apareceu — a cláusula é decorativa.",
                        risk="RISK-CONF-001")
        except Exception as exc:  # noqa: BLE001 - não conseguir provar é exit 2, nunca 0
            errors.err(f"autoprova não pôde rodar: {exc}")
        finally:
            if anterior is None:
                os.environ.pop("HARNESS_REPO_ROOT", None)
            else:
                os.environ["HARNESS_REPO_ROOT"] = anterior
            importlib.reload(hl)

    return provadas


# --------------------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------------------

def _auditar(findings: hl.Findings, errors: hl.Errors, autoprova: bool = True) -> None:
    """Um passo de auditoria completo. Reentrante de propósito: a autoprova o chama de novo."""
    fichas = carregar_fichas(errors)
    if errors:
        return

    try:
        harness = hl.read_yaml("harness/harness.yaml") or {}
    except HarnessError as exc:
        errors.err(str(exc))
        return

    hoje = date.today()
    versoes = set()

    for rel, doc in sorted(fichas.items()):
        suite = doc["suite"]
        versoes.add(suite["contract_version"])
        check_clausula_pin(rel, suite, findings)
        check_clausula_release(rel, suite, findings)
        check_clausula_envelope(rel, suite, findings, errors)
        check_clausula_fingerprint(rel, suite, findings)
        check_higiene_e_gaps(rel, suite, findings, hoje)
        check_modos(rel, suite, findings, harness)

    # A denylist efetiva CONTÉM todo env_prefix declarado — a prova cruzada com o CP-025.
    prefixos = sorted({d["suite"]["env_prefix"] for d in fichas.values()})
    try:
        import env_guard

        efetivos = env_guard.prefixos_efetivos(harness.get("env_hygiene") or {})
    except Exception as exc:  # noqa: BLE001
        errors.err(f"não foi possível derivar a denylist efetiva: {exc}")
        efetivos = []
    for p in prefixos:
        if p not in efetivos:
            findings.add(
                key=f"SUITE-ENV-PREFIX-NAO-COBERTO-{p.rstrip('_')}", origin="suite_contract",
                severity="critical",
                summary=f"o prefixo '{p}*' está declarado numa ficha e NÃO está na denylist "
                        f"efetiva. É a trava do CP-025 com um buraco do tamanho de uma régua: os "
                        f"gates da suíte são fail-closed por variável de ambiente, e um agente "
                        f"que consegue defini-las se autoriza a sondar.",
                risk="RISK-SEC-001",
                remediation="Derivar env_denylist_prefix do registro em ci/env_guard.py.")

    for versao in sorted(versoes):
        contrato = check_contrato(versao, findings, errors)
        if contrato and autoprova:
            provar_autoprova(contrato, findings, errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fiscal genérico do Contrato de Régua.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--skip-autoprova", action="store_true",
                        help="pula a cláusula 5 (copia o repositório); o CI NÃO usa esta flag")
    args = parser.parse_args(argv)

    findings, errors = hl.Findings(), hl.Errors()
    try:
        _auditar(findings, errors, autoprova=not args.skip_autoprova)
    except HarnessError as exc:
        errors.err(str(exc))
    except Exception as exc:  # noqa: BLE001 - fiscal cego é exit 2, nunca exit 0
        errors.err(f"o fiscal não conseguiu fiscalizar: {exc}")

    hl.print_summary("contrato de régua", findings, errors, args.quiet)
    if errors:
        return 2

    laudo = hl.build_report(
        auditor="ci/audit_suites.py", auditor_version=AUDITOR_VERSION, findings=findings,
        stages_covered=["STAGE-QA-CONFIG", "STAGE-CI-HARNESS"],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        hl.emit_report(REPORT_PATH, laudo)
    except HarnessError as exc:
        print(f"✗ contrato de régua: {exc}", file=sys.stderr)
        return 2

    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
