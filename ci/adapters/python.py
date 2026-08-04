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


def _especificadores(path: Path) -> list[str]:
    """Módulos citados por instrução de import, em nome absoluto. Lista CRUA, com duplicatas.

    Só instruções de import — deliberadamente NÃO o uso por atributo que `module_symbols` também
    devolve. Aquele existe para as asserções do ADR-005, onde alcançar o símbolo é o que importa;
    aqui a pergunta é outra, e contar um uso como se fosse import inflaria a conta sem que
    houvesse aresta nova.
    """
    tree = hl.parse_module(path)
    mod_name = hl.module_name(path)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                pkg = mod_name.rsplit(".", 1)[0] if "." in mod_name else ""
                partes = pkg.split(".") if pkg else []
                if node.level > 1:
                    partes = partes[: max(0, len(partes) - (node.level - 1))]
                base = ".".join(partes)
                out.append(f"{base}.{node.module}" if (base and node.module) else (node.module or base))
            else:
                out.append(node.module or "")
    return [e for e in out if e]


def _mapa_de_modulos(root: Path) -> dict[str, str]:
    """nome de módulo -> caminho, para tudo que é Python dentro da raiz."""
    mapa: dict[str, str] = {}
    for cand in root.rglob("*.py"):
        rel = cand.relative_to(root).as_posix()
        if hl.is_excluded(rel):
            continue
        mapa[hl.module_name(cand)] = rel
    return mapa


def _classificar(path: Path, root: Path) -> tuple[list[str], list[str], list[str], int]:
    """(internos crus, externos, unresolved, total). Todo especificador cai em um balde."""
    por_modulo = _mapa_de_modulos(root)
    internos: list[str] = []
    externos: list[str] = []
    unresolved: list[str] = []

    especificadores = _especificadores(path)
    for esp in especificadores:
        alvo = None
        for mod in sorted(por_modulo, key=len, reverse=True):
            if esp == mod or esp.startswith(mod + "."):
                alvo = por_modulo[mod]
                break
        if alvo:
            internos.append(alvo)
        else:
            externos.append(esp)  # stdlib ou dependência: fora da raiz, não é aresta interna
    return internos, externos, unresolved, len(especificadores)


def analyze(path: Path, root: Path) -> Modulo:
    proprio = path.relative_to(root).as_posix()
    internos, externos, unresolved, total = _classificar(path, root)
    return Modulo(
        path=proprio,
        language="python",
        exposes=_exposes(path),
        imports=sorted(set(internos) - {proprio}),
        internos_crus=internos,
        externos=externos,
        unresolved=unresolved,
        total_especificadores=total,
    )


register(Adapter(name="python", extensions=(".py",), semantico=True, analyze=analyze))
