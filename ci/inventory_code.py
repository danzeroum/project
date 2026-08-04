#!/usr/bin/env python3
"""Inventário do código real — o insumo da invariante "código sem metadado não existe".

Gerador, não fiscal: como ci/generate_graph.py, ele descreve o repositório e não julga nada. Quem
julga são os check_* de ci/validate_metadata.py, que consomem este inventário in-process — o JSON
em harness/state/ é evidência para leitura humana, nunca dependência de ordem de execução no CI.

De onde vêm as raízes — descobertas e DECLARADAS, jamais presumidas por convenção:

  derivado  project.yaml:target.code_roots / test_roots, sob workspace/target/
  molde     as raízes do próprio molde (src, tests/unit)

Uso:  python ci/inventory_code.py [--check] [--quiet]
Sai:  0 inventariado · 2 não conseguiu inventariar (raiz declarada ausente, arquivo ilegível).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import adapters
import harness_lib as hl
from harness_lib import HarnessError

# REPO é lido de hl a CADA chamada, nunca fixado no import: harness_lib resolve HARNESS_REPO_ROOT
# no momento em que é carregado, e um `from harness_lib import REPO` congelaria a raiz do primeiro
# carregamento. O fiscal passaria a inventariar o repositório anterior — verde por acidente, que é
# o modo de falha mais caro possível aqui.

LAUDO = "harness/state/code-inventory.json"
WORKSPACE = "workspace/target"

# Raízes do próprio molde. NÃO é exceção de alvo (ADR-008-A5): descreve o layout deste
# repositório, que é o que o molde inventaria quando não governa alvo algum.
RAIZES_MOLDE = {"code": ["src"], "test": ["tests/unit"]}


def _roots(project_doc: dict | None) -> tuple[str, list[str], list[str]]:
    """(prefixo, raízes de código, raízes de teste) — tudo relativo ao repositório."""
    target = (project_doc or {}).get("target")
    if not target:
        return "", list(RAIZES_MOLDE["code"]), list(RAIZES_MOLDE["test"])
    return (WORKSPACE + "/",
            [r.strip("/") for r in target.get("code_roots", [])],
            [r.strip("/") for r in target.get("test_roots", [])])


def _files(base: Path) -> list[Path]:
    out = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if hl.is_excluded(p.relative_to(base).as_posix()) or p.name.startswith("."):
            continue
        out.append(p)
    return out


def build(project_doc: dict | None = None) -> dict:
    """Constrói o inventário. Levanta HarnessError quando não consegue inventariar."""
    if project_doc is None:
        project_doc = hl.read_yaml("project.yaml") or {}
    prefixo, code_roots, test_roots = _roots(project_doc)

    # A raiz do inventário é o que resolve os imports: no derivado, o alvo materializado.
    raiz = hl.REPO / prefixo if prefixo else hl.REPO
    if prefixo and not raiz.exists():
        raise HarnessError(
            f"{WORKSPACE} ausente: o alvo não foi materializado — rode python ci/bootstrap.py")

    modulos: list[dict] = []
    adapters_usados: dict[str, dict] = {}

    for tipo, roots in (("code", code_roots), ("test", test_roots)):
        for root in roots:
            base = raiz / root
            if not base.exists():
                raise HarnessError(
                    f"raiz declarada '{root}' não existe em {prefixo or '.'} — "
                    f"raiz que não casa nada torna a invariante verdadeira por vacuidade")
            for path in _files(base):
                adapter = adapters.for_path(path)
                try:
                    mod = adapter.analyze(path, raiz)
                except HarnessError:
                    raise
                except Exception as exc:  # noqa: BLE001 - ilegível é exit 2, nunca exit 0
                    raise HarnessError(f"[{adapter.name}] {hl.rel(path)}: {exc}") from exc

                # A aritmética de completude, verificada a CADA arquivo. É exit 2 e não achado
                # porque a conta que não fecha não diz "o repositório está errado" — diz que o
                # inventário perdeu um especificador pelo caminho, e um inventário com resíduo
                # invisível não pode fundamentar a invariante do código órfão. Foi assim que 84
                # arestas internas de um alvo real sumiram sem que nada acusasse.
                if not mod.conta_fecha():
                    raise HarnessError(
                        f"[{adapter.name}] {hl.rel(path)}: a partição de imports não fecha — "
                        f"{mod.total_especificadores} especificador(es) lidos, "
                        f"{len(mod.internos_crus)} internos + {len(mod.externos)} externos + "
                        f"{len(mod.unresolved)} unresolved. A diferença é aresta engolida.")

                item = {
                    "path": prefixo + mod.path,
                    "language": mod.language,
                    "kind": tipo,
                    "adapter": adapter.name,
                    "exposes": mod.exposes,
                    "imports": [prefixo + i for i in mod.imports],
                    "unresolved": mod.unresolved,
                }
                modulos.append(item)
                info = adapters_usados.setdefault(
                    adapter.name,
                    {"arquivos": 0, "especificadores": 0, "arestas": 0, "externos": 0,
                     "unresolved": 0, "semantico": adapter.semantico, **(
                        {"nao_lido": adapter.nao_lido} if adapter.nao_lido else {})},
                )
                info["arquivos"] += 1
                info["especificadores"] += mod.total_especificadores
                info["arestas"] += len(mod.internos_crus)
                info["externos"] += len(mod.externos)
                info["unresolved"] += len(mod.unresolved)

    return {
        "schema_version": "1.0",
        "raiz": prefixo or ".",
        "code_roots": code_roots,
        "test_roots": test_roots,
        "adapters": adapters_usados,
        "modulos": sorted(modulos, key=lambda m: m["path"]),
    }


_CACHE: dict | None = None


def cached(project_doc: dict | None = None) -> dict:
    """Memoizado por processo: validate_metadata roda quatro checks sobre o mesmo inventário."""
    global _CACHE
    if _CACHE is None:
        _CACHE = build(project_doc)
    return _CACHE


def reset_cache() -> None:
    global _CACHE
    _CACHE = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventário do código real.")
    parser.add_argument("--check", action="store_true", help="não escreve; só verifica que dá para inventariar")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        doc = build()
    except HarnessError as exc:
        print(f"✗ inventário: {exc}", file=sys.stderr)
        return 2

    if not args.check:
        out = hl.REPO / LAUDO
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"✓ inventário: {len(doc['modulos'])} arquivo(s) em {doc['raiz']}")
        for nome, info in sorted(doc["adapters"].items()):
            print(f"  · {nome}: {info['arquivos']} arquivo(s) · "
                  f"{info['especificadores']} import(s) = {info['arestas']} interno(s) + "
                  f"{info['externos']} externo(s) + {info['unresolved']} unresolved")
            if not info["semantico"]:
                print(f"      não lido: {info.get('nao_lido', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
