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


def assert_dir_allowlist(adr, a, findings, errors) -> None:
    """O diretório contém APENAS o que a asserção lista. Enumera em vez de adivinhar.

    Existe porque a forma óbvia — `path_absent` com glob — é uma armadilha, e vale registrar qual:
    `assert_path_absent` usa `rel_exists`, que é LITERAL. Um glob como
    `harness/releases/*.manifest.json` nunca "existiria", a asserção passaria sempre, e a mutação
    canônica `criar_caminho` criaria um arquivo chamado literalmente `v*.manifest.json` — que
    `rel_exists` ENCONTRARIA. A asserção ficaria vermelha depois de mutada e a prova de mutação
    CERTIFICARIA uma trava decorativa. Um fiscal de fiscais enganado é pior que fiscal nenhum,
    porque produz um selo.

    Enumerar o diretório não tem esse buraco: o que estiver lá aparece, e o inverso canônico —
    pôr qualquer outra coisa dentro — é honesto.
    """
    raiz = hl.REPO / a["dir"].rstrip("/")
    if not raiz.is_dir():
        _unresolvable(findings, adr, a, f"'{a['dir']}' não é um diretório — uma allowlist que não "
                                        f"encontra o que vigiar está quebrada, não satisfeita")
        return
    permitidos = set(a["allow"])
    for p in sorted(raiz.iterdir()):
        if p.name not in permitidos:
            _fail(findings, adr, a,
                  f"'{hl.rel(p)}' está em {a['dir']} e a allowlist só admite "
                  f"{sorted(permitidos)}.", location=hl.rel(p))


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
    "dir_allowlist": assert_dir_allowlist,
    "import_required": assert_import_required,
    "import_forbidden": assert_import_forbidden,
    "file_matches": assert_file_matches,
    "file_lacks": assert_file_lacks,
    "schema_lock": assert_schema_lock,
    "manual": assert_manual,
}


def check_assertion_self_match(adr_index: dict, findings: Findings, errors: Errors) -> None:
    """A asserção que casa com a PRÓPRIA DECLARAÇÃO fica verde por existir, não por conformidade.

    É a parte mecanizável de um padrão de erro que já custou cinco correções em duas semanas
    (CP-039, e a política em harness/policies/metadata-boundaries.md o nomeia por extenso): a regra
    é escrita contra a MENÇÃO de uma coisa em vez de contra o FATO dela, e o documento que explica
    a regra vira o primeiro a satisfazê-la sozinho.

    A forma exata que dá para pegar por máquina: uma asserção `file_matches` cujo `pattern` casa o
    `index.yaml` que a declara. O texto da própria declaração passa a ser a evidência de
    conformidade — a asserção não pode reprovar, porque enquanto ela existir o padrão estará lá.
    Foi o que aconteceu com a ADR-028 deste molde, e até a CP-039 a lição era só prosa.

    `file_lacks` entra pelo motivo espelhado e ainda mais direto: um padrão PROIBIDO que casa o
    index está sendo violado pelo documento que o proíbe — reprova sempre, e por si mesmo.
    """
    idx_rel = ADR_INDEX
    if not hl.rel_exists(idx_rel):
        return
    bruto = hl.read_text(idx_rel)
    for entry in (adr_index or {}).get("adrs", []):
        for a in entry.get("assertions") or []:
            if a.get("kind") not in ("file_matches", "file_lacks"):
                continue
            # SÓ quando a asserção MIRA o index. A primeira versão deste fiscal não tinha esta
            # linha e acusou 40 vezes de uma vez — porque `pattern: "COCKPIT_SRC"` está escrito no
            # index, então todo padrão casa a própria linha `pattern:` trivialmente.
            # Escrevi um fiscal contra a âncora-na-menção e ele ancorou na menção. Sexta ocorrência,
            # e fica registrada aqui porque o padrão é mais teimoso do que a consciência dele.
            if idx_rel not in (a.get("files") or []):
                continue
            try:
                rx = re.compile(a["pattern"], re.MULTILINE | (re.DOTALL if a.get("dotall") else 0))
            except re.error:
                continue  # padrão inválido já é acusado por quem o executa
            if not rx.search(bruto):
                continue
            findings.add(
                key=f"{a['id']}-SELF-MATCH", origin="assertion_self_match", severity="high",
                adr=entry.get("id", "?"), assertion=a["id"], risk=a.get("risk"),
                location=f"{idx_rel} :: {a['id']}",
                summary=f"{a['id']}: o padrão /{a['pattern']}/ casa o próprio {idx_rel}, que é onde "
                        f"a asserção é DECLARADA — ela fica verde por existir, não por o "
                        f"repositório estar conforme.",
                remediation="Ancorar o padrão no FATO e não na MENÇÃO: quem CRIA o artefato, quem "
                            "o EXECUTA, quem o CONFIGURA — não a string que o nomeia.",
            )


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


def check_stage_coverage(stages_doc: dict, findings: Findings, errors: Errors,
                         project_doc: dict | None = None) -> None:
    """Artefato de etapa casa arquivo real — salvo enquanto o derivado incuba (CP-019).

    Um derivado recém-adotado ainda não tem os artefatos que a ingestão vai escrever: o CP-000
    remove os do exemplo, e business/rules some do versionamento porque diretório vazio não é
    versionado. Cobrar aqui transformaria "a ingestão ainda não chegou nesta etapa" em achado
    permanente, do mesmo modo que o piso das coleções fazia antes do CP-017 — e a resposta é a
    mesma, pelo mesmo sinal declarado, porque é o mesmo problema uma camada acima.

    A permissão é AMPLA de propósito, e é o custo desta decisão: enquanto incuba, um derivado que
    perdesse governance/ ou security/ inteiros também não seria acusado aqui. Restringi-la exigiria
    saber quais artefatos a ingestão cria, e ingest.yaml só declara isso para parte deles. O
    contrapeso é o teste negativo: promovido o lifecycle, artefato ausente volta a reprovar.
    """
    projeto = (project_doc or {}).get("project") or {}
    incubando = projeto.get("kind") == "derived" and projeto.get("lifecycle") == "incubating"

    for stage in (stages_doc or {}).get("stages", []):
        sid = stage.get("id", "?")

        for artifact in stage.get("artifacts", []):
            if not hl.resolve_glob(artifact) and not incubando:
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


INGEST = "harness/pipeline/ingest.yaml"


def check_ingest_pipeline(findings: Findings, errors: Errors) -> None:
    """As fases da ingestão têm fiscal resolvível, ordem sã, e não escrevem no alvo.

    Reusa _enforcer_resolves de propósito: um pipeline que escreve metadado precisa da MESMA
    régua de "fiscal resolve" que as etapas do projeto, e duas implementações da mesma pergunta
    divergem com o tempo. A checagem de outputs é a que carrega a decisão do ADR-008: a ingestão
    lê o alvo e escreve no derivado, então output apontando para workspace/ seria escrita no
    material de terceiro disfarçada de metadado local.
    """
    if not hl.rel_exists(INGEST):
        return
    try:
        doc = hl.read_yaml(INGEST) or {}
    except HarnessError as exc:
        errors.err(str(exc))
        return

    vistos: set[int] = set()
    for phase in doc.get("phases", []):
        pid = phase.get("id", "?")

        ordem = phase.get("order")
        if ordem in vistos:
            findings.add(
                key=f"INGEST-ORDER-{pid}", origin="ingest_pipeline", severity="medium",
                risk="RISK-INGEST-002", location=INGEST,
                summary=f"{pid}: ordem {ordem} duplicada — duas fases no mesmo passo tornam "
                        f"'a fase anterior já rodou' uma afirmação sem sentido.",
            )
        vistos.add(ordem)

        agente = f"harness/agents/{phase.get('agent', '')}/AGENT.md"
        if not hl.rel_exists(agente):
            findings.add(
                key=f"INGEST-AGENT-{pid}", origin="ingest_pipeline", severity="high",
                risk="RISK-INGEST-002", location=agente,
                summary=f"{pid} cita o agente '{phase.get('agent')}', que não tem contrato em "
                        f"harness/agents/ — fase sem dono declarado.",
            )

        ok, why = _enforcer_resolves({**phase["fiscal"], "kind": phase["fiscal"]["kind"]}, errors)
        if not ok:
            findings.add(
                key=f"INGEST-FISCAL-{pid}", origin="ingest_pipeline", severity="high",
                risk="RISK-INGEST-002", location=phase["fiscal"].get("ref"),
                summary=f"{pid}: fiscal não resolve — {why}. Fase de ingestão sem fiscal é "
                        f"metadado escrito por máquina que ninguém confere.",
            )

        for out in phase.get("outputs", []):
            if out.startswith("workspace/"):
                findings.add(
                    key=f"INGEST-WRITE-{pid}", origin="ingest_pipeline", severity="critical",
                    risk="RISK-INGEST-002", location=out,
                    summary=f"{pid} declara escrita em '{out}': a ingestão lê o alvo e escreve no "
                            f"derivado. Escrever no alvo faria o vigia hospedar-se no vigiado.",
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


PROPOSALS_DIR = "harness/change-proposals"
CONFORMANCE_REVIEW = "governance/conformance-review.yaml"
PRIVACY_REVIEW = "governance/privacy-review.yaml"


def check_cp_lifecycle(findings: Findings, errors: Errors) -> None:
    """O ciclo de vida declarado é coerente com o que o repositório mostra (CP-022).

    O que este fiscal NÃO faz: resolver `capabilities_affected` contra o metadado de hoje. Essa
    isenção é do CP-018 e continua valendo — uma proposta fala do dia em que foi escrita. O que
    entra aqui é o que NÃO envelhece: a coerência entre `status` e os campos de prova, que descreve
    a própria proposta e não o mundo em volta dela.

    A resolução do review contra a API é de ci/verify_approval.py, e a separação é a de sempre:
    aqui não há rede, então aqui não pode haver a conclusão que só a rede sustenta.
    """
    d = hl.REPO / PROPOSALS_DIR
    if not d.exists():
        return
    for path in sorted(d.glob("*.yaml")):
        rel = hl.rel(path)
        try:
            doc = hl.read_yaml(rel) or {}
        except HarnessError as exc:
            errors.err(str(exc))
            continue
        proposta = doc.get("proposal") or {}
        if doc.get("schema_version") != "1.1":
            continue  # não-retroatividade: as 1.0 não têm ciclo, e reescrevê-las apagaria registro
        cid = proposta.get("id", "?")
        status = proposta.get("status")
        alto = (proposta.get("risk_assessment") or {}).get("level") in ("high", "critical")

        if status == "executed" and not (proposta.get("executed_in") or {}).get("pr_number"):
            findings.add(
                key=f"{cid}-EXECUTED-SEM-PR", origin="cp_lifecycle", severity="high",
                risk="RISK-CHANGE-001", location=rel,
                summary=f"{cid} declara 'executed' sem executed_in.pr_number — uma proposta "
                        f"executada em lugar nenhum é uma decisão sem rastro.",
            )
        if status == "executed" and alto:
            if not (proposta.get("executed_in") or {}).get("merge_commit_sha"):
                findings.add(
                    key=f"{cid}-EXECUTED-SEM-MERGE", origin="cp_lifecycle", severity="high",
                    risk="RISK-CHANGE-001", location=rel,
                    summary=f"{cid} é de risco alto e declara execução sem merge commit — número "
                            f"de PR é ponteiro para uma conversa, merge commit é o conteúdo.",
                )
            if not proposta.get("approved_by"):
                findings.add(
                    key=f"{cid}-SEM-APROVADOR", origin="cp_lifecycle", severity="critical",
                    risk="RISK-CHANGE-001", location=rel,
                    summary=f"{cid} executou mudança de risco alto sem nomear aprovador — "
                            f"'aval necessário' não é 'aval houve'.",
                )
        aprovacao = proposta.get("approved_by") or {}
        executado = proposta.get("executed_in") or {}
        if aprovacao and executado and aprovacao.get("pr_number") != executado.get("pr_number"):
            findings.add(
                key=f"{cid}-APROVACAO-DE-OUTRO-PR", origin="cp_lifecycle", severity="critical",
                risk="RISK-CHANGE-001", location=rel,
                summary=f"{cid}: o aval cita o PR #{aprovacao.get('pr_number')} e a execução cita "
                        f"o PR #{executado.get('pr_number')} — o aval precisa ser DESTE merge.",
            )
        if aprovacao and not alto:
            continue
        if status in ("draft", "approved") and executado:
            findings.add(
                key=f"{cid}-NAO-EXECUTADA-COM-MERGE", origin="cp_lifecycle", severity="medium",
                risk="RISK-CHANGE-001", location=rel,
                summary=f"{cid} declara execução em '{status}' — ou a proposta foi executada e o "
                        f"status mente, ou o campo foi preenchido antes do fato.",
            )


def _alvos_de_consumo(risk_doc: dict, adr_doc: dict) -> dict[str, set[str]]:
    """Os destinos possíveis de um achado, lidos dos artefatos REAIS — nunca de lista duplicada."""
    cps = set()
    d = hl.REPO / PROPOSALS_DIR
    if d.exists():
        for path in d.glob("*.yaml"):
            try:
                p = (hl.read_yaml(hl.rel(path)) or {}).get("proposal") or {}
            except HarnessError:
                continue
            if p.get("id"):
                cps.add(p["id"])
    return {
        "change_proposal": cps,
        "risk": {r.get("id") for r in (risk_doc or {}).get("risks", [])},
        "adr": {a.get("id") for a in (adr_doc or {}).get("adrs", [])},
    }


def check_decision_chain(risk_doc: dict, adr_doc: dict, findings: Findings, errors: Errors) -> None:
    """Achado encaminhado aponta para o artefato que de fato o consumiu (CP-023).

    É a tradução declarativa dos "tipos lineares" cuja FORMA foi rejeitada na primeira rodada
    (R-02) e cuja INTENÇÃO foi aprovada: um parecer não some sem deixar consequência. Hoje um
    achado declara `disposition: change_proposal` e um `ref` de texto livre — "isto virou uma
    proposta" é uma afirmação que ninguém confere, e um achado encaminhado para o vazio é
    indistinguível de um achado tratado.

    `accepted` continua sendo saída legítima (e continua exigindo rationale, pelo schema). O que
    se recusa é o achado que sai do parecer sem NENHUMA decisão resolvível.
    """
    alvos = _alvos_de_consumo(risk_doc, adr_doc)

    def resolve(consumo: dict, origem: str, ident: str, arquivo: str) -> None:
        kind, ref = consumo.get("kind"), consumo.get("ref")
        conhecidos = alvos.get(kind)
        if conhecidos is None:
            findings.add(
                key=f"CHAIN-{ident}-KIND", origin="decision_chain", severity="high",
                risk="RISK-DECISION-001", location=arquivo,
                summary=f"{ident}: consumed_by.kind '{kind}' não é um destino que este fiscal "
                        f"saiba resolver.",
            )
            return
        if ref not in conhecidos:
            findings.add(
                key=f"CHAIN-{ident}", origin="decision_chain", severity="high",
                risk="RISK-DECISION-001", location=arquivo,
                summary=f"{ident} declara ter sido consumido por {ref}, que não existe entre os "
                        f"{kind} do repositório — encaminhar para o vazio é indistinguível de "
                        f"tratar, e é como um achado morre.",
                remediation=f"Criar o {kind} que consome o achado, ou mudar a disposição para "
                            f"'accepted' com rationale.",
            )

    try:
        conformidade = hl.read_yaml(CONFORMANCE_REVIEW) if hl.rel_exists(CONFORMANCE_REVIEW) else {}
        privacidade = hl.read_yaml(PRIVACY_REVIEW) if hl.rel_exists(PRIVACY_REVIEW) else {}
    except HarnessError as exc:
        errors.err(str(exc))
        return

    for achado in ((conformidade or {}).get("review") or {}).get("findings", []) or []:
        ident = achado.get("id", "?")
        if achado.get("disposition") in ("change_proposal", "risk_entry"):
            consumo = achado.get("consumed_by")
            if not consumo:
                findings.add(
                    key=f"CHAIN-{ident}-VAZIO", origin="decision_chain", severity="high",
                    risk="RISK-DECISION-001", location=CONFORMANCE_REVIEW,
                    summary=f"{ident} foi encaminhado ({achado.get('disposition')}) e não diz para "
                            f"onde — achado encaminhado sem destino é achado esquecido com outro nome.",
                )
            else:
                resolve(consumo, "conformance", ident, CONFORMANCE_REVIEW)

    for issue in ((privacidade or {}).get("review") or {}).get("issues", []) or []:
        ident = issue.get("id", "?")
        consumo = issue.get("consumed_by")
        # 'accepted' é decisão declarada (e o schema já exige risco em P0/P1); o que se cobra aqui
        # é o issue crítico que segue aberto ou mitigado sem dizer QUAL trabalho o resolve.
        if issue.get("severity") in ("P0", "P1") and issue.get("status") != "accepted":
            if not consumo:
                findings.add(
                    key=f"CHAIN-{ident}-VAZIO", origin="decision_chain", severity="high",
                    risk="RISK-DECISION-001", location=PRIVACY_REVIEW,
                    summary=f"{ident} é {issue.get('severity')} e não declara consumo — um issue "
                            f"crítico com risco registrado e nenhum trabalho é um risco gerido "
                            f"apenas no papel.",
                )
            else:
                resolve(consumo, "privacy", ident, PRIVACY_REVIEW)
        elif consumo:
            resolve(consumo, "privacy", ident, PRIVACY_REVIEW)


# --------------------------------------------------------------------------------------
# Os três amortecedores de mudança (CP-029)
#
# A harness não propaga uma mudança grande automaticamente — ela expõe o que ficou inconsistente
# e deixa a decisão para quem decide. O que torna isso VIÁVEL são três propriedades do desenho, e
# até aqui elas funcionavam por bom gosto, não por garantia. Propriedade emergente sem asserção é
# propriedade que o primeiro refactor grande destrói sem avisar — e destrói exatamente durante o
# pivô, que é quando ela é mais necessária.
# --------------------------------------------------------------------------------------

# Vocabulário de referência cruzada. Os nomes são lidos aqui porque é o que "campo de referência"
# significa neste repositório; o que NÃO se duplica é a lista de onde eles aparecem — isso vem dos
# schemas reais.
CAMPOS_DE_REFERENCIA = {
    "capability", "satisfies", "implements", "depends_on", "governed_by", "risk",
    "related_capabilities", "related_components", "related_risks", "supersedes",
    "owning_component", "residual_risk",
}

# `target` FICA DE FORA, e a exclusão é um achado desta CP, não um esquecimento. A palavra
# significa três coisas diferentes neste repositório: o repositório governado (project.yaml), o
# artefato que uma ameaça vigia (threat-model), e o VALOR-META de uma métrica (vision). Só o
# segundo é referência cruzada. Um fiscal genérico que tratasse os três como iguais acusaria
# `target: 0.85` de "referenciar por caminho" — e fiscal que acusa o legítimo é desligado por quem
# tem trabalho a fazer, que é o pior desfecho possível para uma trava. A cobertura do caso real
# vem do pattern declarado no próprio threat-model.schema.json.

# Campos que são CAMINHO por desenho, e a distinção é do ADR-009: eles apontam para evidência em
# arquivo, não para artefato com identidade. Tratá-los como campos de ID inverteria a decisão.
CAMPOS_DE_CAMINHO = {
    "verified_by", "validated_by", "tested_by", "source_paths", "test_paths", "business_rules",
    "paths_affected", "file", "path", "ref", "location", "document", "manifest_path",
}

_ID_PATTERN = re.compile(r"\^(CAP|CMP|REQ|RULE|UI|MET|ADR|RISK|CP|THREAT|STAGE|DEP|CONF|PRIV)-")
_PARECE_CAMINHO = re.compile(r"[/\\]|\.(ya?ml|json|md|py|txt)$")


def _valor_do_campo(node: dict) -> dict:
    """Onde mora a restrição de um campo: nele mesmo, ou nos itens se for lista."""
    return node.get("items") if node.get("type") == "array" and isinstance(node.get("items"), dict) else node


def check_references_by_id(findings: Findings, errors: Errors) -> None:
    """Amortecedor (i): arestas por ID, nunca por caminho.

    `CAP-001` continua sendo `CAP-001` onde quer que o arquivo passe a morar — é o que faz
    reorganização estrutural não quebrar referência, e é metade do que torna um pivô barato.

    A garantia útil não é "os dados de hoje usam IDs": os schemas já recusam o contrário NOS CAMPOS
    QUE EXISTEM. É que todo campo de referência TENHA padrão de ID, inclusive os que ainda não
    foram escritos. Um schema novo com `satisfies` de string livre passa hoje e não passa daqui em
    diante.

    A metade dos dados roda também, e é redundante de propósito: se algum schema estiver frouxo por
    caminho que este fiscal não previu, valor com forma de caminho num campo de ID ainda reprova.
    """
    for schema_file in sorted((hl.REPO / "harness" / "schemas").glob("*.json")):
        try:
            schema = hl.read_json(hl.rel(schema_file))
        except HarnessError as exc:
            errors.err(str(exc))
            continue

        def visitar(node, caminho: str) -> None:
            if isinstance(node, list):
                for i, item in enumerate(node):
                    visitar(item, f"{caminho}/{i}")
                return
            if not isinstance(node, dict):
                return
            for nome, sub in (node.get("properties") or {}).items():
                if nome in CAMPOS_DE_REFERENCIA and nome not in CAMPOS_DE_CAMINHO:
                    alvo = _valor_do_campo(sub) if isinstance(sub, dict) else {}
                    tem_id = bool(_ID_PATTERN.search(str(alvo.get("pattern", "")))) or "enum" in alvo
                    # `$ref`/`oneOf` delegam a restrição; objetos aninhados a carregam dentro.
                    delega = any(k in alvo for k in ("$ref", "oneOf", "anyOf", "properties"))
                    if not tem_id and not delega:
                        findings.add(
                            key=f"REF-BY-ID-{schema_file.name}-{nome}", origin="change_buffer",
                            severity="high", risk="RISK-META-001",
                            location=f"{hl.rel(schema_file)}{caminho}/properties/{nome}",
                            summary=f"{schema_file.name}: o campo de referência '{nome}' não "
                                    f"constrange a um padrão de ID — sem isso ele aceita caminho "
                                    f"de arquivo, e a aresta passa a quebrar em toda reorganização.",
                            remediation="Declarar o pattern do ID (ex.: ^CAP-[A-Z0-9-]+$), ou "
                                        "acrescentar o campo a CAMPOS_DE_CAMINHO se ele for "
                                        "mesmo um caminho por desenho.",
                        )
                visitar(sub, f"{caminho}/properties/{nome}")
            for chave in ("items", "then", "else", "if", "allOf", "anyOf", "oneOf", "$defs"):
                if chave in node:
                    visitar(node[chave], f"{caminho}/{chave}")

        visitar(schema, "")

    # Metade dos dados: valor com forma de caminho onde deveria haver ID.
    for path in sorted(hl.REPO.rglob("*.yaml")):
        rel = hl.rel(path)
        if hl.is_excluded(rel) or rel.startswith(("workspace/", "tests/")):
            continue
        try:
            doc = hl.read_yaml(rel)
        except HarnessError:
            continue

        def varrer(node, onde: str) -> None:
            if isinstance(node, dict):
                for nome, valor in node.items():
                    if nome in CAMPOS_DE_REFERENCIA and nome not in CAMPOS_DE_CAMINHO:
                        for v in (valor if isinstance(valor, list) else [valor]):
                            if isinstance(v, str) and _PARECE_CAMINHO.search(v):
                                findings.add(
                                    key=f"REF-PATH-{rel}-{nome}-{v}", origin="change_buffer",
                                    severity="high", risk="RISK-META-001", location=rel,
                                    summary=f"{rel}: o campo '{nome}' referencia por CAMINHO "
                                            f"({v!r}) onde deveria referenciar por ID — a aresta "
                                            f"quebra assim que o arquivo mudar de lugar.",
                                )
                    varrer(valor, f"{onde}/{nome}")
            elif isinstance(node, list):
                for item in node:
                    varrer(item, onde)

        varrer(doc, rel)


# Onde a maturidade vive, e o que ela condiciona. Derivado dos artefatos reais: cada entrada diz
# arquivo, chave da coleção e quais campos a maturidade concreta passa a exigir.
COLECOES_COM_MATURIDADE = [
    ("business/capabilities.yaml", "capabilities", ("source_paths", "test_paths")),
    ("architecture/components.yaml", "components", ("source_paths",)),
]


def check_maturity_gates(findings: Findings, errors: Errors) -> None:
    """Amortecedor (ii): maturidade permite transição honesta.

    Rebaixar uma capacidade para `proposed` durante um pivô isenta-a de código e teste, e o
    repositório fica verde DIZENDO A VERDADE ("em transição") em vez de vermelho por semanas ou
    verde mentindo. É o que torna um pivô fatiável: a fatia 1 rebaixa e fica verde-honesta, as
    seguintes elevam de volta conforme entregam.

    Genérico de propósito. O que já existia vivia dentro de `check_capabilities`, específico de uma
    coleção; assim, a próxima coleção com maturidade nasce coberta em vez de esperar alguém lembrar
    de escrever um `check_*` para ela.
    """
    for rel, chave, exigidos in COLECOES_COM_MATURIDADE:
        if not hl.rel_exists(rel):
            continue
        try:
            doc = hl.read_yaml(rel) or {}
        except HarnessError as exc:
            errors.err(str(exc))
            continue
        for item in doc.get(chave, []) or []:
            iid = item.get("id", "?")
            status = item.get("status")
            if status in hl.CONCRETE:
                for campo in exigidos:
                    if not item.get(campo):
                        findings.add(
                            key=f"MATURITY-{iid}-{campo}", origin="change_buffer", severity="high",
                            risk="RISK-CONF-001", location=rel,
                            summary=f"{iid} está '{status}' e não declara {campo} — maturidade "
                                    f"concreta sem evidência é a afirmação que o gate existe para "
                                    f"impedir.",
                            remediation=f"Declarar {campo}, ou rebaixar para 'proposed' enquanto "
                                        f"a implementação não existe — verde honesto vale mais "
                                        f"que verde que mente.",
                        )
            elif status == "proposed":
                # O par positivo do gate, e ele é a metade que costuma ser esquecida: o fiscal
                # precisa DEIXAR PASSAR o item em transição, senão a saída honesta fica fechada e
                # a única forma de ficar verde volta a ser mentir.
                continue


# O cabeçalho canônico. Um formato só, porque duas convenções para a mesma promessa é como a
# terceira nasce sem nenhuma — e foi exatamente o que se encontrou ao escrever este fiscal.
GENERATED_HEADER = "<!-- GENERATED: não editar; rodar {script} -->"
_GENERATED_RX = re.compile(r"^<!-- GENERATED: não editar; rodar ([^\s]+) -->", re.MULTILINE)


def geradores_declarados() -> dict[str, str]:
    """Mapa documento→script, DERIVADO de cada script em ci/ que declara escrever um docs/*.md.

    Nunca uma lista mantida à mão. Sem isso, um gerador novo nasceria fora da cobertura — que é
    precisamente o modo de falha que ci/alignment_report.py já exibia, por não casar o glob
    `generate_*.py` com que esta regra foi enunciada.
    """
    mapa: dict[str, str] = {}
    for script in sorted((hl.REPO / "ci").glob("*.py")):
        texto = script.read_text(encoding="utf-8", errors="replace")
        for alvo in re.findall(r'["\'](docs/[A-Za-z0-9_.\-]+\.md)["\']', texto):
            mapa[alvo] = hl.rel(script)
        # generate_graph.py monta o caminho por partes: REPO / "docs" / "metadata-graph.md"
        for pasta, arquivo in re.findall(r'"(docs)"\s*/\s*"([A-Za-z0-9_.\-]+\.md)"', texto):
            mapa[f"{pasta}/{arquivo}"] = hl.rel(script)
    return mapa


def check_derived_vs_source(findings: Findings) -> None:
    """Amortecedor (iii): fonte de verdade se edita com revisão; derivado se regenera sem licença.

    A fronteira é cirúrgica e precisa ser LEGÍVEL no próprio arquivo: quem abre um documento
    derivado tem que saber, na primeira linha, que editar ali é trabalho perdido — e qual comando
    o regenera. Sem isso, a edição manual acontece de boa-fé e o `--check` do CI a contradiz
    depois, na hora mais cara.
    """
    for doc, script in sorted(geradores_declarados().items()):
        if not hl.rel_exists(doc):
            findings.add(
                key=f"DERIVED-MISSING-{doc}", origin="change_buffer", severity="medium",
                risk="RISK-META-001", location=doc,
                summary=f"{script} declara gerar '{doc}', que não existe — regerar com "
                        f"`python {script}`.",
            )
            continue
        cabecalho = _GENERATED_RX.search(hl.read_text(doc))
        if not cabecalho:
            findings.add(
                key=f"DERIVED-NO-HEADER-{doc}", origin="change_buffer", severity="high",
                risk="RISK-META-001", location=doc,
                summary=f"'{doc}' é gerado por {script} e não carrega o cabeçalho canônico — "
                        f"quem o abrir não tem como saber que editar ali é trabalho perdido.",
                remediation=f"Emitir na primeira linha: {GENERATED_HEADER.format(script=script)}",
            )
        elif cabecalho.group(1) != script:
            findings.add(
                key=f"DERIVED-WRONG-SCRIPT-{doc}", origin="change_buffer", severity="medium",
                risk="RISK-META-001", location=doc,
                summary=f"'{doc}' diz ser regerado por {cabecalho.group(1)}, e quem o escreve é "
                        f"{script} — o comando do cabeçalho manda o leitor ao lugar errado.",
            )


def check_external_attestation(harness_doc: dict, risk_doc: dict, findings: Findings) -> None:
    """A camada externa da trava: ligada e válida, ou desligada e VISÍVEL (CP-024).

    Os dois estados são legítimos; o que não é legítimo é o silêncio. Com `enabled: false`, este
    fiscal emite um achado informativo a cada execução, citando o risco datado — a lacuna fica
    barulhenta em vez de sumir. Com `enabled: true`, o atestado passa a ser exigido: ausente,
    expirado ou de emissor não declarado bloqueia.

    O achado de "desligado" é `info` de propósito. Bloquear aqui seria inverter a decisão da CP-024
    — que reconhece a ausência da autoridade externa como risco ACEITO com data, não como
    divergência a corrigir hoje. Elevá-lo a bloqueante tornaria o repositório vermelho por uma
    condição que ninguém neste repositório consegue satisfazer, e vermelho permanente é como um
    fiscal é ignorado.
    """
    import verify_protection as vp
    from datetime import datetime, timezone

    externo = vp.estado_da_auditoria_externa(harness_doc)
    riscos = {r.get("id"): r for r in (risk_doc or {}).get("risks", [])}
    risco_id = externo.get("accepted_risk")

    if not externo.get("enabled"):
        risco = riscos.get(risco_id)
        if not risco:
            findings.add(
                key="EXT-AUDIT-RISCO-AUSENTE", origin="external_audit", severity="high",
                risk="RISK-META-002", location=HARNESS_YAML,
                summary=f"A auditoria externa está desligada e o risco aceito declarado "
                        f"({risco_id!r}) não existe no registro — desligar a camada externa "
                        f"precisa custar um risco datado a alguém.",
            )
            return
        if not risco.get("due"):
            findings.add(
                key="EXT-AUDIT-RISCO-SEM-DATA", origin="external_audit", severity="high",
                risk=risco_id, location=RISK_REGISTER,
                summary=f"{risco_id} cobre a ausência da autoridade externa e não tem `due` — "
                        f"risco aceito sem data é risco esquecido (princípio (g)).",
            )
            return
        findings.add(
            key="EXT-AUDIT-DESLIGADA", origin="external_audit", severity="info",
            risk=risco_id, location=HARNESS_YAML,
            summary=f"Autoridade externa desligada: a verificação de proteção mora no mesmo "
                    f"repositório que fiscaliza, e um PR privilegiado remove o passo e a asserção "
                    f"juntos. Risco aceito até {risco.get('due')}.",
            evidence=externo.get("justification", "").strip()[:300],
        )
        return

    # Ligada: o atestado passa a ser exigido, e ausente vale o mesmo que expirado.
    caminho = externo.get("attestation_path", "")
    if not hl.rel_exists(caminho):
        findings.add(
            key="EXT-AUDIT-SEM-ATESTADO", origin="external_audit", severity="critical",
            risk="RISK-META-002", location=caminho,
            summary=f"A auditoria externa está LIGADA e não há atestado em '{caminho}' — "
                    f"ausência de atestado bloqueia release e merge em caminho protegido.",
        )
        return
    try:
        doc = hl.read_json(caminho)
    except HarnessError as exc:
        findings.add(
            key="EXT-AUDIT-ATESTADO-ILEGIVEL", origin="external_audit", severity="critical",
            risk="RISK-META-002", location=caminho, summary=str(exc),
        )
        return
    for msg in hl.schema_errors(caminho, "protection-attestation.schema.json", doc):
        findings.add(
            key="EXT-AUDIT-ATESTADO-INVALIDO", origin="external_audit", severity="critical",
            risk="RISK-META-002", location=caminho, summary=msg,
        )
        return
    # EMISSOR. Achado PRÓPRIO, e sem `return`: um atestado pode estar expirado E ter sido escrito
    # por quem não devia, e são dois problemas com duas reações. "Não consegui verificar", "isto
    # envelheceu" e "alguém escreveu isto à mão" nunca compartilham código de saída nesta casa —
    # colapsá-los economizaria linhas e destruiria a informação que diz para onde olhar.
    autorizado = externo.get("authorized_issuer") or {}
    emissor = (doc.get("attestation") or {}).get("issuer") or {}
    if autorizado and (emissor.get("identity") != autorizado.get("identity")
                       or emissor.get("kind") != autorizado.get("kind")):
        findings.add(
            key="EXT-AUDIT-EMISSOR-NAO-AUTORIZADO", origin="external_audit", severity="critical",
            risk="RISK-META-002", location=caminho,
            summary=f"O atestado declara ter sido emitido por "
                    f"{emissor.get('identity')!r} ({emissor.get('kind')}) e a autoridade declarada "
                    f"é {autorizado.get('identity')!r} ({autorizado.get('kind')}). Atestado de "
                    f"emissor não declarado é indistinguível de atestado escrito à mão por quem "
                    f"tem direito de merge — que é exatamente quem teria motivo para escrevê-lo.",
            remediation="Conferir se o atestado veio da autoridade externa declarada em "
                        "harness.yaml:external_audit.authorized_issuer. Se a autoridade mudou, a "
                        "mudança é decisão declarada, não ajuste de campo.",
        )

    expira = (doc.get("attestation") or {}).get("expires_at")
    try:
        quando = datetime.fromisoformat(str(expira).replace("Z", "+00:00"))
    except ValueError:
        quando = None
    if quando and quando < datetime.now(timezone.utc):
        findings.add(
            key="EXT-AUDIT-ATESTADO-EXPIRADO", origin="external_audit", severity="critical",
            risk="RISK-META-002", location=caminho,
            summary=f"Atestado de proteção expirou em {expira} — atestado sem validade seria "
                    f"carimbo eterno sobre configuração que pode ter mudado; expirado bloqueia "
                    f"do mesmo modo que ausente.",
        )


AGENTS_DIR = "harness/agents"
PROMPTS_DIR = "harness/prompts"
_TEMPLATE_RX = re.compile(r"`(harness/prompts/[A-Za-z0-9_.-]+\.md)`")


def check_agent_prompt_pairing(findings: Findings) -> None:
    """Correspondência BIDIRECIONAL entre contrato de agente e template de tarefa (CP-027).

    As duas direções pegam coisas diferentes, e é por isso que ambas existem:

      agente sem template → a fronteira declarada no AGENT.md não é repetida onde ela seria lida,
      e quem for invocar o agente improvisa a instrução. Improvisar a instrução de um agente que
      pode editar metadado é onde a fronteira deixa de valer.

      template sem agente → AGENTE-FANTASMA: instrução viva para um papel que não existe mais,
      invocável, com proibições que ninguém mantém.

    A correspondência é lida do `inputs.md` de cada agente, NUNCA do nome do arquivo. O nome não
    serve e a evidência está no repositório: `review-task.md` é do `reviewer`, `lgpd-task.md` é do
    `privacy`. Uma convenção de nome inventada aqui obrigaria a renomear artefatos que outros
    fiscais e ADRs já citam — trocar a realidade para caber na regra, em vez do contrário.
    """
    base = hl.REPO / AGENTS_DIR
    prompts = hl.REPO / PROMPTS_DIR
    if not base.exists() or not prompts.exists():
        return

    declarados: dict[str, str] = {}
    for agente in sorted(p for p in base.iterdir() if p.is_dir()):
        nome = agente.name
        inputs = agente / "inputs.md"
        if not inputs.exists():
            findings.add(
                key=f"AGENT-NO-INPUTS-{nome}", origin="agent_pairing", severity="medium",
                risk="RISK-META-001", location=f"{AGENTS_DIR}/{nome}",
                summary=f"O agente '{nome}' não declara inputs.md — sem ele não há onde declarar "
                        f"qual template a harness lhe passa.",
            )
            continue
        alvos = _TEMPLATE_RX.findall(inputs.read_text(encoding="utf-8"))
        alvos = [a for a in alvos if "*" not in a]
        if not alvos:
            findings.add(
                key=f"AGENT-NO-TEMPLATE-{nome}", origin="agent_pairing", severity="high",
                risk="RISK-META-001", location=f"{AGENTS_DIR}/{nome}/inputs.md",
                summary=f"O agente '{nome}' não declara template de tarefa — a fronteira do "
                        f"AGENT.md não é repetida onde ela seria lida, e quem o invocar improvisa "
                        f"a instrução.",
                remediation=f"Criar {PROMPTS_DIR}/{nome}-task.md e citá-lo em inputs.md.",
            )
            continue
        for alvo in alvos:
            if not hl.rel_exists(alvo):
                findings.add(
                    key=f"AGENT-TEMPLATE-MISSING-{nome}", origin="agent_pairing", severity="high",
                    risk="RISK-META-001", location=alvo,
                    summary=f"O agente '{nome}' declara o template '{alvo}', que não existe.",
                )
            else:
                declarados[alvo] = nome

    for arquivo in sorted(prompts.glob("*.md")):
        rel = hl.rel(arquivo)
        if rel not in declarados:
            findings.add(
                key=f"PROMPT-GHOST-{arquivo.stem}", origin="agent_pairing", severity="high",
                risk="RISK-META-001", location=rel,
                summary=f"'{rel}' não é reivindicado por agente algum — agente-fantasma: "
                        f"instrução viva para um papel que não existe, invocável, com proibições "
                        f"que ninguém mantém.",
                remediation="Apagar o template, ou declará-lo no inputs.md do agente dono.",
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
    check_assertion_self_match(adr_index, findings, errors)
    check_stage_coverage(stages_doc, findings, errors, project_doc)
    check_repo_partition(stages_doc, findings)
    check_ingest_pipeline(findings, errors)
    check_policy_pointers(findings)
    check_agent_prompt_pairing(findings)
    check_cp_lifecycle(findings, errors)
    check_references_by_id(findings, errors)
    check_maturity_gates(findings, errors)
    check_derived_vs_source(findings)
    check_decision_chain(risk_doc, adr_index, findings, errors)
    check_external_attestation(harness_doc, risk_doc, findings)
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
