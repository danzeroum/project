#!/usr/bin/env python3
"""Adapter de TypeScript/JavaScript — parser próprio de imports, semântico PARCIAL.

Por que não `dependency-cruiser`, que resolveria tsconfig, aliases de workspace e re-exports
corretamente: adotá-lo faria este molde — Python puro — passar a exigir uma toolchain de Node
para fiscalizar qualquer alvo, inclusive alvos que não têm Node. O parser próprio resolve o caso
que a invariante do código órfão precisa (pertencimento e imports relativos) e DECLARA no laudo o
que não resolve, em vez de deixar o buraco invisível.

O que ele reconhecidamente NÃO lê, e por isso `semantico=False`:
  - aliases de path (`@app/x`) e workspaces de monorepo, que dependem de tsconfig/package.json;
  - re-export (`export * from`), que exigiria seguir a cadeia;
  - import dinâmico com especificador montado em runtime.

Aresta não resolvida vira ausência de aresta, nunca aresta falsa: o check de dependência declarada
trata import não visto como "não sei", e é o laudo que diz onde ele foi cego.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import Adapter, Modulo, register

EXTENSOES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

# from "x" | import "x" | import(...) | require("x") — só o especificador interessa.
_ESPECIFICADOR = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']""",
    re.MULTILINE,
)
# export function|class|const|let|var|interface|type|enum NOME
_EXPORT = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
# export { a, b as c }
_EXPORT_CHAVES = re.compile(r"^\s*export\s*\{([^}]*)\}", re.MULTILINE)


def _resolver(especificador: str, origem: Path, root: Path) -> str | None:
    """Só o que é relativo: '@app/x' e 'react' não são resolvíveis sem tsconfig, e chutar
    um caminho plausível produziria aresta falsa — pior que aresta ausente."""
    if not especificador.startswith("."):
        return None
    base = (origem.parent / especificador).resolve()
    candidatos = [base, *(base.with_suffix(ext) for ext in EXTENSOES),
                  *(base / f"index{ext}" for ext in EXTENSOES)]
    for cand in candidatos:
        if cand.is_file():
            try:
                return cand.relative_to(root.resolve()).as_posix()
            except ValueError:
                return None  # fora da raiz: não é aresta interna
    return None


def _exposes(texto: str) -> list[str]:
    nomes = set(_EXPORT.findall(texto))
    for bloco in _EXPORT_CHAVES.findall(texto):
        for parte in bloco.split(","):
            parte = parte.strip()
            if not parte:
                continue
            nomes.add(parte.split(" as ")[-1].strip() if " as " in parte else parte)
    return sorted(n for n in nomes if n)


def analyze(path: Path, root: Path) -> Modulo:
    texto = path.read_text(encoding="utf-8", errors="replace")
    alvos = {r for e in _ESPECIFICADOR.findall(texto) if (r := _resolver(e, path, root))}
    proprio = path.relative_to(root).as_posix()
    return Modulo(
        path=proprio,
        language="typescript",
        exposes=_exposes(texto),
        imports=sorted(alvos - {proprio}),
    )


register(Adapter(
    name="typescript",
    extensions=EXTENSOES,
    semantico=False,
    analyze=analyze,
    nao_lido="aliases de path e workspaces de monorepo, re-export em cadeia, import dinâmico",
))
