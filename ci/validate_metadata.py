#!/usr/bin/env python3
"""Fiscal de metadados — LINTER de CI, não runner da harness.

Não orquestra agentes, não executa modos, não toca a rede. Apenas verifica que os metadados
DECLARADOS correspondem ao repositório REAL: schema válido, paths existem, IDs resolvem,
controles apontam para algo concreto. É o que transforma declaração em contrato ("morde").

Fiscal estrutural: JSON Schema (forma, tipos, enums, padrões).
Fiscal semântico: as funções check_* abaixo (existência de path, coerência entre documentos),
com a existência de código/teste CONDICIONADA à maturidade da capacidade/componente.

Uso:  python ci/validate_metadata.py
Sai com código 1 ao primeiro conjunto de inconsistências; 0 se tudo casar.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "harness" / "schemas"

# Maturidades em que código e teste DEVEM existir fisicamente.
CONCRETE = {"implemented", "verified"}

# (arquivo de metadado, schema) — schema None = só validação de YAML + invariantes de cabeçalho.
DOCS = [
    ("project.yaml", "project.schema.json"),
    ("governance/risk-register.yaml", "risk-register.schema.json"),
    ("business/capabilities.yaml", "capabilities.schema.json"),
    ("architecture/components.yaml", "components.schema.json"),
    ("architecture/interfaces.yaml", "interfaces.schema.json"),
    ("design/design-system.yaml", "design-system.schema.json"),
    ("design/ui-surfaces.yaml", "ui-surfaces.schema.json"),
    ("architecture/adr/index.yaml", "adr-index.schema.json"),
    ("business/requirements/backlog.yaml", "backlog.schema.json"),
    ("business/vision.yaml", "vision.schema.json"),
]

# Propostas de mudança: artefatos versionados validados por schema + semântica.
CHANGE_PROPOSALS_DIR = "harness/change-proposals"
# Regras de negócio: um arquivo por capacidade, validado por schema + semântica.
BUSINESS_RULES_DIR = "business/rules"

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def load_yaml(rel: str) -> dict | None:
    path = REPO / rel
    if not path.exists():
        err(f"[falta] arquivo de metadado ausente: {rel}")
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensivo
        err(f"[yaml] {rel}: {exc}")
        return None


def validate_all_schemas_are_valid() -> None:
    for schema_file in sorted(SCHEMAS.glob("*.json")):
        try:
            Draft202012Validator.check_schema(json.loads(schema_file.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001 - reporta qualquer schema inválido
            err(f"[schema] {schema_file.name} é um JSON Schema inválido: {exc}")


def validate_structural(rel: str, schema_name: str, doc: dict) -> None:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: e.path):
        loc = "/".join(str(p) for p in e.path) or "(raiz)"
        err(f"[estrutural] {rel} em '{loc}': {e.message}")


def check_header_invariants(rel: str, doc: dict) -> None:
    # I11 (reforço; o schema já garante via oneOf onde há schema).
    sot = doc.get("source_of_truth")
    gen = doc.get("generated_from")
    if sot is True and gen not in (None,):
        err(f"[I11] {rel}: source_of_truth:true exige generated_from:null")
    if sot is False and not gen:
        err(f"[I11] {rel}: source_of_truth:false exige generated_from não-vazio")


def exact_pin(rel: str = "requirements-qa.txt") -> str | None:
    path = REPO / rel
    if not path.exists():
        err(f"[falta] {rel} ausente — o pin do padrão é obrigatório")
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*webqa-suite==([^\s#]+)", line)
        if m:
            return m.group(1)
    err(f"[I2] {rel}: webqa-suite deve estar pinado com == (sem faixa)")
    return None


def check_version_single_source(project_doc: dict | None) -> None:
    """I2/I3: a versão mora só em requirements-qa.txt; config.yaml espelha sob verificação."""
    pin = exact_pin()
    # project.yaml referencia, nunca restata (o schema já garante version_source const).
    if project_doc:
        qs = project_doc.get("quality_standard", {})
        if qs.get("version_source") != "requirements-qa.txt":
            err("[I2] project.yaml: quality_standard.version_source deve ser 'requirements-qa.txt'")
    # I3: o único espelho tolerado — config.yaml.standard_version == pin.
    cfg_path = REPO / "tests" / "qa" / "config.yaml"
    if cfg_path.exists() and pin is not None:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        mirror = str(cfg.get("standard_version", ""))
        if mirror != pin:
            err(f"[I3] tests/qa/config.yaml standard_version ({mirror!r}) != pin ({pin!r})")


def rel_exists(p: str) -> bool:
    return (REPO / p).exists()


def check_capabilities(doc: dict | None) -> dict[str, dict]:
    caps: dict[str, dict] = {}
    if not doc:
        return caps
    for cap in doc.get("capabilities", []):
        cid = cap.get("id", "?")
        caps[cid] = cap
        status = cap.get("status")
        srcs = cap.get("source_paths", [])
        tsts = cap.get("test_paths", [])
        if status in CONCRETE:
            if not srcs:
                err(f"[I4] {cid} é {status} mas não declara source_paths")
            if not tsts:
                err(f"[I5] {cid} é {status} mas não declara test_paths")
            for p in srcs:
                if not rel_exists(p):
                    err(f"[I4] {cid}: source_path inexistente: {p}")
                elif not p.startswith("src/"):
                    err(f"[I4] {cid}: source_path fora de src/: {p}")
            for p in tsts:
                if not rel_exists(p):
                    err(f"[I5] {cid}: test_path inexistente: {p}")
                elif not p.startswith("tests/"):
                    err(f"[I5] {cid}: test_path fora de tests/: {p}")
        for p in cap.get("business_rules", []):
            if not rel_exists(p):
                err(f"[regra] {cid}: business_rules aponta para arquivo inexistente: {p}")
    return caps


def check_components(doc: dict | None, caps: dict[str, dict]) -> set[str]:
    if not doc:
        return set()
    comp_ids = {c.get("id") for c in doc.get("components", [])}
    for comp in doc.get("components", []):
        cmid = comp.get("id", "?")
        status = comp.get("status")
        cap_ref = comp.get("capability")
        if cap_ref not in caps:
            err(f"[I6] {cmid}: capability {cap_ref} não existe em capabilities.yaml")
        for dep in comp.get("depends_on", []):
            if dep not in comp_ids:
                err(f"[dep] {cmid}: depends_on aponta para componente inexistente: {dep}")
        if status in CONCRETE:
            for p in comp.get("source_paths", []):
                if not rel_exists(p):
                    err(f"[componente] {cmid}: source_path inexistente: {p}")
            cap_tests = set(caps.get(cap_ref, {}).get("test_paths", []))
            for p in comp.get("tested_by", []):
                if not rel_exists(p):
                    err(f"[I6] {cmid}: tested_by inexistente: {p}")
                elif cap_ref in caps and p not in cap_tests:
                    err(f"[I6] {cmid}: tested_by '{p}' não consta em {cap_ref}.test_paths")
    return comp_ids


def check_risk_controls(doc: dict | None) -> set[str]:
    if not doc:
        return set()
    risk_ids: set[str] = set()
    for risk in doc.get("risks", []):
        rid = risk.get("id", "?")
        risk_ids.add(rid)
        for ctrl in risk.get("controls", []):
            kind = ctrl.get("kind")
            ref = ctrl.get("ref", "")
            if kind == "local_path":
                if not rel_exists(ref):
                    err(f"[I8] {rid}: controle local_path inexistente: {ref}")
            elif kind == "standard_symbol":
                # Não resolvemos símbolo em repo externo; garantimos a âncora de versão local.
                if ctrl.get("version_source") != "requirements-qa.txt":
                    err(f"[I8] {rid}: standard_symbol deve ancorar version_source em requirements-qa.txt")
            # github_environment / branch_protection: não verificáveis localmente; forma já validada.
    return risk_ids


def check_interfaces(doc: dict | None, components_doc: dict | None) -> None:
    """provider/consumers existem; exposes ⊆ exposes do provedor; consumidor depende do provedor."""
    if not doc:
        return
    comps = {c.get("id"): c for c in (components_doc or {}).get("components", [])}
    for ifc in doc.get("interfaces", []):
        iid = ifc.get("id", "?")
        provider = ifc.get("provider")
        if provider not in comps:
            err(f"[IFC] {iid}: provider {provider} não existe em components.yaml")
        else:
            prov_exposes = set(comps[provider].get("exposes", []))
            for sym in ifc.get("exposes", []):
                if sym not in prov_exposes:
                    err(f"[IFC] {iid}: exposes '{sym}' não é exposto por {provider}")
        for consumer in ifc.get("consumers", []):
            if consumer not in comps:
                err(f"[IFC] {iid}: consumer {consumer} não existe em components.yaml")
            elif provider not in comps.get(consumer, {}).get("depends_on", []):
                err(f"[IFC] {iid}: {consumer} consome mas não declara depends_on {provider}")


def check_ui_surfaces(doc: dict | None, caps: dict[str, dict]) -> None:
    """I7: toda superfície de UI aponta para uma capacidade existente."""
    if not doc:
        return
    for surface in doc.get("ui_surfaces", []):
        sid = surface.get("id", "?")
        cap_ref = surface.get("capability")
        if cap_ref not in caps:
            err(f"[I7] {sid}: capability {cap_ref} não existe em capabilities.yaml")


def check_business_rules(caps: dict[str, dict]) -> None:
    """Cada arquivo de regras aponta para uma capacidade real e é referenciado de volta por ela;
    regras verificadas apontam para testes existentes (condicionado à maturidade)."""
    rules_dir = REPO / BUSINESS_RULES_DIR
    if not rules_dir.exists():
        return
    schema = json.loads((SCHEMAS / "business-rules.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path in sorted(rules_dir.glob("*.yaml")):
        rel = path.relative_to(REPO).as_posix()
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # pragma: no cover - defensivo
            err(f"[yaml] {rel}: {exc}")
            continue
        check_header_invariants(rel, doc)
        for e in sorted(validator.iter_errors(doc), key=lambda e: e.path):
            loc = "/".join(str(p) for p in e.path) or "(raiz)"
            err(f"[estrutural] {rel} em '{loc}': {e.message}")
        cap_ref = (doc or {}).get("capability")
        if cap_ref not in caps:
            err(f"[regra] {rel}: capability {cap_ref} não existe em capabilities.yaml")
        elif rel not in caps[cap_ref].get("business_rules", []):
            err(f"[regra] {rel}: {cap_ref} não referencia este arquivo em business_rules (elo quebrado)")
        for rule in (doc or {}).get("rules", []):
            if rule.get("status") in CONCRETE:
                for p in rule.get("verified_by", []):
                    if not rel_exists(p):
                        err(f"[regra] {rule.get('id', '?')}: verified_by inexistente: {p}")
                    elif not p.startswith("tests/"):
                        err(f"[regra] {rule.get('id', '?')}: verified_by fora de tests/: {p}")


def metric_ids(vision_doc: dict | None) -> set[str]:
    if not vision_doc:
        return set()
    return {m.get("id") for m in vision_doc.get("product", {}).get("success_metrics", [])}


def check_backlog(doc: dict | None, caps: dict[str, dict], risk_ids: set[str], metrics: set[str]) -> None:
    """Cada requisito pertence a uma capacidade real; depends_on, risk e metrics resolvem."""
    if not doc:
        return
    req_ids = {i.get("id") for i in doc.get("items", [])}
    for item in doc.get("items", []):
        rid = item.get("id", "?")
        if item.get("capability") not in caps:
            err(f"[REQ] {rid}: capability {item.get('capability')} não existe em capabilities.yaml")
        for dep in item.get("depends_on", []):
            if dep not in req_ids:
                err(f"[REQ] {rid}: depends_on aponta para requisito inexistente: {dep}")
        risk = item.get("risk")
        if risk and risk not in risk_ids:
            err(f"[REQ] {rid}: risco citado {risk} não existe no risk-register")
        for met in item.get("metrics", []):
            if met not in metrics:
                err(f"[REQ] {rid}: métrica citada {met} não existe em vision.yaml")


def check_adr_index(doc: dict | None, caps: dict[str, dict], risk_ids: set[str]) -> None:
    """Cada ADR do índice tem arquivo real; supersedes e referências (CAP/RISK) resolvem."""
    if not doc:
        return
    adr_ids = {a.get("id") for a in doc.get("adrs", [])}
    for adr in doc.get("adrs", []):
        aid = adr.get("id", "?")
        if not rel_exists(adr.get("file", "")):
            err(f"[ADR] {aid}: arquivo inexistente: {adr.get('file')}")
        for sup in adr.get("supersedes", []):
            if sup not in adr_ids:
                err(f"[ADR] {aid}: supersedes aponta para ADR inexistente: {sup}")
        for cap in adr.get("related_capabilities", []):
            if cap not in caps:
                err(f"[ADR] {aid}: related_capabilities {cap} não existe")
        for rref in adr.get("related_risks", []):
            if rref not in risk_ids:
                err(f"[ADR] {aid}: related_risks {rref} não existe no registro")


def check_change_proposals(caps: dict[str, dict], comp_ids: set[str], risk_ids: set[str]) -> None:
    """Cada proposta afeta apenas IDs reais e cita apenas riscos do registro."""
    proposals_dir = REPO / CHANGE_PROPOSALS_DIR
    if not proposals_dir.exists():
        return
    schema = json.loads((SCHEMAS / "change-proposal.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path in sorted(proposals_dir.glob("*.yaml")):
        rel = path.relative_to(REPO).as_posix()
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # pragma: no cover - defensivo
            err(f"[yaml] {rel}: {exc}")
            continue
        check_header_invariants(rel, doc)
        for e in sorted(validator.iter_errors(doc), key=lambda e: e.path):
            loc = "/".join(str(p) for p in e.path) or "(raiz)"
            err(f"[estrutural] {rel} em '{loc}': {e.message}")
        proposal = (doc or {}).get("proposal", {})
        pid = proposal.get("id", rel)
        for cid in proposal.get("capabilities_affected", []):
            if cid not in caps:
                err(f"[CP] {pid}: capabilities_affected {cid} não existe em capabilities.yaml")
        for cmid in proposal.get("components_affected", []):
            if cmid not in comp_ids:
                err(f"[CP] {pid}: components_affected {cmid} não existe em components.yaml")
        for rref in proposal.get("risk_assessment", {}).get("risks", []):
            if rref not in risk_ids:
                err(f"[CP] {pid}: risco citado {rref} não existe no risk-register")


def main() -> int:
    validate_all_schemas_are_valid()

    loaded: dict[str, dict] = {}
    for rel, schema_name in DOCS:
        doc = load_yaml(rel)
        if doc is None:
            continue
        loaded[rel] = doc
        check_header_invariants(rel, doc)
        if schema_name:
            validate_structural(rel, schema_name, doc)

    check_version_single_source(loaded.get("project.yaml"))
    caps = check_capabilities(loaded.get("business/capabilities.yaml"))
    comp_ids = check_components(loaded.get("architecture/components.yaml"), caps)
    risk_ids = check_risk_controls(loaded.get("governance/risk-register.yaml"))
    check_interfaces(loaded.get("architecture/interfaces.yaml"), loaded.get("architecture/components.yaml"))
    check_ui_surfaces(loaded.get("design/ui-surfaces.yaml"), caps)
    check_business_rules(caps)
    metrics = metric_ids(loaded.get("business/vision.yaml"))
    check_backlog(loaded.get("business/requirements/backlog.yaml"), caps, risk_ids, metrics)
    check_adr_index(loaded.get("architecture/adr/index.yaml"), caps, risk_ids)
    check_change_proposals(caps, comp_ids, risk_ids)

    if errors:
        print(f"✗ validação de metadados falhou ({len(errors)} inconsistência(s)):\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("✓ metadados coerentes: schema, paths, IDs e controles casam com o repositório.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
