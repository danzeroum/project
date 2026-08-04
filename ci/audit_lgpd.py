#!/usr/bin/env python3
"""Fiscal determinístico de LGPD — roda sempre, sobre o projeto inteiro.

A fronteira desta ferramenta é explícita e não deve ser borrada:

    O fiscal determinístico NÃO julga legalidade. Ele garante que o julgamento existe,
    é do tipo certo, e cobre exatamente este estado do repositório.

Adequação da base legal à finalidade, proporcionalidade do prazo de retenção, se um DTO
devolve além do necessário, se um campo não sinalizado pela heurística é ainda assim dado
pessoal — tudo isso é juízo, e fica com a skill /revisao-lgpd (agente harness/agents/privacy).
O que mora aqui é o que a máquina consegue afirmar sem opinar: o inventário é coerente, a
retenção tem prazo, a varredura não encontra dado pessoal fora do registro, e o parecer/RIPD
não está vencido.

Frescor é por FINGERPRINT DE CONTEÚDO, nunca por data ou `git log`: actions/checkout@v4 clona
com fetch-depth 1, então histórico não existe no CI — e data tornaria o resultado irreprodutível.
É o mesmo idioma do sensitive_paths_hash do ADR-003.

Uso:  python ci/audit_lgpd.py [--quiet] [--json] [--print-fingerprint] [--print-surface]
Saída: 0 conforme · 1 divergências (laudo escrito) · 2 o fiscal não conseguiu fiscalizar.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import harness_lib as hl
from harness_lib import Errors, Findings, HarnessError

AUDITOR_VERSION = "1.0"
REPORT_PATH = "harness/reports/lgpd-audit.json"

INVENTORY = "governance/data-inventory.yaml"
REVIEW = "governance/privacy-review.yaml"
STAGES = "harness/stages.yaml"
PROJECT_YAML = "project.yaml"

# Os arquivos que DECLARAM o tratamento não são tratamento. Varrê-los faria o inventário
# acusar a si mesmo de shadow processing.
SCAN_SELF_EXCLUDE = {INVENTORY, REVIEW}

# Prefixo da evidência da harness: é o que o L9 vigia nos uploads de artifact.
EVIDENCE_PREFIX = "harness/"

# --------------------------------------------------------------------------------------
# Léxicos — a régua desta verificação.
#
# Constantes de código, deliberadamente NÃO um YAML de configuração: uma lista curada que o
# fiscalizado edita pelo caminho de menor resistência para de procurar o que dava trabalho, e
# o laudo continua dizendo "nenhum achado". É o mesmo argumento do ADR-001 aplicado aqui.
# Suprimir é DECLARAR em data-inventory.yaml:scan.exclusions com justificativa — nunca apagar
# um termo daqui. E ci/ é protected_path: mudar esta lista exige revisão humana.
# --------------------------------------------------------------------------------------

TOKENS_PESSOAIS = frozenset({
    # Documentos e identificadores civis (Brasil)
    "cpf", "cnpj", "rg", "cnh", "passaporte", "titulo", "eleitor", "pis", "nis", "nit",
    # Contato
    "email", "mail", "telefone", "celular", "phone", "whatsapp",
    # Endereço
    "endereco", "logradouro", "bairro", "cep", "zipcode", "zip", "address",
    # Identidade pessoal
    "nome", "sobrenome", "name", "surname", "fullname", "nascimento", "birthdate", "birth",
    "idade", "age", "genero", "gender",
    # Rastreio e localização
    "geolocalizacao", "geolocation", "latitude", "longitude", "ip",
    # Financeiro
    "cartao", "card", "iban", "agencia", "conta",
})

TOKENS_SENSIVEIS = frozenset({
    # Art. 5º, II — origem racial ou étnica, convicção religiosa, opinião política, filiação a
    # sindicato ou a organização religiosa/filosófica/política, dado referente à saúde ou à
    # vida sexual, dado genético ou biométrico.
    "saude", "health", "diagnostico", "prontuario", "cid", "medicamento",
    "biometria", "biometric", "digital", "facial", "genetico", "genomic", "dna",
    "raca", "etnia", "ethnicity", "religiao", "religion", "conviccao",
    "politica", "sindical", "sindicato", "union",
    "orientacao", "sexual", "sexualidade",
})

# Tokens ambíguos: só contam quando acompanhados de um qualificador na MESMA identificação.
# 'digital' sozinho é 'transformação digital'; 'digital' com 'impressao' é biometria.
AMBIGUOUS = {
    "digital": {"impressao", "biometria"},
    "politica": {"opiniao", "filiacao"},
    "sexual": {"orientacao", "vida"},
    "conta": {"bancaria", "corrente"},
    "ip": {"address", "endereco", "origem"},
    "nome": {"completo", "titular", "cliente", "usuario", "pessoa"},
    "name": {"full", "first", "last", "holder", "customer"},
}

RIPD_SECTIONS = [
    "EXECUTIVE SUMMARY", "INVENTÁRIO DE DADOS", "BASES LEGAIS", "MEDIDAS DE SEGURANÇA",
    "RETENÇÃO E EXPURGO", "DIREITOS DOS TITULARES", "RISCOS RESIDUAIS", "APROVAÇÃO",
]
PARECER_SECTIONS = [
    "PAPEL DO SISTEMA", "DADOS INCIDENTAIS", "CONTROLES PROPORCIONAIS", "CONTROLES DESCARTADOS",
]

PBD_DESIGN = "Privacidade no Design"
PBD_PROATIVO = "Proativo e Preventivo"
PBD_DEFAULT = "Privacy by Default"


# --------------------------------------------------------------------------------------
# Superfície de varredura — declarada em stages.yaml, nunca hard-coded aqui
# --------------------------------------------------------------------------------------

def scan_surface(stages_doc: dict) -> list[Path]:
    globs = [
        artifact
        for stage in (stages_doc or {}).get("stages", [])
        if stage.get("privacy_lens", {}).get("scan")
        for artifact in stage.get("artifacts", [])
    ]
    seen: dict[str, Path] = {}
    for g in globs:
        for p in hl.resolve_glob(g):
            targets = [p] if p.is_file() else [c for c in p.rglob("*") if c.is_file()]
            for t in targets:
                r = hl.rel(t)
                if hl.is_excluded(r) or r in SCAN_SELF_EXCLUDE:
                    continue
                if t.suffix in {".py", ".yaml", ".yml", ".json"}:
                    seen[r] = t
    return [seen[k] for k in sorted(seen)]


# --------------------------------------------------------------------------------------
# Varredura de dado pessoal (D5)
# --------------------------------------------------------------------------------------

def _classify(tokens: list[str]) -> str | None:
    """Retorna 'sensivel', 'pessoal' ou None. Casamento por token exato, jamais substring."""
    tset = set(tokens)
    for group, verdict in ((TOKENS_SENSIVEIS, "sensivel"), (TOKENS_PESSOAIS, "pessoal")):
        for tok in tset & group:
            required = AMBIGUOUS.get(tok)
            if required is None or (tset & required):
                return verdict
    return None


def _identifiers_py(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(hl.parse_module(path)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, ast.Assign):
            out.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.Dict):
            out.update(k.value for k in node.keys
                       if isinstance(k, ast.Constant) and isinstance(k.value, str))
    return out


def _identifiers_mapping(doc: object) -> set[str]:
    out: set[str] = set()
    if isinstance(doc, dict):
        for k, v in doc.items():
            if isinstance(k, str):
                out.add(k)
            out |= _identifiers_mapping(v)
    elif isinstance(doc, list):
        for item in doc:
            out |= _identifiers_mapping(item)
    return out


def _inventoried_tokens(inventory: dict) -> set[str]:
    known: set[str] = set()
    for f in (inventory or {}).get("fields", []):
        for name in [f.get("name", "")] + list(f.get("aliases", [])):
            known.update(hl.tokenize_identifier(name))
    return known


def scan_personal_data(surface: list[Path], inventory: dict,
                       findings: Findings, errors: Errors) -> list[Path]:
    """Identificador com forma de dado pessoal fora do inventário é tratamento-sombra.

    Retorna os arquivos com achado — eles entram no fingerprint do escopo, porque introduzir
    PII num arquivo é exatamente o evento que precisa reabrir o julgamento.
    """
    known = _inventoried_tokens(inventory)
    exclusions = (inventory or {}).get("scan", {}).get("exclusions", [])
    used_exclusions: set[int] = set()
    hit_files: list[Path] = []

    for path in surface:
        r = hl.rel(path)
        try:
            if path.suffix == ".py":
                identifiers = _identifiers_py(path)
            elif path.suffix in {".yaml", ".yml"}:
                identifiers = _identifiers_mapping(hl.read_yaml(r))
            else:
                identifiers = _identifiers_mapping(hl.read_json(r))
        except HarnessError as exc:
            errors.err(str(exc))
            continue

        flagged = False
        for ident in sorted(identifiers):
            tokens = hl.tokenize_identifier(ident)
            verdict = _classify(tokens)
            if not verdict:
                continue
            if known and set(tokens) <= known:
                continue  # já inventariado por nome ou alias

            excused = False
            for i, ex in enumerate(exclusions):
                if ex["token"] in tokens and any(
                    hl.rel(m) == r for m in hl.resolve_glob(ex["path_glob"])
                ):
                    used_exclusions.add(i)
                    excused = True
                    break
            if excused:
                continue

            flagged = True
            findings.add(
                key=f"SHADOW-{r}-{ident}", origin="lgpd_scan",
                severity="high" if verdict == "sensivel" else "medium",
                risk="RISK-PRIV-001", location=f"{r} :: {ident}",
                lgpd_article="Art. 37", pbd_principle=PBD_DESIGN,
                summary=f"'{ident}' tem forma de dado {verdict} e não consta em {INVENTORY} — "
                        f"tratamento sem registro de operações.",
                remediation=f"Inventariar o campo em {INVENTORY} (finalidade, base legal, retenção, "
                            f"componente dono) ou, se não for dado pessoal, declarar a exclusão em "
                            f"scan.exclusions com justificativa.",
            )
        if flagged:
            hit_files.append(path)

    for i, ex in enumerate(exclusions):
        if i not in used_exclusions:
            findings.add(
                key=f"EXCLUSION-STALE-{ex['token']}-{i}", origin="lgpd_inventory", severity="low",
                risk="RISK-PRIV-001", location=INVENTORY,
                lgpd_article="Art. 37", pbd_principle=PBD_PROATIVO,
                summary=f"Exclusão morta: '{ex['token']}' em '{ex['path_glob']}' não suprime "
                        f"achado algum — isenção que não protege nada só serve para parecer limpo.",
            )
    return hit_files


# --------------------------------------------------------------------------------------
# Invariantes do inventário (o que o schema não alcança)
# --------------------------------------------------------------------------------------

def check_inventory_invariants(inventory: dict, findings: Findings) -> None:
    purposes = {p["id"] for p in (inventory or {}).get("purposes", [])}
    fields = (inventory or {}).get("fields", [])

    for f in fields:
        fid = f.get("id", "?")
        if f.get("purpose") not in purposes:
            findings.add(
                key=f"{fid}-PURPOSE", origin="lgpd_inventory", severity="high",
                risk="RISK-PRIV-001", location=INVENTORY,
                lgpd_article="Art. 6", pbd_principle=PBD_DESIGN,
                summary=f"{fid} aponta para a finalidade {f.get('purpose')}, que não existe — "
                        f"dado sem finalidade declarada viola a finalidade específica.",
            )
        for loc in f.get("locations", []):
            if not hl.resolve_glob(loc):
                findings.add(
                    key=f"{fid}-LOCATION-{loc}", origin="lgpd_inventory", severity="medium",
                    risk="RISK-PRIV-001", location=INVENTORY,
                    lgpd_article="Art. 37", pbd_principle=PBD_PROATIVO,
                    summary=f"{fid} declara viver em '{loc}', que não existe no repositório.",
                )

    if fields:
        rights = (inventory or {}).get("subject_rights", {})
        for right, value in rights.items():
            if not value:
                findings.add(
                    key=f"RIGHT-{right}", origin="lgpd_inventory", severity="high",
                    risk="RISK-PRIV-001", location=INVENTORY,
                    lgpd_article="Art. 18", pbd_principle="Centrado no Usuário",
                    summary=f"O direito de {right} não tem endpoint declarado. Não existe direito "
                            f"do titular sem endpoint: sem onde exercer, o direito não existe no sistema.",
                )


def check_evidence_retention(project_doc: dict, findings: Findings, errors: Errors) -> None:
    """L9 — a retenção declarada precisa alcançar a cópia da evidência que sobrevive ao runner.

    L8 já cobra a igualdade entre project.yaml e tests/qa/campanha.yaml, mas nenhum dos dois
    alcança o artifact do CI: sem `retention-days` no upload, a retenção real vem de uma setting
    do GitHub — editável fora do repositório e invisível a qualquer fiscal. É a mesma mentira de
    retenção que o L8 fecha, uma camada acima.

    Compara com o valor DECLARADO em project.yaml, não com um literal: subir a retenção exige
    mudar os dois lugares, e o conjunto continua coerente.
    """
    declared = (project_doc or {}).get("governance", {}).get("evidence_retention_days")
    if declared is None:
        return
    wf_dir = hl.REPO / ".github" / "workflows"
    if not wf_dir.exists():
        return
    for wf in sorted(wf_dir.glob("*.yml")):
        rel = hl.rel(wf)
        try:
            doc = hl.read_yaml(rel) or {}
        except HarnessError as exc:
            errors.err(str(exc))
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                if not isinstance(step, dict) or "upload-artifact" not in str(step.get("uses", "")):
                    continue
                with_ = step.get("with") or {}
                path = str(with_.get("path", ""))
                if not path.startswith(EVIDENCE_PREFIX):
                    continue
                got = with_.get("retention-days")
                where = f"{rel} :: {job_name} :: {with_.get('name', '?')}"
                if got is None:
                    findings.add(
                        key=f"ARTIFACT-RETENTION-{rel}-{with_.get('name', job_name)}",
                        origin="lgpd_retention", severity="medium",
                        risk="RISK-PRIV-001", location=where,
                        lgpd_article="Art. 15", pbd_principle=PBD_DEFAULT,
                        summary=f"O upload de '{path}' não declara retention-days: a retenção "
                                f"efetiva da evidência vem de uma setting do GitHub, fora do "
                                f"repositório e fora do alcance de qualquer fiscal.",
                        remediation=f"Declarar retention-days: {declared}, igual a "
                                    f"project.yaml:governance.evidence_retention_days.",
                    )
                elif int(got) != int(declared):
                    findings.add(
                        key=f"ARTIFACT-RETENTION-MISMATCH-{rel}-{with_.get('name', job_name)}",
                        origin="lgpd_retention", severity="high",
                        risk="RISK-PRIV-001", location=where,
                        lgpd_article="Art. 16", pbd_principle=PBD_DEFAULT,
                        summary=f"O upload de '{path}' retém por {got} dias, mas o projeto declara "
                                f"{declared} — duas retenções diferentes para a mesma evidência.",
                        remediation="Alinhar os dois, ou mudar a retenção declarada explicitamente.",
                    )


def check_declaration_consistency(inventory: dict, project_doc: dict,
                                  hit_files: list[Path], findings: Findings) -> None:
    """D1/D7: o papel declarado em project.yaml e o inventário contam a mesma história."""
    role = (inventory or {}).get("controller", {}).get("role")
    declared = (project_doc or {}).get("classification", {}).get("lgpd_relevance")
    if role != declared:
        findings.add(
            key="ROLE-MISMATCH", origin="lgpd_declaration", severity="high",
            risk="RISK-PRIV-001", location=PROJECT_YAML,
            lgpd_article="Art. 37", pbd_principle="Transparência",
            summary=f"project.yaml declara lgpd_relevance '{declared}' e {INVENTORY} declara "
                    f"controller.role '{role}' — a mesma verdade escrita em dois lugares já divergiu.",
            remediation="Alinhar os dois; o papel é derivado do que o sistema de fato trata.",
        )

    fields = (inventory or {}).get("fields", [])
    if fields and role in ("none", "incidental"):
        findings.add(
            key="ROLE-UNDERSTATED", origin="lgpd_declaration", severity="high",
            risk="RISK-PRIV-001", location=INVENTORY,
            lgpd_article="Art. 5", pbd_principle="Transparência",
            summary=f"O inventário lista {len(fields)} campo(s) de dado pessoal, mas o papel "
                    f"declarado é '{role}' — quem trata dado pessoal é controlador ou operador.",
        )
    if not fields and role in ("controller", "operator", "controller_and_operator") and not hit_files:
        findings.add(
            key="ROLE-OVERSTATED", origin="lgpd_declaration", severity="medium",
            risk="RISK-PRIV-001", location=INVENTORY,
            lgpd_article="Art. 37", pbd_principle="Transparência",
            summary=f"O papel declarado é '{role}', mas o inventário está vazio — registro das "
                    f"operações ausente para um sistema que se declara tratador.",
        )


# --------------------------------------------------------------------------------------
# Frescor do julgamento (D6)
# --------------------------------------------------------------------------------------

def scope_fingerprint(project_doc: dict, hit_files: list[Path]) -> str:
    """Escopo PROPORCIONAL: só o que pode mudar o veredito determinístico.

    Cobrir src/** faria qualquer refactor de precificação vencer o parecer e derrubar o CI.
    Refatorar preço não reabre o julgamento; introduzir um campo de CPF reabre.
    """
    parts: list[tuple[str, str]] = []
    if hl.rel_exists(INVENTORY):
        parts.append((INVENTORY, hl.sha256_file(hl.REPO / INVENTORY)))
    classification = (project_doc or {}).get("classification", {})
    business = (project_doc or {}).get("business", {})
    project = (project_doc or {}).get("project", {})
    parts.append((f"{PROJECT_YAML}#classification", hl.sha256_canonical({
        "classification": classification,
        "criticality": business.get("criticality"),
        "lifecycle": project.get("lifecycle"),
    })))
    if hl.rel_exists("tests/qa/config.yaml"):
        parts.append(("tests/qa/config.yaml", hl.sha256_file(hl.REPO / "tests/qa/config.yaml")))
    for p in hit_files:
        parts.append((hl.rel(p), hl.sha256_file(p)))
    return hl.fingerprint(parts)


def _sections_present(text: str, sections: list[str]) -> list[str]:
    normalized = hl.tokenize_identifier(text)
    joined = " ".join(normalized)
    missing = []
    for section in sections:
        needle = " ".join(hl.tokenize_identifier(section))
        if needle not in joined:
            missing.append(section)
    return missing


def check_judgment_currency(inventory: dict, review: dict, project_doc: dict,
                            hit_files: list[Path], findings: Findings) -> str:
    """O fiscal não julga; ele exige que o julgamento exista, seja do tipo certo e cubra este estado."""
    current = scope_fingerprint(project_doc, hit_files)
    r = (review or {}).get("review", {})

    fields = (inventory or {}).get("fields", [])
    role = (inventory or {}).get("controller", {}).get("role")
    expected_kind = (
        "ripd_completo"
        if fields or role in ("controller", "operator", "controller_and_operator")
        else "parecer_proporcionalidade"
    )

    if r.get("kind") != expected_kind:
        findings.add(
            key="JUDGMENT-KIND", origin="lgpd_judgment", severity="high",
            risk="RISK-PRIV-002", location=REVIEW,
            lgpd_article="Art. 38", pbd_principle=PBD_PROATIVO,
            summary=f"O julgamento registrado é '{r.get('kind')}', mas o estado do sistema exige "
                    f"'{expected_kind}'.",
            remediation="Rodar /revisao-lgpd (agente privacy) e regravar o documento no tipo certo.",
        )

    doc_rel = r.get("document")
    if not doc_rel or not hl.rel_exists(doc_rel):
        findings.add(
            key="JUDGMENT-DOC-MISSING", origin="lgpd_judgment", severity="high",
            risk="RISK-PRIV-002", location=REVIEW,
            lgpd_article="Art. 38", pbd_principle=PBD_PROATIVO,
            summary=f"O documento do julgamento ('{doc_rel}') não existe.",
        )
    else:
        expected_sections = RIPD_SECTIONS if expected_kind == "ripd_completo" else PARECER_SECTIONS
        missing = _sections_present(hl.read_text(doc_rel), expected_sections)
        if missing:
            findings.add(
                key="JUDGMENT-DOC-INCOMPLETE", origin="lgpd_judgment", severity="high",
                risk="RISK-PRIV-002", location=doc_rel,
                lgpd_article="Art. 38", pbd_principle="Transparência",
                summary=f"{doc_rel} não tem as seções obrigatórias de '{expected_kind}': "
                        f"{', '.join(missing)}.",
            )

    if r.get("scope_fingerprint") != current:
        findings.add(
            key="JUDGMENT-STALE", origin="lgpd_judgment", severity="high",
            risk="RISK-PRIV-002", location=REVIEW,
            lgpd_article="Art. 38", pbd_principle=PBD_PROATIVO,
            summary="O julgamento de privacidade não cobre o estado atual: o escopo mudou desde "
                    "que ele foi produzido, então ele não fala deste sistema.",
            evidence=f"registrado={r.get('scope_fingerprint')} atual={current}",
            remediation="Rodar /revisao-lgpd, atualizar o documento e regravar scope_fingerprint "
                        "com: python ci/audit_lgpd.py --print-fingerprint",
        )

    for issue in r.get("issues", []):
        if issue.get("severity") in ("P0", "P1") and issue.get("status") == "open":
            findings.add(
                key=f"OPEN-{issue.get('id', '?')}", origin="lgpd_judgment",
                severity="critical" if issue["severity"] == "P0" else "high",
                risk=issue.get("risk"), location=issue.get("location"),
                lgpd_article=issue.get("lgpd_article", "Art. 52"),
                pbd_principle=issue.get("pbd_principle", PBD_DEFAULT),
                summary=f"{issue.get('id')} ({issue['severity']}) segue aberto: {issue.get('summary', '')}",
            )
    return current


# --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fiscal determinístico de LGPD.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", default=REPORT_PATH)
    parser.add_argument("--print-fingerprint", action="store_true",
                        help="imprime o scope_fingerprint atual (é como se preenche privacy-review.yaml)")
    parser.add_argument("--print-surface", action="store_true",
                        help="lista os arquivos que a varredura percorre")
    args = parser.parse_args(argv)

    findings, errors = Findings(), Errors()
    try:
        inventory = hl.read_yaml(INVENTORY)
        review = hl.read_yaml(REVIEW)
        project_doc = hl.read_yaml(PROJECT_YAML)
        stages_doc = hl.read_yaml(STAGES)
    except HarnessError as exc:
        print(f"✗ lgpd: {exc}", file=sys.stderr)
        return 2

    surface = scan_surface(stages_doc)
    if args.print_surface:
        for p in surface:
            print(hl.rel(p))
        return 0

    hit_files = scan_personal_data(surface, inventory, findings, errors)
    if args.print_fingerprint:
        print(scope_fingerprint(project_doc, hit_files))
        return 0

    check_inventory_invariants(inventory, findings)
    check_evidence_retention(project_doc, findings, errors)
    check_declaration_consistency(inventory, project_doc, hit_files, findings)
    fingerprint = check_judgment_currency(inventory, review, project_doc, hit_files, findings)

    stages_covered = [
        s["id"] for s in (stages_doc or {}).get("stages", [])
        if s.get("privacy_lens", {}).get("scan")
    ]
    report = hl.build_report(
        auditor="ci/audit_lgpd.py", auditor_version=AUDITOR_VERSION,
        findings=findings, stages_covered=stages_covered,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        scope_fingerprint=fingerprint,
    )
    if errors:
        report["result"] = "error"
    try:
        hl.emit_report(args.report, report)
    except HarnessError as exc:
        print(f"✗ lgpd: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        hl.print_summary("lgpd", findings, errors, quiet=args.quiet)

    if errors:
        return 2
    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
