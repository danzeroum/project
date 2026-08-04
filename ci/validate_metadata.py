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
import sys

from jsonschema import Draft202012Validator

import harness_lib as hl
from harness_lib import CONCRETE, REPO, SCHEMAS, HarnessError, rel_exists

# (arquivo de metadado, schema) — schema None = só validação de YAML + invariantes de cabeçalho.
DOCS = [
    ("project.yaml", "project.schema.json"),
    ("target.lock", "target-lock.schema.json"),
    ("governance/risk-register.yaml", "risk-register.schema.json"),
    ("business/capabilities.yaml", "capabilities.schema.json"),
    ("architecture/components.yaml", "components.schema.json"),
    ("architecture/interfaces.yaml", "interfaces.schema.json"),
    ("design/design-system.yaml", "design-system.schema.json"),
    ("design/ui-surfaces.yaml", "ui-surfaces.schema.json"),
    ("architecture/adr/index.yaml", "adr-index.schema.json"),
    ("business/requirements/backlog.yaml", "backlog.schema.json"),
    ("business/vision.yaml", "vision.schema.json"),
    ("harness/harness.yaml", "harness.schema.json"),
    ("harness/stages.yaml", "stages.schema.json"),
    ("governance/data-inventory.yaml", "data-inventory.schema.json"),
    ("governance/privacy-review.yaml", "privacy-review.schema.json"),
]

# Propostas de mudança: artefatos versionados validados por schema + semântica.
CHANGE_PROPOSALS_DIR = "harness/change-proposals"
# Regras de negócio: um arquivo por capacidade, validado por schema + semântica.
BUSINESS_RULES_DIR = "business/rules"

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def load_yaml(rel: str) -> dict | None:
    if not rel_exists(rel):
        err(f"[falta] arquivo de metadado ausente: {rel}")
        return None
    try:
        return hl.read_yaml(rel)
    except HarnessError as exc:  # pragma: no cover - defensivo
        err(str(exc))
        return None


def validate_all_schemas_are_valid() -> None:
    for schema_file in sorted(SCHEMAS.glob("*.json")):
        try:
            Draft202012Validator.check_schema(json.loads(schema_file.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001 - reporta qualquer schema inválido
            err(f"[schema] {schema_file.name} é um JSON Schema inválido: {exc}")


def validate_structural(rel: str, schema_name: str, doc: dict) -> None:
    for msg in hl.schema_errors(rel, schema_name, doc):
        err(msg)


def check_header_invariants(rel: str, doc: dict) -> None:
    # I11 (reforço; o schema já garante via oneOf onde há schema).
    for msg in hl.header_invariant_errors(rel, doc):
        err(msg)


def exact_pin(rel: str = "requirements-qa.txt") -> str | None:
    pin, problems = hl.exact_pin(rel)
    for msg in problems:
        err(msg)
    return pin


def check_version_single_source(project_doc: dict | None) -> None:
    """I2/I3: a versão mora só em requirements-qa.txt; config.yaml espelha sob verificação."""
    pin = exact_pin()
    # project.yaml referencia, nunca restata (o schema já garante version_source const).
    if project_doc:
        qs = project_doc.get("quality_standard", {})
        if qs.get("version_source") != "requirements-qa.txt":
            err("[I2] project.yaml: quality_standard.version_source deve ser 'requirements-qa.txt'")
    # I3: o único espelho tolerado — config.yaml.standard_version == pin.
    if rel_exists("tests/qa/config.yaml") and pin is not None:
        cfg = hl.read_yaml("tests/qa/config.yaml") or {}
        mirror = str(cfg.get("standard_version", ""))
        if mirror != pin:
            err(f"[I3] tests/qa/config.yaml standard_version ({mirror!r}) != pin ({pin!r})")


def check_target_lock(project_doc: dict | None, lock_doc: dict | None) -> None:
    """O papel do repositório é declarado em dois arquivos; eles têm que concordar.

    project.yaml diz QUAL alvo (repo, ref) e ONDE o SHA mora; target.lock guarda o SHA. A separação
    é a mesma de quality_standard.version_source → requirements-qa.txt, e existe pela mesma razão:
    o número num lugar só. Dois arquivos que discordam sobre o papel do repositório são pior que um
    só, porque cada fiscal pode acreditar em um deles e ambos passam.
    """
    if not project_doc or not lock_doc:
        return
    declared = (project_doc.get("project") or {}).get("kind")
    locked = lock_doc.get("kind")
    if declared != locked:
        err(f"[alvo] target.lock diz kind={locked!r} e project.yaml diz kind={declared!r} — "
            f"o papel do repositório não pode depender de qual arquivo se lê primeiro")
        return

    target = project_doc.get("target")
    if declared == "derived":
        # O schema já exige o bloco; aqui cobramos a âncora, que é o que impede o SHA de vazar.
        if (target or {}).get("lock_source") != "target.lock":
            err("[alvo] project.yaml: target.lock_source deve ser 'target.lock' — "
                "o SHA mora num lugar só")
    elif target is not None:  # pragma: no cover - o schema já reprova antes
        err("[alvo] project.yaml declara 'target' com kind:mold — "
            "um molde ancorado num alvo específico deixou de ser genérico")


def check_target_roots(project_doc: dict | None) -> None:
    """As raízes de código declaradas existem de fato no alvo materializado.

    Só verificável com o workspace presente (é `/bootstrap` que o materializa), e por isso a
    ausência dele é silêncio, não achado: cobrar aqui transformaria "ainda não rodou o bootstrap"
    em divergência de metadado. Com o workspace presente, porém, raiz declarada que não existe é
    achado — um code_roots chutado torna a invariante do código órfão verdadeira por vacuidade,
    que é pior do que não tê-la.
    """
    target = (project_doc or {}).get("target")
    if not target or not rel_exists("workspace/target"):
        return
    for root in target.get("code_roots", []):
        if not rel_exists(f"workspace/target/{root.strip('/')}"):
            err(f"[alvo] code_roots declara '{root}', que não existe no alvo no SHA de target.lock")


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


def check_components(doc: dict | None, caps: dict[str, dict], req_items: dict[str, dict]) -> set[str]:
    if not doc:
        return set()
    building = {"in_progress", "done"}
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
        for req in comp.get("implements", []):
            if req not in req_items:
                err(f"[CMP] {cmid}: implements {req} não existe no backlog")
                continue
            if req_items[req].get("capability") != cap_ref:
                err(f"[CMP] {cmid}: implements {req} é da capacidade "
                    f"{req_items[req].get('capability')}, não de {cap_ref}")
            if req_items[req].get("status") not in building:
                err(f"[CMP] {cmid}: implements {req} está '{req_items[req].get('status')}' "
                    f"— um componente não implementa um requisito ainda não iniciado")
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


def check_ui_surfaces(doc: dict | None, caps: dict[str, dict], req_caps: dict[str, str]) -> None:
    """I7: toda superfície de UI aponta para uma capacidade existente; um requisito satisfeito
    existe e compartilha a mesma capacidade da superfície (coerência)."""
    if not doc:
        return
    for surface in doc.get("ui_surfaces", []):
        sid = surface.get("id", "?")
        cap_ref = surface.get("capability")
        if cap_ref not in caps:
            err(f"[I7] {sid}: capability {cap_ref} não existe em capabilities.yaml")
        for req in surface.get("satisfies", []):
            if req not in req_caps:
                err(f"[UI] {sid}: satisfies {req} não existe no backlog")
            elif req_caps[req] != cap_ref:
                err(f"[UI] {sid}: satisfies {req} é da capacidade {req_caps[req]}, não de {cap_ref}")


def check_business_rules(caps: dict[str, dict]) -> dict[str, str]:
    """Cada arquivo de regras aponta para uma capacidade real e é referenciado de volta por ela;
    regras verificadas apontam para testes existentes (condicionado à maturidade).
    Retorna o mapa regra→capacidade para o backlog cruzar governed_by."""
    rule_caps: dict[str, str] = {}
    rules_dir = REPO / BUSINESS_RULES_DIR
    if not rules_dir.exists():
        return rule_caps
    for path in sorted(rules_dir.glob("*.yaml")):
        rel = hl.rel(path)
        try:
            doc = hl.read_yaml(rel)
        except HarnessError as exc:  # pragma: no cover - defensivo
            err(str(exc))
            continue
        check_header_invariants(rel, doc)
        validate_structural(rel, "business-rules.schema.json", doc)
        cap_ref = (doc or {}).get("capability")
        if cap_ref not in caps:
            err(f"[regra] {rel}: capability {cap_ref} não existe em capabilities.yaml")
        elif rel not in caps[cap_ref].get("business_rules", []):
            err(f"[regra] {rel}: {cap_ref} não referencia este arquivo em business_rules (elo quebrado)")
        for rule in (doc or {}).get("rules", []):
            if cap_ref:
                rule_caps[rule.get("id")] = cap_ref
            if rule.get("status") in CONCRETE:
                for p in rule.get("verified_by", []):
                    if not rel_exists(p):
                        err(f"[regra] {rule.get('id', '?')}: verified_by inexistente: {p}")
                    elif not p.startswith("tests/"):
                        err(f"[regra] {rule.get('id', '?')}: verified_by fora de tests/: {p}")
    return rule_caps


def metric_ids(vision_doc: dict | None) -> set[str]:
    if not vision_doc:
        return set()
    return {m.get("id") for m in vision_doc.get("product", {}).get("success_metrics", [])}


def check_backlog(doc: dict | None, caps: dict[str, dict], risk_ids: set[str],
                  metrics: set[str], rule_caps: dict[str, str]) -> None:
    """Cada requisito pertence a uma capacidade real; depends_on, risk, metrics e governed_by
    resolvem — e cada regra que rege um requisito compartilha a capacidade dele."""
    if not doc:
        return
    req_ids = {i.get("id") for i in doc.get("items", [])}
    for item in doc.get("items", []):
        rid = item.get("id", "?")
        cap = item.get("capability")
        if cap not in caps:
            err(f"[REQ] {rid}: capability {cap} não existe em capabilities.yaml")
        for dep in item.get("depends_on", []):
            if dep not in req_ids:
                err(f"[REQ] {rid}: depends_on aponta para requisito inexistente: {dep}")
        risk = item.get("risk")
        if risk and risk not in risk_ids:
            err(f"[REQ] {rid}: risco citado {risk} não existe no risk-register")
        for met in item.get("metrics", []):
            if met not in metrics:
                err(f"[REQ] {rid}: métrica citada {met} não existe em vision.yaml")
        for rule in item.get("governed_by", []):
            if rule not in rule_caps:
                err(f"[REQ] {rid}: governed_by {rule} não existe em business/rules")
            elif rule_caps[rule] != cap:
                err(f"[REQ] {rid}: governed_by {rule} é da capacidade {rule_caps[rule]}, não de {cap}")
        vtests = item.get("validated_by", [])
        if vtests and item.get("status") not in {"in_progress", "done"}:
            err(f"[REQ] {rid}: validated_by presente mas o requisito está "
                f"'{item.get('status')}' — só requisito iniciado é validado por teste")
        cap_tests = set(caps.get(cap, {}).get("test_paths", []))
        for t in vtests:
            if not rel_exists(t):
                err(f"[REQ] {rid}: validated_by teste inexistente: {t}")
            elif not t.startswith("tests/"):
                err(f"[REQ] {rid}: validated_by fora de tests/: {t}")
            elif t not in cap_tests:
                err(f"[REQ] {rid}: validated_by '{t}' não consta em {cap}.test_paths")


def check_adr_index(doc: dict | None, caps: dict[str, dict], comp_ids: set[str],
                    risk_ids: set[str]) -> None:
    """Cada ADR do índice tem arquivo real; supersedes e referências (CAP/CMP/RISK) resolvem."""
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
        for cmp in adr.get("related_components", []):
            if cmp not in comp_ids:
                err(f"[ADR] {aid}: related_components {cmp} não existe em components.yaml")
        for rref in adr.get("related_risks", []):
            if rref not in risk_ids:
                err(f"[ADR] {aid}: related_risks {rref} não existe no registro")


def check_adr_assertion_refs(doc: dict | None, risk_ids: set[str]) -> None:
    """Toda asserção cita um risco do registro — é o elo que faz divergência virar risco.

    A EXECUÇÃO da asserção é de ci/audit_governance.py; aqui só se resolve o ID, que é o
    trabalho deste fiscal.
    """
    if not doc:
        return
    for adr in doc.get("adrs", []):
        for a in adr.get("assertions", []):
            rref = a.get("risk")
            if rref and rref not in risk_ids:
                err(f"[ADR] {a.get('id', '?')}: risco citado {rref} não existe no registro")


def check_data_inventory(doc: dict | None, comp_ids: set[str]) -> None:
    """Todo campo de dado pessoal pertence a um componente real — sem dono, não há responsável."""
    if not doc:
        return
    for f in doc.get("fields", []):
        cmp_ref = f.get("owning_component")
        if cmp_ref not in comp_ids:
            err(f"[LGPD] {f.get('id', '?')}: owning_component {cmp_ref} não existe "
                f"em components.yaml")


def check_privacy_review(doc: dict | None, risk_ids: set[str]) -> None:
    """Issue P0/P1 do julgamento aponta para um risco do registro (o schema já exige o campo)."""
    if not doc:
        return
    for issue in doc.get("review", {}).get("issues", []):
        rref = issue.get("risk")
        if rref and rref not in risk_ids:
            err(f"[LGPD] {issue.get('id', '?')}: risco citado {rref} não existe no registro")


def check_change_proposals(caps: dict[str, dict], comp_ids: set[str], risk_ids: set[str]) -> None:
    """Cada proposta afeta apenas IDs reais e cita apenas riscos do registro."""
    proposals_dir = REPO / CHANGE_PROPOSALS_DIR
    if not proposals_dir.exists():
        return
    for path in sorted(proposals_dir.glob("*.yaml")):
        rel = hl.rel(path)
        try:
            doc = hl.read_yaml(rel)
        except HarnessError as exc:  # pragma: no cover - defensivo
            err(str(exc))
            continue
        check_header_invariants(rel, doc)
        validate_structural(rel, "change-proposal.schema.json", doc)
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


def main(argv: list[str] | None = None) -> int:
    # Zerado na entrada: validate_all.py chama este main in-process, junto dos demais fiscais.
    errors.clear()
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
    check_target_lock(loaded.get("project.yaml"), loaded.get("target.lock"))
    check_target_roots(loaded.get("project.yaml"))
    backlog_doc = loaded.get("business/requirements/backlog.yaml") or {}
    req_items = {i.get("id"): i for i in backlog_doc.get("items", [])}
    caps = check_capabilities(loaded.get("business/capabilities.yaml"))
    comp_ids = check_components(loaded.get("architecture/components.yaml"), caps, req_items)
    risk_ids = check_risk_controls(loaded.get("governance/risk-register.yaml"))
    check_interfaces(loaded.get("architecture/interfaces.yaml"), loaded.get("architecture/components.yaml"))
    req_caps = {rid: item.get("capability") for rid, item in req_items.items()}
    check_ui_surfaces(loaded.get("design/ui-surfaces.yaml"), caps, req_caps)
    rule_caps = check_business_rules(caps)
    metrics = metric_ids(loaded.get("business/vision.yaml"))
    check_backlog(loaded.get("business/requirements/backlog.yaml"), caps, risk_ids, metrics, rule_caps)
    check_adr_index(loaded.get("architecture/adr/index.yaml"), caps, comp_ids, risk_ids)
    check_adr_assertion_refs(loaded.get("architecture/adr/index.yaml"), risk_ids)
    check_data_inventory(loaded.get("governance/data-inventory.yaml"), comp_ids)
    check_privacy_review(loaded.get("governance/privacy-review.yaml"), risk_ids)
    check_change_proposals(caps, comp_ids, risk_ids)

    if errors:
        print(f"✗ validação de metadados falhou ({len(errors)} inconsistência(s)):\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("✓ metadados coerentes: schema, paths, IDs e controles casam com o repositório.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
