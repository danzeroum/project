#!/usr/bin/env python3
"""Adapter de TypeScript/JavaScript — imports relativos e aliases de workspace.

Por que não `dependency-cruiser`: adotá-lo faria este molde — Python puro — passar a exigir uma
toolchain de Node para fiscalizar qualquer alvo, inclusive alvos que não têm Node (ADR-009).

Por que os aliases são resolvidos pelos `package.json`, e NÃO por `tsconfig:paths`: medido num
monorepo real, os pacotes se referenciam por `@escopo/nome` e o `tsconfig` não declara `paths`
algum — a resolução vem do link que o gerenciador de pacotes cria. O registro de verdade é o
`name` de cada `package.json` sob as raízes, e ele é o mesmo em npm, yarn, pnpm e bun.

Todo especificador cai em exatamente uma de três listas — resolvido, externo, unresolved — e
`ci/inventory_code.py` recusa o inventário se a conta não fechar. A regra vale mais que o caso
que a originou: 84 arestas internas de um alvo real sumiam sem entrar em lugar nenhum, e o
adapter cumpria "nunca inventar aresta" enquanto quebrava "declarar o que não leu".

O que ele reconhecidamente ainda NÃO lê, e por isso `semantico=False`:
  - re-export em cadeia (`export * from`), que exigiria seguir a cadeia até a definição;
  - import dinâmico com especificador montado em runtime;
  - alias declarado só em `tsconfig:paths` sem pacote correspondente no workspace.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import Adapter, Modulo, register

EXTENSOES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

# from "x" | import "x" | import(...) | require("x") — só o especificador interessa.
_ESPECIFICADOR = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']""",
    re.MULTILINE,
)
_EXPORT = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_EXPORT_CHAVES = re.compile(r"^\s*export\s*\{([^}]*)\}", re.MULTILINE)

_IGNORAR = {"node_modules", ".git", "dist", "build", ".next", "coverage"}

# Onde a FONTE de um pacote costuma morar. Convenção, não configuração — e é o que salva quando
# o entrypoint declarado aponta para build que não existe em clone fresco.
_DIRS_FONTE = ("", "src", "lib", "source")


def _pacotes_do_workspace(root: Path) -> dict[str, tuple[str, dict]]:
    """nome do pacote -> (diretório, package.json), lido dos package.json sob a raiz.

    Memoizado por raiz porque o inventário chama isto uma vez por arquivo. Profundidade limitada
    a três níveis: cobre `apps/*`, `packages/*` e layouts equivalentes sem varrer a árvore toda.
    """
    cache = _pacotes_do_workspace._cache  # type: ignore[attr-defined]
    chave = str(root)
    if chave in cache:
        return cache[chave]

    mapa: dict[str, tuple[str, dict]] = {}
    for profundidade in ("package.json", "*/package.json", "*/*/package.json"):
        for pj in root.glob(profundidade):
            if any(parte in _IGNORAR for parte in pj.parts):
                continue
            try:
                doc = json.loads(pj.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue  # package.json ilegível não é aresta; vira unresolved lá na frente
            nome = doc.get("name")
            if nome and pj.parent != root:
                mapa[nome] = (pj.parent.relative_to(root).as_posix(), doc)
    cache[chave] = mapa
    return mapa


_pacotes_do_workspace._cache = {}  # type: ignore[attr-defined]


def _arquivo_de(base: Path, root: Path) -> str | None:
    """base pode ser o arquivo, base+extensão, ou base/index+extensão."""
    candidatos = [base, *(base.with_suffix(e) for e in EXTENSOES),
                  *(base / f"index{e}" for e in EXTENSOES)]
    for cand in candidatos:
        if cand.is_file():
            try:
                return cand.relative_to(root.resolve()).as_posix()
            except ValueError:
                return None  # fora da raiz: não é aresta interna
    return None


def _entradas_declaradas(pj: dict) -> list[str]:
    """Entrypoints que o package.json declara, na ordem em que um resolvedor os tentaria."""
    out: list[str] = []
    exports = pj.get("exports")
    if isinstance(exports, str):
        out.append(exports)
    elif isinstance(exports, dict):
        raiz = exports.get(".", exports)
        if isinstance(raiz, str):
            out.append(raiz)
        elif isinstance(raiz, dict):
            out += [v for v in raiz.values() if isinstance(v, str)]
    out += [pj[c] for c in ("module", "main", "types") if isinstance(pj.get(c), str)]
    return out


def _entrypoint(base: Path, root: Path, pj: dict) -> str | None:
    """O arquivo que representa o pacote, com três tentativas em ordem de fidelidade.

    A segunda é a que importa num monorepo não construído: `main` costuma apontar para
    `./dist/index.js`, que só existe depois do build. Um clone fresco não tem dist algum, e
    desistir aí faria TODA aresta entre pacotes virar unresolved — tecnicamente honesto e
    praticamente inútil. Mapear o nome do entrypoint de volta para a fonte é convenção estável
    em npm, yarn, pnpm e bun.
    """
    declaradas = _entradas_declaradas(pj)
    for cand in declaradas:                          # 1. o build existe
        if alvo := _arquivo_de((base / cand).resolve(), root):
            return alvo
    for cand in declaradas:                          # 2. o mesmo nome, na fonte
        nome = Path(cand).stem
        for d in _DIRS_FONTE:
            if alvo := _arquivo_de((base / d / nome).resolve(), root):
                return alvo
    for d in _DIRS_FONTE:                            # 3. convenção pura
        if alvo := _arquivo_de((base / d / "index").resolve(), root):
            return alvo
    return None


def _resolver(esp: str, origem: Path, root: Path) -> tuple[str, str | None]:
    """(classe, alvo). classe ∈ {'interno', 'externo', 'unresolved'}."""
    if esp.startswith("."):
        alvo = _arquivo_de((origem.parent / esp).resolve(), root)
        # Relativo que não resolve é aresta REAL que não conseguimos seguir — nunca 'externo'.
        return ("interno", alvo) if alvo else ("unresolved", esp)

    if esp.startswith("node:"):
        return "externo", None

    pacotes = _pacotes_do_workspace(root)
    for nome, (diretorio, pj) in sorted(pacotes.items(), key=lambda kv: -len(kv[0])):
        if esp != nome and not esp.startswith(nome + "/"):
            continue
        base = root.resolve() / diretorio
        sub = esp[len(nome):].lstrip("/")
        if sub:
            for d in _DIRS_FONTE:
                if alvo := _arquivo_de((base / d / sub).resolve(), root):
                    return "interno", alvo
        elif alvo := _entrypoint(base, root, pj):
            return "interno", alvo
        # Pacote do workspace cujo arquivo não foi encontrado: declarado, nunca inventado.
        return "unresolved", esp

    return "externo", None  # bare specifier sem pacote no workspace: dependência de terceiro


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
    especificadores = _ESPECIFICADOR.findall(texto)
    proprio = path.relative_to(root).as_posix()

    internos: list[str] = []
    externos: list[str] = []
    unresolved: list[str] = []

    for esp in especificadores:
        classe, alvo = _resolver(esp, path, root)
        if classe == "interno":
            internos.append(alvo)  # type: ignore[arg-type]
        elif classe == "externo":
            externos.append(esp)
        else:
            unresolved.append(esp)

    return Modulo(
        path=proprio,
        language="typescript",
        exposes=_exposes(texto),
        # A aresta é deduplicada e não aponta para o próprio arquivo; a partição, logo abaixo,
        # guarda a lista crua — é ela que prova que nada foi engolido.
        imports=sorted(set(internos) - {proprio}),
        internos_crus=internos,
        externos=externos,
        unresolved=unresolved,
        total_especificadores=len(especificadores),
    )


register(Adapter(
    name="typescript",
    extensions=EXTENSOES,
    semantico=False,
    analyze=analyze,
    nao_lido="re-export em cadeia, import dinâmico, alias só em tsconfig:paths sem pacote no workspace",
))
