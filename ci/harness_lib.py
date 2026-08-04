#!/usr/bin/env python3
"""Base compartilhada dos fiscais de CI. Não é fiscal — é a ferramenta que eles usam.

Aqui mora só o que MAIS DE UM fiscal precisa: leitura de metadado, validação estrutural,
resolução de glob, caminhamento de AST, hash de escopo, acumuladores e emissão de laudo.
A resolução de IDs (CAP/REQ/CMP/RISK/ADR) NÃO mora aqui — é trabalho exclusivo de
ci/validate_metadata.py, e duplicá-la criaria duas respostas para a mesma pergunta.

REPO respeita HARNESS_REPO_ROOT. É o que permite ao CI copiar o repositório, injetar uma
violação na cópia e provar que o fiscal morde — sem sujar a árvore de trabalho.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator

REPO = Path(os.environ.get("HARNESS_REPO_ROOT") or Path(__file__).resolve().parent.parent).resolve()
SCHEMAS = REPO / "harness" / "schemas"

# Maturidades em que código e teste DEVEM existir fisicamente (compartilhado com validate_metadata).
CONCRETE = {"implemented", "verified"}

# Diretórios que nenhum fiscal percorre: ruído de ferramenta ou evidência efêmera.
EXCLUDED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist", ".eggs",
}
# workspace/ é o código do ALVO materializado por ci/bootstrap.py — material efêmero de terceiro,
# pela mesma razão que a evidência da harness já está aqui. Sem esta linha, check_repo_partition
# exigiria que cada arquivo do alvo pertencesse a uma etapa DESTE repositório, e a partição do
# derivado passaria a depender do tamanho do projeto que ele governa.
EXCLUDED_PREFIXES = ("harness/runs/", "harness/reports/", "harness/state/", "workspace/")


class HarnessError(Exception):
    """O fiscal não conseguiu fiscalizar. Vira exit 2 — nunca exit 0."""


# --------------------------------------------------------------------------------------
# Leitura de metadado
# --------------------------------------------------------------------------------------

def rel_exists(rel: str) -> bool:
    return (REPO / rel).exists()


def read_text(rel: str) -> str:
    path = REPO / rel
    if not path.exists():
        raise HarnessError(f"[falta] arquivo ausente: {rel}")
    return path.read_text(encoding="utf-8")


def read_yaml(rel: str) -> Any:
    """Lê e desserializa. Ausência e YAML inválido são erro de fiscalização, não achado."""
    try:
        return yaml.safe_load(read_text(rel))
    except yaml.YAMLError as exc:
        raise HarnessError(f"[yaml] {rel}: {exc}") from exc


def read_json(rel: str) -> Any:
    try:
        return json.loads(read_text(rel))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"[json] {rel}: {exc}") from exc


_VALIDATORS: dict[str, Draft202012Validator] = {}


def validator_for(schema_name: str) -> Draft202012Validator:
    """Memoizado: os 15 schemas são compilados uma vez por processo, não por documento.

    É o que mantém o hook Stop barato o bastante para rodar a cada turno.
    """
    if schema_name not in _VALIDATORS:
        path = SCHEMAS / schema_name
        if not path.exists():
            raise HarnessError(f"[schema] schema ausente: harness/schemas/{schema_name}")
        _VALIDATORS[schema_name] = Draft202012Validator(
            json.loads(path.read_text(encoding="utf-8"))
        )
    return _VALIDATORS[schema_name]


def schema_errors(rel: str, schema_name: str, doc: Any) -> list[str]:
    out = []
    for e in sorted(validator_for(schema_name).iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in e.path) or "(raiz)"
        out.append(f"[estrutural] {rel} em '{loc}': {e.message}")
    return out


def header_invariant_errors(rel: str, doc: Any) -> list[str]:
    """I11: source_of_truth:true exige generated_from:null, e vice-versa."""
    if not isinstance(doc, dict):
        return []
    sot, gen = doc.get("source_of_truth"), doc.get("generated_from")
    if sot is True and gen is not None:
        return [f"[I11] {rel}: source_of_truth:true exige generated_from:null"]
    if sot is False and not gen:
        return [f"[I11] {rel}: source_of_truth:false exige generated_from não-vazio"]
    return []


def exact_pin(rel: str = "requirements-qa.txt") -> tuple[str | None, list[str]]:
    """I2: o pin do padrão mora em um lugar só, e com == (sem faixa)."""
    path = REPO / rel
    if not path.exists():
        return None, [f"[falta] {rel} ausente — o pin do padrão é obrigatório"]
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*webqa-suite==([^\s#]+)", line)
        if m:
            return m.group(1), []
    return None, [f"[I2] {rel}: webqa-suite deve estar pinado com == (sem faixa)"]


# --------------------------------------------------------------------------------------
# Caminhos
# --------------------------------------------------------------------------------------

def is_excluded(rel: str) -> bool:
    """Ruído de ferramenta ou evidência efêmera: nenhum fiscal percorre.

    `.egg-info` casa por sufixo porque o nome carrega o do pacote (`project.egg-info`) — enumerar
    nomes possíveis faria a exclusão depender do nome do projeto, e o inventário passaria a contar
    resíduo de build como código do negócio no primeiro alvo com outro nome.
    """
    parts = Path(rel).parts
    return (any(p in EXCLUDED_DIRS or p.endswith(".egg-info") for p in parts)
            or rel.startswith(EXCLUDED_PREFIXES))


_is_excluded = is_excluded  # compatibilidade interna


def resolve_glob(pattern: str) -> list[Path]:
    """Resolve um glob relativo ao repo. Um caminho literal de diretório casa a si mesmo.

    Ordenado para que dois runs no mesmo commit produzam o mesmo laudo, byte a byte.
    """
    if not any(ch in pattern for ch in "*?["):
        target = REPO / pattern
        return [target] if target.exists() else []
    return sorted(
        p for p in REPO.glob(pattern)
        if not _is_excluded(p.relative_to(REPO).as_posix())
    )


def walk_files() -> list[Path]:
    """Todo arquivo versionável do repositório — a base da partição por etapa."""
    out = []
    for p in REPO.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO).as_posix()
        if _is_excluded(rel):
            continue
        out.append(p)
    return sorted(out)


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


# --------------------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------------------

_AST_CACHE: dict[tuple[str, float], ast.Module] = {}


def parse_module(path: Path) -> ast.Module:
    """Cacheado por (path, mtime): asserções de import e varredura de PII compartilham o parse."""
    key = (str(path), path.stat().st_mtime)
    if key not in _AST_CACHE:
        try:
            _AST_CACHE[key] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise HarnessError(f"[ast] {rel(path)}: não parseia ({exc}) — não é 'conforme'") from exc
    return _AST_CACHE[key]


def module_name(path: Path) -> str:
    """src/project/pricing.py -> project.pricing (sobe enquanto houver __init__.py)."""
    parts = [] if path.stem == "__init__" else [path.stem]
    d = path.parent
    while (d / "__init__.py").exists():
        parts.insert(0, d.name)
        d = d.parent
    return ".".join(parts)


def _resolve_relative(mod_name: str, level: int, mod: str | None) -> str:
    pkg = mod_name.rsplit(".", 1)[0] if "." in mod_name else ""
    parts = pkg.split(".") if pkg else []
    if level > 1:
        parts = parts[: max(0, len(parts) - (level - 1))]
    base = ".".join(parts)
    return f"{base}.{mod}" if (base and mod) else (mod or base)


def _dotted(node: ast.Attribute) -> str | None:
    parts = []
    cur: ast.expr = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    return ".".join(reversed(parts))


def module_symbols(path: Path) -> set[str]:
    """Símbolos que o módulo importa OU usa por atributo, em nome qualificado.

    Duas passadas de propósito. Sem a segunda, `import project.ports` seguido de
    `project.ports.CatalogoEmMemoria()` escaparia de um import_forbidden — que é
    exatamente a violação que o ADR-005 quer impedir.
    """
    tree = parse_module(path)
    mod_name = module_name(path)
    syms: set[str] = set()
    alias_to_full: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                syms.add(alias.name)
                alias_to_full[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative(mod_name, node.level, node.module)
                if node.level
                else (node.module or "")
            )
            if base:
                syms.add(base)
            for alias in node.names:
                full = f"{base}.{alias.name}" if base else alias.name
                syms.add(full)
                alias_to_full[alias.asname or alias.name] = full

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if not dotted:
                continue
            root = dotted.split(".")[0]
            if root in alias_to_full:
                syms.add(dotted.replace(root, alias_to_full[root], 1))
    return syms


def symbol_hits(symbols: Iterable[str], target: str) -> bool:
    """`project.ports` casa `project.ports.X`; `from x import *` conta como uso do módulo todo."""
    parent = target.rsplit(".", 1)[0]
    for sym in symbols:
        if sym == target or sym.startswith(target + ".") or sym == f"{parent}.*":
            return True
    return False


def defined_names(path: Path) -> set[str]:
    """def/class de topo e de classe — é como enforced_by.symbol é verificado."""
    out: set[str] = set()
    for node in ast.walk(parse_module(path)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


# --------------------------------------------------------------------------------------
# YAML de workflow e JSON Pointer
# --------------------------------------------------------------------------------------

def workflow_step_names(rel_path: str) -> set[str]:
    """Nomes de passos de um workflow — alvo estável, ao contrário de regex posicional."""
    doc = read_yaml(rel_path) or {}
    names: set[str] = set()
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if isinstance(step, dict) and step.get("name"):
                names.add(str(step["name"]))
    return names


class PointerMissing(Exception):
    """Ponteiro não resolve. É ACHADO (a trava sumiu), nunca exceção que derruba o fiscal."""


def json_pointer(doc: Any, pointer: str) -> Any:
    """RFC 6901. '/properties/proposal/properties/change_mode/const'."""
    if pointer in ("", "/"):
        return doc
    if not pointer.startswith("/"):
        raise PointerMissing(f"ponteiro deve começar com '/': {pointer!r}")
    cur = doc
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            if token not in cur:
                raise PointerMissing(f"ponteiro não resolve em {pointer!r}: falta '{token}'")
            cur = cur[token]
        elif isinstance(cur, list):
            try:
                cur = cur[int(token)]
            except (ValueError, IndexError) as exc:
                raise PointerMissing(f"ponteiro não resolve em {pointer!r}: índice '{token}'") from exc
        else:
            raise PointerMissing(f"ponteiro não resolve em {pointer!r}: '{token}' sobre escalar")
    return cur


# --------------------------------------------------------------------------------------
# Hash de escopo (ADR-003: procedência por conteúdo, nunca por data ou git)
# --------------------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_canonical(obj: Any) -> str:
    """Hash de um subconjunto de metadado, independente de formatação e ordem de chaves."""
    return sha256_bytes(
        yaml.safe_dump(obj, sort_keys=True, allow_unicode=True).encode("utf-8")
    )


def fingerprint(parts: Iterable[tuple[str, str]]) -> str:
    """sha256 estável sobre pares (rótulo, hash). Sem data, sem git: reprodutível em clone raso."""
    joined = "\n".join(f"{k}={v}" for k, v in sorted(parts))
    return "sha256:" + sha256_bytes(joined.encode("utf-8"))


# --------------------------------------------------------------------------------------
# Normalização de identificador (varredura de dado pessoal)
# --------------------------------------------------------------------------------------

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenize_identifier(name: str) -> list[str]:
    """'dataNascimento_Titular' -> ['data','nascimento','titular'].

    Casamento por token exato (nunca substring) é o que impede 'phone' de casar 'microphone'.
    """
    ascii_name = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    spaced = _CAMEL.sub(" ", ascii_name)
    return [t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t]


# --------------------------------------------------------------------------------------
# Acumuladores
# --------------------------------------------------------------------------------------

SEVERITIES = ("info", "low", "medium", "high", "critical")


@dataclass
class Findings:
    """Divergências entre o declarado e o real. Qualquer uma derruba o CI (fail-closed).

    A severidade é TRIAGEM — ordena o laudo e informa a decisão humana. Nunca é gate:
    um `fail_on_severity` seria justamente a trava que o vigiado desliga.
    """

    items: list[dict] = field(default_factory=list)

    def add(self, *, key: str, origin: str, severity: str, summary: str,
            adr: str | None = None, assertion: str | None = None, stage: str | None = None,
            risk: str | None = None, location: str | None = None, evidence: str | None = None,
            remediation: str | None = None, lgpd_article: str | None = None,
            pbd_principle: str | None = None) -> None:
        if severity not in SEVERITIES:
            raise HarnessError(f"severidade desconhecida: {severity!r}")
        slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Z0-9-]", "-", key.upper())).strip("-")
        item = {
            "id": "FIND-" + slug,
            "origin": origin,
            "severity": severity,
            "summary": summary,
        }
        for name, value in (
            ("adr", adr), ("assertion", assertion), ("stage", stage), ("risk", risk),
            ("location", location), ("evidence", evidence), ("remediation", remediation),
            ("lgpd_article", lgpd_article), ("pbd_principle", pbd_principle),
        ):
            if value is not None:
                item[name] = value
        self.items.append(item)

    def blocking(self) -> list[dict]:
        return [i for i in self.items if i["severity"] != "info"]

    def sorted_items(self) -> list[dict]:
        return sorted(self.items, key=lambda i: (-SEVERITIES.index(i["severity"]), i["id"]))

    def by_severity(self) -> dict[str, int]:
        return {s: sum(1 for i in self.items if i["severity"] == s) for s in SEVERITIES}


@dataclass
class Errors:
    """O fiscal não conseguiu fiscalizar. Distinto de achado: vira exit 2."""

    items: list[str] = field(default_factory=list)

    def err(self, msg: str) -> None:
        self.items.append(msg)

    def __bool__(self) -> bool:
        return bool(self.items)


# --------------------------------------------------------------------------------------
# Laudo
# --------------------------------------------------------------------------------------

def build_report(*, auditor: str, auditor_version: str, findings: Findings,
                 stages_covered: list[str], generated_at: str,
                 scope_fingerprint: str | None = None,
                 repository: str | None = None, commit: str | None = None) -> dict:
    provenance = {
        "auditor": auditor,
        "auditor_version": auditor_version,
        "repository": repository or os.environ.get("GITHUB_REPOSITORY", "danzeroum/project"),
        "commit": commit or os.environ.get("GITHUB_SHA", "unknown"),
        "generated_at": generated_at,
        "stages_covered": sorted(stages_covered),
    }
    if scope_fingerprint:
        provenance["scope_fingerprint"] = scope_fingerprint
    items = findings.sorted_items()
    return {
        "schema_version": "1.0",
        "provenance": provenance,
        "result": "findings" if findings.blocking() else "ok",
        "summary": {"total": len(items), "by_severity": findings.by_severity()},
        "findings": items,
    }


def emit_report(rel_path: str, doc: dict) -> None:
    """Valida o laudo contra o próprio contrato ANTES de escrever.

    Um fiscal que emitisse laudo fora do schema seria a versão executável de
    'markdown que não morde'. Falha aqui é exit 2, e nenhum arquivo é escrito.
    """
    problems = schema_errors(rel_path, "audit-report.schema.json", doc)
    if problems:
        raise HarnessError(
            "laudo não satisfaz audit-report.schema.json:\n  " + "\n  ".join(problems)
        )
    out = REPO / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
                   encoding="utf-8")


def print_summary(title: str, findings: Findings, errors: Errors, quiet: bool = False) -> None:
    if errors:
        print(f"✗ {title}: o fiscal não conseguiu fiscalizar ({len(errors.items)}):")
        for e in errors.items:
            print(f"  - {e}")
        return
    blocking = findings.blocking()
    if not blocking:
        if not quiet:
            print(f"✓ {title}: o repositório real corresponde ao declarado.")
        return
    print(f"✗ {title}: {len(blocking)} divergência(s) entre o declarado e o real:\n")
    for item in findings.sorted_items():
        if item["severity"] == "info":
            continue
        head = f"  [{item['severity']}] {item['id']}"
        ref = item.get("assertion") or item.get("stage") or item.get("adr")
        if ref:
            head += f" ({ref})"
        print(head)
        print(f"      {item['summary']}")
        if item.get("location"):
            print(f"      onde: {item['location']}")
        if item.get("remediation"):
            print(f"      correção: {item['remediation']}")
