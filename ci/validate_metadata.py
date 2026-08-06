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

from jsonschema import Draft202012Validator

import harness_lib as hl
from harness_lib import CONCRETE, REPO, SCHEMAS, HarnessError, rel_exists

# (arquivo de metadado, schema) — schema None = só validação de YAML + invariantes de cabeçalho.
DOCS = [
    ("project.yaml", "project.schema.json"),
    ("target.lock", "target-lock.schema.json"),
    ("harness/pipeline/ingest.yaml", "ingest-pipeline.schema.json"),
    ("governance/conformance-review.yaml", "conformance-review.schema.json"),
    ("security/threat-model.yaml", "threat-model.schema.json"),
    ("security/dependencies.yaml", "dependencies.schema.json"),
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


RELEASES_DIR = "harness/releases"


def check_release_manifests() -> None:
    """Todo manifesto de release é válido e o nome do arquivo deriva da tag que ele declara.

    A igualdade nome↔tag é o que impede duas releases de compartilharem arquivo — e a segunda
    venceria em silêncio, que é a forma de falha mais cara possível numa raiz de confiança. O
    resto da cadeia (tag → commit, manifesto na árvore, o commit de release não muda mais nada)
    exige git ou rede e por isso vive em ci/mold_release.py::verify_chain: um fiscal que faz I/O
    confunde "a cadeia quebrou" com "não consegui olhar", e as duas conclusões pedem reações
    opostas (princípio (h)).
    """
    import mold_release

    releases = REPO / RELEASES_DIR
    if not releases.exists():
        return
    for path in sorted(releases.glob("*.manifest.json")):
        rel = hl.rel(path)
        try:
            doc = hl.read_json(rel)
        except HarnessError as exc:
            err(str(exc))
            continue
        check_header_invariants(rel, doc)
        validate_structural(rel, "release-manifest.schema.json", doc)
        tag = (doc or {}).get("release", {}).get("tag")
        if tag and rel != mold_release.manifest_path_for(tag):
            err(f"[release] {rel} declara a tag {tag!r}, cujo manifesto é "
                f"{mold_release.manifest_path_for(tag)} — nome de arquivo que não deriva da tag "
                f"permite duas releases no mesmo caminho")


def check_mold_release(project_doc: dict | None, lock_doc: dict | None) -> None:
    """A âncora do molde é coerente CONSIGO MESMA — os elos que não dependem de rede.

    O schema já exige o bloco no derivado e o proíbe no molde. O que sobra para cá é a coerência
    interna: o caminho do manifesto deriva da tag declarada. Parece redundante com o pattern do
    schema, e não é: o schema garante a FORMA do caminho, não que ele seja o caminho DAQUELA tag.
    Um lock declarando tag v1.2.0 e manifest_path de v9.9.9 passa no schema e mente na cadeia.
    """
    import mold_release

    mr = (lock_doc or {}).get("mold_release")
    if not mr:
        return
    tag = mr.get("tag")
    esperado = mold_release.manifest_path_for(tag) if tag else None
    if esperado and mr.get("manifest_path") != esperado:
        err(f"[molde] target.lock: mold_release declara a tag {tag!r} e o manifesto "
            f"{mr.get('manifest_path')!r} — o caminho é derivado da tag ({esperado}), nunca escolhido")


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


# Coleções cujo piso saiu do schema e passou a viver aqui (CP-017). O mapa arquivo→coleção é
# local; o mapa arquivo→FASE é lido de harness/pipeline/ingest.yaml, que já o declara — a mensagem
# de erro diz qual fase deveria ter preenchido, sem uma segunda fonte de verdade para derivar.
COLECOES_COM_PISO = [
    ("business/capabilities.yaml", "capabilities"),
    ("architecture/components.yaml", "components"),
    ("architecture/interfaces.yaml", "interfaces"),
    ("business/requirements/backlog.yaml", "items"),
]


def _fase_que_preenche(rel: str) -> str:
    """Qual fase de ingestão declara este arquivo como output. Vazio se nenhuma."""
    try:
        pipeline = hl.read_yaml("harness/pipeline/ingest.yaml")
    except (HarnessError, OSError):  # pragma: no cover - o próprio DOCS já reprova o ilegível
        return ""
    for fase in (pipeline or {}).get("phases", []):
        if rel in (fase.get("outputs") or []):
            return fase.get("id", "")
    return ""


def check_collection_floor(loaded: dict[str, dict], project_doc: dict | None) -> None:
    """Coleção vazia só enquanto a ingestão não terminou — e "terminou" é declarado, não inferido.

    O piso de um item saiu dos schemas (CP-017) porque um schema valida UM documento: ele não
    enxerga o project.yaml e não pode responder "este repositório já foi ingerido?". Fingir que
    enxerga produziria a única coisa pior que a pergunta errada — a resposta errada com cara de
    estrutural.

    Aqui a pergunta tem contexto. O molde carrega sempre o negócio de exemplo, então o piso vale
    para ele sem ressalva. No derivado, `lifecycle: incubating` é a declaração de que a ingestão
    está em curso, e é o que suspende o piso; qualquer outro valor volta a cobrá-lo. A permissão
    expira por um ato declarado — promover o lifecycle — e não por dedução a partir do próprio
    arquivo que se está julgando, que seria circular: "a fase acabou porque o arquivo está cheio"
    não reprova arquivo vazio nenhum.

    O risco que esta função existe para impedir é o oposto do que a motivou: sem ela, tirar o piso
    do schema deixaria um repositório declarar zero de tudo, passar em tudo, e afirmar cobertura
    sobre conjunto vazio.
    """
    projeto = (project_doc or {}).get("project") or {}
    kind, lifecycle = projeto.get("kind"), projeto.get("lifecycle")
    if kind == "derived" and lifecycle == "incubating":
        return
    motivo = ("molde: o negócio de exemplo é o substrato das asserções"
              if kind != "derived" else f"derivado com lifecycle {lifecycle!r}, não 'incubating'")
    for rel, chave in COLECOES_COM_PISO:
        doc = loaded.get(rel)
        if doc is None or (doc.get(chave) or []):
            continue
        fase = _fase_que_preenche(rel)
        onde = f" — {fase} é a fase que a preenche" if fase else ""
        err(f"[piso] {rel}: '{chave}' está vazia e o piso se aplica ({motivo}){onde}. "
            f"Coleção vazia só é aceitável em derivado ainda em ingestão")


def declared_roots(project_doc: dict | None) -> tuple[list[str], list[str]]:
    """Raízes de código e de teste, com o prefixo do workspace já aplicado no derivado.

    Substitui o prefixo literal 'src/' que estava cravado aqui. Não é afrouxamento: o prefixo
    passa a vir do que o repositório DECLARA em project.yaml em vez de uma convenção embutida no
    fiscal — e sem isso o metadado de um derivado, que aponta para workspace/target/, não valida
    no próprio CI que deveria protegê-lo.
    """
    import inventory_code

    prefixo, code_roots, test_roots = inventory_code._roots(project_doc)
    return ([f"{prefixo}{r}/" for r in code_roots], [f"{prefixo}{r}/" for r in test_roots])


def check_capabilities(doc: dict | None, code_roots: list[str], test_roots: list[str]) -> dict[str, dict]:
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
                elif not any(p.startswith(r) for r in code_roots):
                    err(f"[I4] {cid}: source_path fora das raízes declaradas {code_roots}: {p}")
            for p in tsts:
                if not rel_exists(p):
                    err(f"[I5] {cid}: test_path inexistente: {p}")
                elif not any(p.startswith(r) for r in test_roots):
                    err(f"[I5] {cid}: test_path fora das raízes declaradas {test_roots}: {p}")
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


# Onde a ingestão pode escrever itens com proveniência, e sob qual chave eles vivem.
DERIVAVEIS = [
    ("business/capabilities.yaml", "capabilities"),
    ("architecture/components.yaml", "components"),
    ("architecture/interfaces.yaml", "interfaces"),
    ("design/ui-surfaces.yaml", "ui_surfaces"),
    ("business/requirements/backlog.yaml", "items"),
    ("governance/risk-register.yaml", "risks"),
    ("security/threat-model.yaml", "threats"),
]

# Campos que só um humano preenche. A ingestão escreve o sentinela; promover é substituí-lo.
PENDENTE = "pending_judgment"


def check_derived_from(loaded: dict[str, dict], project_doc: dict | None,
                       lock_doc: dict | None) -> None:
    """Proveniência ancorada: de onde no alvo, e em QUE commit.

    A igualdade de SHA é o ponto. Sem ela, "este metadado descreve o alvo" degrada em silêncio
    para "descrevia o alvo em algum momento" — o mesmo modo de falha que target.lock resolve, uma
    camada acima. Um item cujo derived_from aponta para um SHA antigo não é um detalhe de
    procedência: é um metadado que fala de um sistema que já mudou.
    """
    target = (project_doc or {}).get("target") or {}
    lock_sha = (lock_doc or {}).get("target_sha")

    for rel, chave in DERIVAVEIS:
        for item in (loaded.get(rel) or {}).get(chave, []) or []:
            proc = item.get("derived_from")
            if not proc:
                continue
            iid = item.get("id", "?")
            if not target:
                err(f"[proveniência] {rel}:{iid} declara derived_from, mas este repositório não "
                    f"governa alvo algum — proveniência sem alvo é ficção")
                continue
            if proc.get("repo") != target.get("repo"):
                err(f"[proveniência] {rel}:{iid}: derived_from.repo {proc.get('repo')!r} não é o "
                    f"alvo declarado ({target.get('repo')!r})")
            if proc.get("sha") != lock_sha:
                err(f"[proveniência] {rel}:{iid}: derived_from.sha não casa target.lock — o item "
                    f"descreve o alvo em {str(proc.get('sha'))[:12]} e o lock está em "
                    f"{str(lock_sha)[:12]}; reingerir ou avançar o lock por change-proposal")
            alvo = f"workspace/target/{proc.get('path', '').lstrip('/')}"
            if rel_exists("workspace/target") and not rel_exists(alvo):
                err(f"[proveniência] {rel}:{iid}: derived_from.path não existe no alvo: "
                    f"{proc.get('path')!r}")


def check_pending_judgment(loaded: dict[str, dict]) -> None:
    """pending_judgment vive só em documento derivado. Promover é substituí-lo.

    É o inverso do 'to-be-assessed' que o CLAUDE.md proíbe: aquele é um campo aberto que nenhum
    fiscal consegue reprovar, e por isso a pendência vira permanente sem nunca aparecer como
    falha. Este é reprovável por construção — o documento não pode se declarar fonte de verdade
    enquanto carregar um julgamento que ninguém fez.
    """
    for rel, chave in DERIVAVEIS:
        doc = loaded.get(rel)
        if not doc:
            continue
        promovido = doc.get("source_of_truth") is True
        for item in doc.get(chave, []) or []:
            campos = sorted(k for k, v in item.items() if v == PENDENTE)
            if campos and promovido:
                err(f"[julgamento] {rel}:{item.get('id', '?')} está num documento "
                    f"source_of_truth:true com {', '.join(campos)}={PENDENTE} — "
                    f"promover é substituir o sentinela por julgamento, não declarar o documento "
                    f"pronto com ele dentro")


def check_threat_model(doc: dict | None, comp_ids: set[str], ifc_ids: set[str],
                       ui_ids: set[str], risk_ids: set[str],
                       stage_ids: set[str] | None = None) -> None:
    """Toda ameaça vigia algo que existe e deixa um residual rastreável.

    O schema já garante que existe ao menos uma mitigação e um residual_risk. Aqui se cobra que os
    alvos RESOLVEM: ameaça contra componente inexistente é trava que não encontra o que vigiar —
    quebrada, não satisfeita (ADR-006) — e residual apontando para risco inexistente devolve a
    ameaça ao limbo de onde o residual deveria tirá-la.

    As ETAPAS entram no conjunto de alvos possíveis (CP-019) porque parte do que se ameaça é a
    própria máquina de governar, e ela não é componente de negócio. Antes disso, uma ameaça ao
    harness só passava apontando para um CMP-* arbitrário que por acaso existisse — o fiscal ficava
    satisfeito sem que a declaração dissesse nada verdadeiro, que é conformidade por vacuidade
    dentro do fiscal que existe para impedi-la. Ampliar o conjunto não afrouxa a trava: é o que
    permite exercê-la com um alvo real.
    """
    if not doc:
        return
    conhecidos = comp_ids | ifc_ids | ui_ids | (stage_ids or set())
    for ameaca in doc.get("threats", []):
        tid = ameaca.get("id", "?")
        if ameaca.get("target") not in conhecidos:
            err(f"[ameaça] {tid}: target {ameaca.get('target')} não existe em components, "
                f"interfaces, ui-surfaces nem nas etapas de harness/stages.yaml")
        if ameaca.get("residual_risk") not in risk_ids:
            err(f"[ameaça] {tid}: residual_risk {ameaca.get('residual_risk')} não existe no "
                f"risk-register — ameaça sem residual rastreável volta ao limbo")
        for mit in ameaca.get("mitigations", []):
            if mit.get("kind") == "local_path" and not rel_exists(mit.get("ref", "")):
                err(f"[ameaça] {tid}: mitigação local_path inexistente: {mit.get('ref')}")


# Uma linha de `dependencies` do pyproject, em QUALQUER das formas que a PEP 508 admite:
#
#     "pyyaml>=6"                                    faixa
#     "webqa-suite==1.0.0"                           pin exato
#     "httpx[http2]>=0.27"                           com extras
#     "cockpit-harness @ git+https://host/r@<sha>"   REFERÊNCIA DIRETA
#
# A última foi acrescentada pela CP-039, e a ausência dela invertia o propósito deste fiscal. O
# regex anterior aceitava só `[<>=!~]` depois do nome, então a forma mais perigosa que existe —
# código arbitrário de um host qualquer, sem índice e sem assinatura — era a única invisível ao
# inventário de supply chain. Quem declarasse a dependência E a inventariasse levava achado de
# "entrada morta"; quem não a inventariasse não levava achado nenhum. O fiscal punia a honestidade
# e premiava o silêncio, que é o pior estado possível para um fiscal.
#
# Medido no primeiro derivado que extraiu a própria harness e passou a consumi-la por pin de SHA.
_DEP_PYPROJECT = re.compile(
    r'^\s*"([A-Za-z0-9][A-Za-z0-9._-]*)'   # o nome do pacote, que é o que o inventário casa
    r'\s*(?:\[[^\]]*\])?'                  # extras opcionais: [http2], [standard]
    r'\s*(?:[<>=!~@].*)?"'                 # faixa, pin, marcador — ou ` @ url` da referência direta
    r'\s*,?\s*$'
)


def _declaradas() -> dict[str, str]:
    """Dependências que este repositório declara, e onde. Leitura textual e deliberada.

    Sem tomllib nem resolver de ambiente: o que interessa é o que o repositório DECLARA, não o que
    está instalado na máquina de quem roda. Um inventário conferido contra o site-packages local
    passaria ou reprovaria conforme o computador, que é o oposto de fiscalizável.
    """
    achadas: dict[str, str] = {}
    if rel_exists("pyproject.toml"):
        for linha in read_text_lines("pyproject.toml"):
            m = _DEP_PYPROJECT.match(linha)
            if m:
                achadas[m.group(1).lower()] = "pyproject.toml"
    if rel_exists("requirements-qa.txt"):
        for linha in read_text_lines("requirements-qa.txt"):
            m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==", linha)
            if m:
                achadas[m.group(1).lower()] = "requirements-qa.txt"
    return achadas


def read_text_lines(rel: str) -> list[str]:
    return hl.read_text(rel).splitlines()


def check_dependency_inventory(doc: dict | None) -> None:
    """Dependência declarada e não inventariada é achado — a direção reversa da Fase E."""
    if not doc:
        return
    inventariadas = {d.get("name", "").lower(): d for d in doc.get("dependencies", [])}
    declaradas = _declaradas()

    for nome, onde in sorted(declaradas.items()):
        if nome not in inventariadas:
            err(f"[dependência] '{nome}' é declarada em {onde} e não está em "
                f"security/dependencies.yaml — dependência que entra sem passar pelo inventário "
                f"é superfície de supply chain que ninguém revisou")
        elif inventariadas[nome].get("declared_in") != onde:
            err(f"[dependência] '{nome}': inventário diz {inventariadas[nome].get('declared_in')!r} "
                f"e ela é declarada em {onde!r}")

    for nome, item in sorted(inventariadas.items()):
        if nome not in declaradas:
            err(f"[dependência] '{nome}' está inventariada e não é declarada em lugar nenhum — "
                f"entrada morta faz o inventário parecer mais completo do que é")
        if not rel_exists(item.get("declared_in", "")):
            err(f"[dependência] '{nome}': declared_in aponta para arquivo inexistente: "
                f"{item.get('declared_in')}")


def _inventory(project_doc: dict | None) -> dict | None:
    """O inventário do código real, in-process. Sem ele os quatro checks abaixo não rodam —
    e não rodar é exit 2 ('o fiscal não conseguiu fiscalizar'), nunca exit 0."""
    import inventory_code

    try:
        return inventory_code.cached(project_doc)
    except HarnessError as exc:
        err(f"[inventário] {exc}")
        return None


def check_orphan_code(inv: dict | None, components_doc: dict | None) -> None:
    """A invariante: todo arquivo de código pertence a exatamente um componente.

    É a direção que faltava. Os demais checks perguntam "esse metadado aponta para código real?";
    este pergunta "esse código real é apontado por algum metadado?". Sem ele, implementação nova
    entra no repositório em silêncio e a governança afirma uma cobertura que nunca teve.
    """
    if not inv or not components_doc:
        return
    donos: dict[str, list[str]] = {}
    for comp in components_doc.get("components", []):
        for p in comp.get("source_paths", []):
            donos.setdefault(p, []).append(comp.get("id", "?"))

    isentos = _isencoes(components_doc)

    for mod in inv["modulos"]:
        if mod["kind"] != "code":
            continue
        path = mod["path"]
        if path in isentos:
            isentos[path] += 1
            continue
        if path not in donos:
            err(f"[órfão] '{path}' não pertence a nenhum componente nem a uma isenção declarada — "
                f"acrescente-o a source_paths de um CMP-* ou declare a isenção com justificativa "
                f"em architecture/components.yaml:exemptions")
        elif len(donos[path]) > 1:
            err(f"[órfão] '{path}' pertence a mais de um componente ({', '.join(donos[path])}) — "
                f"dono ambíguo é dono nenhum")


_ISENCOES_VISTAS: dict[str, int] = {}


def _isencoes(components_doc: dict | None) -> dict[str, int]:
    """Contador de isenções, COMPARTILHADO entre as duas invariantes de órfão.

    Antes da CP-039 ele era local a `check_orphan_code`, e era essa localidade o defeito: a isenção
    só existia para um dos dois lados. Compartilhar permite que a mesma declaração cubra um
    `conftest.py` sem que a checagem de isenção morta acuse a que casou do outro lado.
    """
    _ISENCOES_VISTAS.clear()
    for entry in (components_doc or {}).get("exemptions", []):
        _ISENCOES_VISTAS[entry["path"]] = 0
    return _ISENCOES_VISTAS


def check_dead_exemptions() -> None:
    """Isenção que não casa NADA — nem código, nem teste. Roda DEPOIS das duas invariantes.

    Separada delas pela CP-039, e a razão é o defeito que a versão anterior tinha: enquanto só
    `check_orphan_code` contava, declarar a isenção de um arquivo de APOIO DE TESTE produzia achado
    de isenção morta E zero redução no contador de teste órfão. Líquido: +1 por declaração honesta.
    A trava recusava a declaração que ela própria prescrevia como remédio — medido no primeiro
    derivado, que tentou declarar dez arquivos de apoio e levou dez achados por isso.
    """
    for path, casou in _ISENCOES_VISTAS.items():
        if not casou:
            err(f"[órfão] isenção morta em components.yaml: '{path}' não casa arquivo de código "
                f"nem de teste — isenção que não protege nada só serve para a cobertura parecer "
                f"fechada")


def check_orphan_tests(inv: dict | None, components_doc: dict | None,
                       caps: dict[str, dict], backlog_doc: dict | None) -> None:
    """Teste que ninguém declara é teste que ninguém sabe que existe — e cuja remoção não dói.

    CONSULTA `exemptions` desde a CP-039, pelo mesmo motivo que `check_orphan_code` sempre
    consultou: fixture, stub e conftest não exercitam nada, e vinculá-los a um componente para
    calar o fiscal seria inventar que exercitam. A isenção continua custando justificativa de 40
    caracteres e continua morrendo se não casar arquivo algum — o que muda é ela passar a EXISTIR
    para este lado.
    """
    if not inv:
        return
    isentos = _ISENCOES_VISTAS
    referenciados: set[str] = set()
    for comp in (components_doc or {}).get("components", []):
        referenciados.update(comp.get("tested_by", []))
    for cap in caps.values():
        referenciados.update(cap.get("test_paths", []))
    for item in (backlog_doc or {}).get("items", []):
        referenciados.update(item.get("validated_by", []))

    for mod in inv["modulos"]:
        if mod["kind"] != "test":
            continue
        path = mod["path"]
        if path in isentos:
            isentos[path] += 1
            continue
        if path not in referenciados:
            err(f"[teste órfão] '{path}' não é referenciado por tested_by, test_paths nem "
                f"validated_by, nem consta de components.yaml:exemptions — a evidência existe e "
                f"nenhum metadado a reivindica")


def check_declared_dependencies(inv: dict | None, components_doc: dict | None) -> None:
    """Dependência real ⊆ declarada.

    Import não declarado ACUSA: é acoplamento que existe e que nenhuma decisão registrou.
    depends_on sem import é só aviso — pode ser dependência legítima que o adapter não enxerga
    (alias de monorepo, injeção em runtime), e reprovar aí produziria pressão para apagar
    declarações verdadeiras, que é o oposto do que se quer.
    """
    if not inv or not components_doc:
        return
    de_arquivo: dict[str, str] = {}
    for comp in components_doc.get("components", []):
        for p in comp.get("source_paths", []):
            de_arquivo[p] = comp.get("id", "?")
    declarado = {c.get("id"): set(c.get("depends_on", [])) for c in components_doc.get("components", [])}

    real: dict[str, set[str]] = {cid: set() for cid in declarado}
    for mod in inv["modulos"]:
        origem = de_arquivo.get(mod["path"])
        if origem is None:
            continue
        for alvo_path in mod["imports"]:
            destino = de_arquivo.get(alvo_path)
            if destino and destino != origem:
                real[origem].add(destino)

    for cid, alvos in real.items():
        for nao_declarado in sorted(alvos - declarado[cid]):
            err(f"[dependência] {cid} importa código de {nao_declarado} e não o declara em "
                f"depends_on — acoplamento que existe e que nenhuma decisão registrou")


def check_exposes(inv: dict | None, components_doc: dict | None) -> None:
    """Símbolo declarado em exposes existe no código.

    Só onde o adapter é semântico: para uma linguagem lida pelo fallback, exigir isso reprovaria
    por ignorância do fiscal, não por erro do repositório. O que o fallback não leu está declarado
    no laudo do inventário — o silêncio é que está proibido.
    """
    if not inv or not components_doc:
        return
    semanticos = {n for n, i in inv["adapters"].items() if i["semantico"]}
    reais: dict[str, set[str]] = {}
    lido: set[str] = set()
    for mod in inv["modulos"]:
        reais[mod["path"]] = set(mod["exposes"])
        if mod["adapter"] in semanticos:
            lido.add(mod["path"])

    for comp in components_doc.get("components", []):
        paths = [p for p in comp.get("source_paths", []) if p in lido]
        if not paths:
            continue
        disponiveis = set().union(*(reais[p] for p in paths))
        for sym in comp.get("exposes", []):
            if sym not in disponiveis:
                err(f"[exposes] {comp.get('id', '?')}: declara '{sym}', que não existe em "
                    f"{', '.join(paths)}")


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


def check_business_rules(caps: dict[str, dict], test_roots: list[str]) -> dict[str, str]:
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
                    elif not any(p.startswith(r) for r in test_roots):
                        err(f"[regra] {rule.get('id', '?')}: verified_by fora das raízes "
                            f"declaradas {test_roots}: {p}")
    return rule_caps


def metric_ids(vision_doc: dict | None) -> set[str]:
    if not vision_doc:
        return set()
    return {m.get("id") for m in vision_doc.get("product", {}).get("success_metrics", [])}


def check_backlog(doc: dict | None, caps: dict[str, dict], risk_ids: set[str],
                  test_roots: list[str],
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
            elif not any(t.startswith(r) for r in test_roots):
                err(f"[REQ] {rid}: validated_by fora das raízes declaradas {test_roots}: {t}")
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


def check_change_proposals() -> None:
    """A proposta é conferida na FORMA, nunca contra o metadado de hoje (CP-018).

    Uma change-proposal fala do dia em que foi escrita; o metadado fala de agora. Resolver os IDs
    dela contra o presente faz as duas divergirem por construção — e divergirem exatamente quando
    a proposta FUNCIONA. Medido: executar a proposta que remove um negócio de exemplo invalida
    todas as propostas que o citavam, inclusive ela mesma. Uma proposta que reprova por ter sido
    cumprida não é um registro com defeito; é o fiscal fazendo a pergunta errada.

    O que continua cobrado é o que não envelhece: schema, invariantes de cabeçalho e a forma dos
    IDs, que o próprio schema trava por pattern.

    TROCA DE GUARDA, e ela é deliberada. O que este fiscal pegava era um ID de capacidade,
    componente ou risco DIGITADO ERRADO no momento da escrita. Isso passa a ser pego pela revisão
    humana do pull request — a única camada que consegue distinguir "ID errado" de "ID que existia
    quando isto foi escrito". A checagem não sumiu por descuido: ela mudou de lugar, e este
    parágrafo existe para que a ausência não seja lida como esquecimento e reintroduzida.

    A isenção acaba aqui. Metadado VIVO — capabilities, components, ADRs, threat-model, backlog,
    ui-surfaces — segue com resolução de ID cobrada, porque descreve o que É, não o que foi
    decidido.
    """
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


def main(argv: list[str] | None = None) -> int:
    # Zerado na entrada: validate_all.py chama este main in-process, junto dos demais fiscais.
    errors.clear()
    # O inventário é memoizado por processo para os quatro checks; entre execuções (o hook Stop,
    # os testes de mordida) ele precisa ser recalculado, senão o fiscal julgaria o repositório
    # anterior — que é exatamente o tipo de verde por acidente que este repositório recusa.
    import inventory_code
    inventory_code.reset_cache()
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
    check_mold_release(loaded.get("project.yaml"), loaded.get("target.lock"))
    check_release_manifests()
    check_target_roots(loaded.get("project.yaml"))
    check_collection_floor(loaded, loaded.get("project.yaml"))
    check_derived_from(loaded, loaded.get("project.yaml"), loaded.get("target.lock"))
    check_pending_judgment(loaded)
    backlog_doc = loaded.get("business/requirements/backlog.yaml") or {}
    req_items = {i.get("id"): i for i in backlog_doc.get("items", [])}
    code_roots, test_roots = declared_roots(loaded.get("project.yaml"))
    caps = check_capabilities(loaded.get("business/capabilities.yaml"), code_roots, test_roots)
    components_doc = loaded.get("architecture/components.yaml")
    comp_ids = check_components(components_doc, caps, req_items)

    # A direção que faltava: não "o metadado aponta para código real?", mas "o código real é
    # apontado por algum metadado?". O inventário é construído in-process — o JSON em
    # harness/state/ é evidência, nunca dependência de ordem de execução no CI.
    inv = _inventory(loaded.get("project.yaml"))
    check_orphan_code(inv, components_doc)
    check_orphan_tests(inv, components_doc, caps, backlog_doc)
    check_dead_exemptions()   # depois das duas: a isenção pode casar de qualquer um dos lados
    check_declared_dependencies(inv, components_doc)
    check_exposes(inv, components_doc)
    risk_ids = check_risk_controls(loaded.get("governance/risk-register.yaml"))
    check_interfaces(loaded.get("architecture/interfaces.yaml"), loaded.get("architecture/components.yaml"))
    req_caps = {rid: item.get("capability") for rid, item in req_items.items()}
    check_ui_surfaces(loaded.get("design/ui-surfaces.yaml"), caps, req_caps)
    rule_caps = check_business_rules(caps, test_roots)
    metrics = metric_ids(loaded.get("business/vision.yaml"))
    check_backlog(loaded.get("business/requirements/backlog.yaml"), caps, risk_ids,
                  test_roots, metrics, rule_caps)
    check_adr_index(loaded.get("architecture/adr/index.yaml"), caps, comp_ids, risk_ids)
    check_adr_assertion_refs(loaded.get("architecture/adr/index.yaml"), risk_ids)
    check_data_inventory(loaded.get("governance/data-inventory.yaml"), comp_ids)
    check_privacy_review(loaded.get("governance/privacy-review.yaml"), risk_ids)
    ifc_ids = {i.get("id") for i in (loaded.get("architecture/interfaces.yaml") or {}).get("interfaces", [])}
    ui_ids = {u.get("id") for u in (loaded.get("design/ui-surfaces.yaml") or {}).get("ui_surfaces", [])}
    stage_ids = {s.get("id") for s in (loaded.get("harness/stages.yaml") or {}).get("stages", [])}
    check_threat_model(loaded.get("security/threat-model.yaml"), comp_ids, ifc_ids, ui_ids,
                       risk_ids, stage_ids)
    check_dependency_inventory(loaded.get("security/dependencies.yaml"))
    check_change_proposals()

    if errors:
        print(f"✗ validação de metadados falhou ({len(errors)} inconsistência(s)):\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("✓ metadados coerentes: schema, paths, IDs e controles casam com o repositório.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
