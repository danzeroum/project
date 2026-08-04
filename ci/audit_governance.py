#!/usr/bin/env python3
"""Fiscal de conformidade — o repositório REAL faz o que as decisões DECLARAM?

Distinto de ci/validate_metadata.py, que pergunta "a forma está certa e os IDs resolvem?".
Este pergunta "o que foi decidido é o que o código faz?". Nunca resolve ID; aquele nunca lê src/.

Executa as asserções tipadas de architecture/adr/index.yaml e verifica que toda etapa de
harness/stages.yaml tem fiscal resolvível e que todo arquivo do repositório pertence a
alguma etapa. Divergência vira achado com o RISK-* que ela instancia, e derruba o CI.

Uso:  python ci/audit_governance.py [--quiet] [--json] [--report PATH]
Saída: 0 conforme · 1 divergências (laudo escrito) · 2 o fiscal não conseguiu fiscalizar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import harness_lib as hl
from harness_lib import Errors, Findings, HarnessError, PointerMissing

AUDITOR_VERSION = "1.0"
REPORT_PATH = "harness/reports/governance-audit.json"

ADR_INDEX = "architecture/adr/index.yaml"
STAGES = "harness/stages.yaml"
RISK_REGISTER = "governance/risk-register.yaml"
HARNESS_YAML = "harness/harness.yaml"
PROJECT_YAML = "project.yaml"
CODEOWNERS = ".github/CODEOWNERS"


# --------------------------------------------------------------------------------------
# Asserções de ADR
# --------------------------------------------------------------------------------------

def _unresolvable(findings: Findings, adr: str, a: dict, what: str) -> None:
    """Alvo que não existe é ACHADO, nunca aprovação.

    Uma asserção cujo glob casa zero arquivos "passa" por vacuidade — e passar por vacuidade
    é exatamente o modo de falha que o ADR-002 descreve, reencarnado dentro do mecanismo
    que deveria impedi-lo.
    """
    findings.add(
        key=f"{a['id']}-UNRESOLVABLE", origin="adr_assertion", severity="high",
        adr=adr, assertion=a["id"], risk=a.get("risk"),
        summary=f"A asserção não resolve alvo algum ({what}) — não pode ser dada como satisfeita.",
        remediation="Corrigir o alvo em architecture/adr/index.yaml ou remover a asserção.",
    )


def _fail(findings: Findings, adr: str, a: dict, summary: str,
          location: str | None = None, evidence: str | None = None) -> None:
    findings.add(
        key=a["id"], origin="adr_assertion", severity=a["severity"],
        adr=adr, assertion=a["id"], risk=a.get("risk"),
        summary=summary, location=location, evidence=evidence,
        remediation=f"Alinhar o repositório à decisão, ou revisar {adr} — decisão que o código "
                    f"não segue precisa ser mudada explicitamente, não ignorada.",
    )


def assert_path_absent(adr, a, findings, errors) -> None:
    for p in a["paths"]:
        if hl.rel_exists(p):
            _fail(findings, adr, a, f"'{p}' existe no consumidor e a decisão diz que nunca deve existir.",
                  location=p)


def assert_path_present(adr, a, findings, errors) -> None:
    for p in a["paths"]:
        if not hl.rel_exists(p):
            _fail(findings, adr, a, f"'{p}' não existe — a decisão declara este fiscal como existente.",
                  location=p)


def _import_assert(adr, a, findings, errors, *, required: bool) -> None:
    modules = [p for p in hl.resolve_glob(a["module_glob"]) if p.suffix == ".py"]
    if not modules:
        _unresolvable(findings, adr, a, f"module_glob '{a['module_glob']}' não casa nenhum .py")
        return
    for mod in modules:
        try:
            syms = hl.module_symbols(mod)
        except HarnessError as exc:
            errors.err(str(exc))
            continue
        for target in a["symbols"]:
            hit = hl.symbol_hits(syms, target)
            if required and not hit:
                _fail(findings, adr, a,
                      f"{hl.rel(mod)} não depende de '{target}', e a decisão exige essa dependência.",
                      location=hl.rel(mod))
            elif not required and hit:
                _fail(findings, adr, a,
                      f"{hl.rel(mod)} depende de '{target}', e a decisão proíbe essa dependência.",
                      location=hl.rel(mod),
                      evidence=f"símbolo alcançado por import ou uso por atributo: {target}")


def assert_import_required(adr, a, findings, errors) -> None:
    _import_assert(adr, a, findings, errors, required=True)


def assert_import_forbidden(adr, a, findings, errors) -> None:
    _import_assert(adr, a, findings, errors, required=False)


def _regex_assert(adr, a, findings, errors, *, want_match: bool) -> None:
    excluded = set()
    for pattern in a.get("exclude", []):
        excluded.update(hl.rel(p) for p in hl.resolve_glob(pattern))
    files = [p for g in a["files"] for p in hl.resolve_glob(g)]
    files = [p for p in files if p.is_file() and hl.rel(p) not in excluded]
    if not files:
        _unresolvable(findings, adr, a, f"files {a['files']} não casa nenhum arquivo")
        return
    flags = re.MULTILINE | (re.DOTALL if a.get("dotall") else 0)
    rx = re.compile(a["pattern"], flags)
    mode = a.get("match", "all")
    hits = {hl.rel(p): bool(rx.search(p.read_text(encoding="utf-8", errors="replace"))) for p in files}

    if want_match:
        offenders = [f for f, ok in hits.items() if not ok]
        if mode == "any" and any(hits.values()):
            return
        for f in offenders:
            _fail(findings, adr, a,
                  f"{f} não contém o padrão que a decisão exige: /{a['pattern']}/", location=f)
    else:
        for f, ok in hits.items():
            if ok:
                _fail(findings, adr, a,
                      f"{f} contém o padrão que a decisão proíbe: /{a['pattern']}/", location=f)


def assert_file_matches(adr, a, findings, errors) -> None:
    _regex_assert(adr, a, findings, errors, want_match=True)


def assert_file_lacks(adr, a, findings, errors) -> None:
    _regex_assert(adr, a, findings, errors, want_match=False)


def assert_schema_lock(adr, a, findings, errors) -> None:
    """Prova que uma trava if/then continua no schema. Texto de ADR não segura schema."""
    if not hl.rel_exists(a["file"]):
        _unresolvable(findings, adr, a, f"schema '{a['file']}' não existe")
        return
    try:
        doc = hl.read_json(a["file"])
    except HarnessError as exc:
        errors.err(str(exc))
        return
    try:
        value = hl.json_pointer(doc, a["pointer"])
    except PointerMissing as exc:
        _fail(findings, adr, a,
              f"a trava sumiu do schema: {exc}", location=f"{a['file']}{a['pointer']}")
        return
    if "expected" in a:
        if value != a["expected"]:
            _fail(findings, adr, a,
                  f"a trava mudou de valor: esperado {a['expected']!r}, encontrado {value!r}.",
                  location=f"{a['file']}{a['pointer']}")
    else:
        if not isinstance(value, list) or a["contains"] not in value:
            _fail(findings, adr, a,
                  f"a trava não contém mais {a['contains']!r}: encontrado {value!r}.",
                  location=f"{a['file']}{a['pointer']}")


def assert_manual(adr, a, findings, errors) -> None:
    """Nunca reprova. Existe para que o que NÃO é verificável apareça no laudo em vez de sumir."""
    findings.add(
        key=a["id"], origin="manual_assertion", severity="info",
        adr=adr, assertion=a["id"], risk=a.get("risk"),
        summary=f"Não verificável por máquina: {a['description']}",
        evidence=a["justification"],
    )


KINDS = {
    "path_absent": assert_path_absent,
    "path_present": assert_path_present,
    "import_required": assert_import_required,
    "import_forbidden": assert_import_forbidden,
    "file_matches": assert_file_matches,
    "file_lacks": assert_file_lacks,
    "schema_lock": assert_schema_lock,
    "manual": assert_manual,
}


def check_adr_conformance(adr_index: dict, findings: Findings, errors: Errors) -> None:
    seen_ids: set[str] = set()
    for entry in (adr_index or {}).get("adrs", []):
        adr = entry.get("id", "?")
        assertions = entry.get("assertions") or []
        status = entry.get("status")

        if status in ("accepted", "proposed") and not assertions:
            findings.add(
                key=f"{adr}-NO-ASSERTIONS", origin="adr_meta", severity="high",
                adr=adr, risk="RISK-CONF-001",
                summary=f"{adr} está '{status}' sem nenhuma asserção — é a decisão que o ADR-002 proíbe.",
                location=f"{ADR_INDEX} :: {adr}",
                remediation="Declarar ao menos uma asserção executável, ou uma 'manual' justificada.",
            )
        elif assertions and all(a.get("kind") == "manual" for a in assertions):
            findings.add(
                key=f"{adr}-ONLY-MANUAL", origin="adr_meta", severity="medium",
                adr=adr, risk="RISK-CONF-001",
                summary=f"{adr} só tem asserções manuais — declaração honesta, mas nada morde.",
                location=f"{ADR_INDEX} :: {adr}",
            )

        for a in assertions:
            aid = a.get("id", "?")
            if aid in seen_ids:
                findings.add(
                    key=f"{aid}-DUPLICATE", origin="adr_meta", severity="medium",
                    adr=adr, assertion=aid,
                    summary=f"id de asserção duplicado: {aid}", location=ADR_INDEX,
                )
            seen_ids.add(aid)
            fn = KINDS.get(a.get("kind"))
            if fn is None:
                # Schema e código não podem divergir em silêncio.
                errors.err(f"[kind] {aid}: kind '{a.get('kind')}' sem implementação em ci/audit_governance.py")
                continue
            try:
                fn(adr, a, findings, errors)
            except HarnessError as exc:
                errors.err(f"[{aid}] {exc}")


# --------------------------------------------------------------------------------------
# Cobertura de etapas
# --------------------------------------------------------------------------------------

def _enforcer_resolves(e: dict, errors: Errors) -> tuple[bool, str]:
    kind, ref = e.get("kind"), e.get("ref", "")
    if kind == "none":
        return False, "declarado sem fiscal"
    if kind == "external_standard":
        return (e.get("version_source") == "requirements-qa.txt",
                "controle no padrão externo sem âncora de versão local")
    if kind == "schema":
        return hl.rel_exists(ref), f"schema inexistente: {ref}"
    if kind == "workflow_step":
        if not hl.rel_exists(ref):
            return False, f"workflow inexistente: {ref}"
        try:
            names = hl.workflow_step_names(ref)
        except HarnessError as exc:
            errors.err(str(exc))
            return False, str(exc)
        return e.get("step") in names, f"passo '{e.get('step')}' não existe em {ref}"
    if kind == "ci_script":
        if not hl.rel_exists(ref):
            return False, f"script inexistente: {ref}"
        symbol = e.get("symbol")
        if not symbol:
            return True, ""
        try:
            defined = hl.defined_names(hl.REPO / ref)
        except HarnessError as exc:
            errors.err(str(exc))
            return False, str(exc)
        return symbol in defined, f"'{symbol}' não está definido em {ref} (renomeado ou removido?)"
    return False, f"kind desconhecido: {kind}"


def check_stage_coverage(stages_doc: dict, findings: Findings, errors: Errors) -> None:
    for stage in (stages_doc or {}).get("stages", []):
        sid = stage.get("id", "?")

        for artifact in stage.get("artifacts", []):
            if not hl.resolve_glob(artifact):
                findings.add(
                    key=f"{sid}-ARTIFACT-{artifact}", origin="stage_coverage", severity="medium",
                    stage=sid, risk="RISK-STAGE-001", location=artifact,
                    summary=f"{sid} declara o artefato '{artifact}', que não casa nenhum arquivo.",
                )

        resolved = []
        for e in stage.get("enforced_by", []):
            ok, why = _enforcer_resolves(e, errors)
            if ok:
                resolved.append(e)
            else:
                findings.add(
                    key=f"{sid}-ENFORCER-{e.get('ref', '?')}", origin="stage_coverage",
                    severity="high" if e.get("kind") != "none" else "medium",
                    stage=sid, risk="RISK-STAGE-001", location=e.get("ref"),
                    summary=f"{sid}: fiscal não resolve — {why}.",
                    remediation="Restaurar o fiscal, ou declarar kind:none com justificativa "
                                "(a etapa passa a aparecer no laudo como não fiscalizada).",
                )
        if not resolved:
            findings.add(
                key=f"{sid}-UNENFORCED", origin="stage_coverage", severity="high",
                stage=sid, risk="RISK-STAGE-001", location=STAGES,
                summary=f"{sid} não tem nenhum fiscal resolvível — a cobertura desta etapa é afirmada, não verificada.",
            )


def check_repo_partition(stages_doc: dict, findings: Findings) -> None:
    """Todo arquivo pertence a exatamente uma etapa ou a uma isenção declarada.

    É a partição que faz "todas as etapas" ser invariante em vez de aspiração: um diretório
    novo passa a exigir que alguém declare a que etapa ele pertence.
    """
    claimed: set[str] = set()
    for stage in (stages_doc or {}).get("stages", []):
        for artifact in stage.get("artifacts", []):
            for p in hl.resolve_glob(artifact):
                if p.is_file():
                    claimed.add(hl.rel(p))
                else:
                    claimed.update(hl.rel(c) for c in p.rglob("*") if c.is_file())

    exempt: set[str] = set()
    for entry in (stages_doc or {}).get("ungoverned", []):
        matches = hl.resolve_glob(entry["path"])
        if not matches:
            findings.add(
                key=f"UNGOVERNED-STALE-{entry['path']}", origin="stage_partition", severity="low",
                risk="RISK-STAGE-001", location=STAGES,
                summary=f"Isenção morta: '{entry['path']}' não casa nada — isenção que não protege "
                        f"arquivo algum só serve para parecer que a partição fecha.",
            )
        for p in matches:
            if p.is_file():
                exempt.add(hl.rel(p))
            else:
                exempt.update(hl.rel(c) for c in p.rglob("*") if c.is_file())

    for path in hl.walk_files():
        r = hl.rel(path)
        if r not in claimed and r not in exempt:
            findings.add(
                key=f"UNCOVERED-{r}", origin="stage_partition", severity="medium",
                risk="RISK-STAGE-001", location=r,
                summary=f"'{r}' não pertence a nenhuma etapa do projeto nem a uma isenção declarada.",
                remediation="Acrescentar o caminho aos artifacts da etapa certa em harness/stages.yaml, "
                            "ou declarar a isenção em 'ungoverned' com justificativa.",
            )


# --------------------------------------------------------------------------------------
# Governança transversal
# --------------------------------------------------------------------------------------

# Prefixos do PADRÃO EXTERNO. Uma política pode legitimamente apontar para um gate da suíte:
# é controle concreto, só não local — a mesma distinção que o risk-register faz entre
# controls[kind: local_path] e controls[kind: standard_symbol]. E ADR-001 exige que esses
# caminhos NUNCA existam aqui: cobrar existência local deles inverteria a decisão.
EXTERNAL_PREFIXES = ("webqa/", "checks/", "data/")

# Um caminho de verdade tem extensão ou termina em barra. Descarta prosa como `if/then`.
_PATHISH = re.compile(r"^[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*/?$")


# Um rótulo de bloco no rodapé da política: "Fiscalizado por:", "Declarado em:", "Falha como:".
_LABEL = re.compile(r"^[A-ZÀ-Ú][\wÀ-ÿ ]{2,20}:")


def _pointer_block(text: str) -> str | None:
    """Só as linhas do bloco 'Fiscalizado por:', sem invadir 'Declarado em:' nem 'Falha como:'.

    Uma política pode ter mais de uma linha 'Fiscalizado por:' (provenance.md tem duas: a local
    e a do padrão externo); todas entram.
    """
    lines = text.splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("Fiscalizado por:"):
            inside = True
            collected.append(line)
        elif inside and _LABEL.match(line):
            inside = False
        elif inside and line.strip():
            collected.append(line)
        elif inside:
            inside = False
    return "\n".join(collected) if collected else None


def _pointer_targets(line: str) -> list[str]:
    out = []
    for candidate in re.findall(r"`([^`]+)`", line):
        target = candidate.split("::")[0].strip()
        if not _PATHISH.match(target):
            continue
        if not (target.endswith("/") or "." in Path(target).name):
            continue
        out.append(target)
    return out


def check_policy_pointers(findings: Findings) -> None:
    """O policies/README.md enuncia em prosa que entrada sem 'Fiscalizado por:' é lembrete.

    Aqui a regra é executada: o apontamento existe e resolve para algo concreto — um arquivo
    local, ou um símbolo do padrão externo (concreto, porém fora deste repositório).
    """
    for path in sorted((hl.REPO / "harness" / "policies").glob("*.md")):
        r = hl.rel(path)
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        block = _pointer_block(text)
        if block is None:
            findings.add(
                key=f"POLICY-{path.stem}-NO-POINTER", origin="policy_pointer", severity="high",
                risk="RISK-META-001", location=r,
                summary=f"{r} não termina em 'Fiscalizado por:' — é lembrete, nunca garantia.",
            )
            continue
        targets = _pointer_targets(block)
        if not targets:
            findings.add(
                key=f"POLICY-{path.stem}-EMPTY-POINTER", origin="policy_pointer", severity="high",
                risk="RISK-META-001", location=r,
                summary=f"{r} tem 'Fiscalizado por:' sem apontar para nenhum fiscal concreto.",
            )
            continue
        for target in targets:
            if target.startswith(EXTERNAL_PREFIXES):
                continue  # controle no padrão externo: concreto, não local (idem standard_symbol)
            if not hl.rel_exists(target):
                findings.add(
                    key=f"POLICY-{path.stem}-DANGLING-{target}", origin="policy_pointer",
                    severity="high", risk="RISK-META-001", location=r,
                    summary=f"{r} aponta para um fiscal local inexistente: {target}",
                )


def check_risk_control_coverage(risk_doc: dict, findings: Findings) -> None:
    """Todo risco tem ao menos um controle verificável localmente.

    validate_metadata.py não consegue resolver github_environment/branch_protection; um risco
    apoiado SÓ neles é um risco cuja mitigação ninguém neste repositório consegue conferir.
    """
    for risk in (risk_doc or {}).get("risks", []):
        rid = risk.get("id", "?")
        local = [c for c in risk.get("controls", [])
                 if c.get("kind") == "local_path" and hl.rel_exists(c.get("ref", ""))]
        if not local:
            findings.add(
                key=f"{rid}-NO-LOCAL-CONTROL", origin="risk_control", severity="high",
                risk=rid, location=RISK_REGISTER,
                summary=f"{rid} não tem nenhum controle local verificável — a mitigação declarada "
                        f"não pode ser conferida por ninguém dentro deste repositório.",
            )


def check_protected_paths(harness_doc: dict, findings: Findings) -> None:
    paths = (harness_doc or {}).get("repository", {}).get("protected_paths", [])
    owned: list[str] = []
    if hl.rel_exists(CODEOWNERS):
        for line in hl.read_text(CODEOWNERS).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                owned.append(line.split()[0].lstrip("/").rstrip("/"))
    else:
        findings.add(
            key="CODEOWNERS-MISSING", origin="protected_path", severity="high",
            risk="RISK-META-002", location=HARNESS_YAML,
            summary="harness.yaml declara que o fiscal real de protected_paths é 'CODEOWNERS + "
                    "branch protection', e .github/CODEOWNERS não existe.",
        )
        return

    for p in paths:
        if not hl.rel_exists(p):
            findings.add(
                key=f"PROTECTED-MISSING-{p}", origin="protected_path", severity="medium",
                risk="RISK-META-002", location=p,
                summary=f"protected_path '{p}' não existe no repositório.",
            )
        stem = p.rstrip("/")
        if not any(stem == o or stem.startswith(o + "/") or o.startswith(stem) for o in owned):
            findings.add(
                key=f"PROTECTED-UNOWNED-{p}", origin="protected_path", severity="high",
                risk="RISK-META-002", location=CODEOWNERS,
                summary=f"protected_path '{p}' não é coberto por nenhuma regra de CODEOWNERS — "
                        f"a proteção é declarada, mas ninguém precisa revisar a mudança.",
            )


def check_owners_assigned(risk_doc: dict, project_doc: dict, findings: Findings) -> None:
    stakeholders = (project_doc or {}).get("business", {}).get("stakeholders", {})
    for risk in (risk_doc or {}).get("risks", []):
        owner = risk.get("owner")
        value = stakeholders.get(owner)
        if value in (None, "", "unassigned"):
            findings.add(
                key=f"{risk.get('id', '?')}-OWNER-UNASSIGNED", origin="risk_control", severity="medium",
                risk=risk.get("id"), location=PROJECT_YAML,
                summary=f"{risk.get('id')} é de responsabilidade de '{owner}', que está "
                        f"'{value}' em project.yaml — risco sem dono real não é risco gerido.",
            )


# --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fiscal de conformidade governança ↔ repositório.")
    parser.add_argument("--quiet", action="store_true", help="só imprime em caso de falha")
    parser.add_argument("--json", action="store_true", help="imprime o laudo no stdout")
    parser.add_argument("--report", default=REPORT_PATH)
    args = parser.parse_args(argv)

    findings, errors = Findings(), Errors()
    try:
        adr_index = hl.read_yaml(ADR_INDEX)
        stages_doc = hl.read_yaml(STAGES)
        risk_doc = hl.read_yaml(RISK_REGISTER)
        harness_doc = hl.read_yaml(HARNESS_YAML)
        project_doc = hl.read_yaml(PROJECT_YAML)
    except HarnessError as exc:
        print(f"✗ conformidade: {exc}", file=sys.stderr)
        return 2

    check_adr_conformance(adr_index, findings, errors)
    check_stage_coverage(stages_doc, findings, errors)
    check_repo_partition(stages_doc, findings)
    check_policy_pointers(findings)
    check_risk_control_coverage(risk_doc, findings)
    check_protected_paths(harness_doc, findings)
    check_owners_assigned(risk_doc, project_doc, findings)

    stages_covered = [s["id"] for s in (stages_doc or {}).get("stages", [])]
    report = hl.build_report(
        auditor="ci/audit_governance.py", auditor_version=AUDITOR_VERSION,
        findings=findings, stages_covered=stages_covered,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if errors:
        report["result"] = "error"
    try:
        hl.emit_report(args.report, report)
    except HarnessError as exc:
        print(f"✗ conformidade: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        hl.print_summary("conformidade", findings, errors, quiet=args.quiet)

    if errors:
        return 2
    return 1 if findings.blocking() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
