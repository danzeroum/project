#!/usr/bin/env python3
"""Adapter de Python — leitura semântica por AST.

Reusa harness_lib (parse cacheado por mtime, module_name, defined_names): o AST de um arquivo é
lido uma vez por processo e compartilhado com as asserções de import do ADR-005 e com a varredura
de PII do fiscal de LGPD.
"""

from __future__ import annotations

import ast
from pathlib import Path

import harness_lib as hl

from . import Adapter, Modulo, register


def _exposes(path: Path) -> list[str]:
    """Símbolos públicos de topo, em nome qualificado — a forma que components.yaml usa."""
    prefixo = hl.module_name(path)
    tree = hl.parse_module(path)
    nomes: list[str] = []
    for node in tree.body:  # só o topo: método de classe não é símbolo exposto pelo módulo
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.append(node.name)
        elif isinstance(node, ast.Assign):
            nomes += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nomes.append(node.target.id)
    return sorted(f"{prefixo}.{n}" for n in nomes if not n.startswith("_"))


def _imports(path: Path, root: Path) -> list[str]:
    """Arestas para arquivos DENTRO da raiz. Import de biblioteca externa não é aresta interna."""
    por_modulo: dict[str, str] = {}
    for cand in root.rglob("*.py"):
        if hl.is_excluded(cand.relative_to(root).as_posix()):
            continue
        por_modulo[hl.module_name(cand)] = cand.relative_to(root).as_posix()

    alvos: set[str] = set()
    for sym in hl.module_symbols(path):
        # 'project.ports.CatalogoProdutos' casa o módulo 'project.ports'; o mais longo primeiro,
        # para que um pacote não roube a aresta de um submódulo com nome prefixo.
        for mod in sorted(por_modulo, key=len, reverse=True):
            if sym == mod or sym.startswith(mod + "."):
                alvos.add(por_modulo[mod])
                break
    proprio = path.relative_to(root).as_posix()
    return sorted(alvos - {proprio})


def analyze(path: Path, root: Path) -> Modulo:
    return Modulo(
        path=path.relative_to(root).as_posix(),
        language="python",
        exposes=_exposes(path),
        imports=_imports(path, root),
    )


register(Adapter(name="python", extensions=(".py",), semantico=True, analyze=analyze))
