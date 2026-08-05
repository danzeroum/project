#!/usr/bin/env python3
"""Documentação viva dos schemas — derivada deles, com --check bloqueante.

São mais de vinte schemas, e até aqui a única forma de saber o que um campo significa era abrir o
JSON. Este gerador transforma as `description` que já existem lá em `docs/schema-reference.md`.

O `--check` é BLOQUEANTE, e essa é a decisão (R-11 rejeitou "docs não-bloqueantes"): documentação
que pode ficar desatualizada sem custo fica desatualizada — e passa a mentir com a autoridade de
documentação, que é pior que não existir. O padrão desta casa é o mesmo do grafo e do alinhamento.

O arquivo nasce com o cabeçalho canônico do CP-029 e entra sozinho na cobertura de
check_derived_vs_source, que deriva a lista de geradores do diretório real — é o teste de que
aquele fiscal foi construído para derivar, e não para conhecer dois arquivos.

Uso:  python ci/generate_schema_docs.py [--check] [--stdout]
Saída: 0 em dia (ou escrito) · 1 desatualizado com --check.
"""

from __future__ import annotations

import json
import sys

import harness_lib as hl

DOC = "docs/schema-reference.md"
CABECALHO = "<!-- GENERATED: não editar; rodar ci/generate_schema_docs.py -->"


def _tipo(node: dict) -> str:
    if "enum" in node:
        return "enum(" + " · ".join(str(v) for v in node["enum"]) + ")"
    if "const" in node:
        return f"const({node['const']})"
    t = node.get("type")
    if isinstance(t, list):
        return " | ".join(t)
    if t == "array":
        itens = node.get("items") or {}
        return f"array<{_tipo(itens) if isinstance(itens, dict) else '?'}>"
    return str(t or "—")


def _linhas_de(schema: dict, prefixo: str = "") -> list[tuple[str, str, bool, str]]:
    """(caminho, tipo, obrigatório, descrição) para cada propriedade, em profundidade.

    Só desce em objetos e itens de array: descer em `allOf`/`if`/`then` produziria caminhos que
    não existem em documento nenhum, e um índice que descreve campos inexistentes é pior que um
    índice incompleto — ele manda o leitor procurar o que não há.
    """
    out: list[tuple[str, str, bool, str]] = []
    props = schema.get("properties") or {}
    obrigatorios = set(schema.get("required") or [])
    for nome, sub in props.items():
        if not isinstance(sub, dict):
            continue
        caminho = f"{prefixo}{nome}"
        out.append((caminho, _tipo(sub), nome in obrigatorios, (sub.get("description") or "").strip()))
        if sub.get("type") == "object" or "properties" in sub:
            out.extend(_linhas_de(sub, f"{caminho}."))
        itens = sub.get("items")
        if isinstance(itens, dict) and ("properties" in itens):
            out.extend(_linhas_de(itens, f"{caminho}[]."))
    return out


def render() -> str:
    partes = [
        CABECALHO,
        "# Referência dos schemas",
        "",
        "Derivado de `harness/schemas/*.json`. As descrições vêm dos próprios schemas — este",
        "documento não acrescenta significado, ele torna legível o que já está declarado.",
        "",
        "Um campo sem descrição aqui é um campo sem descrição **no schema**: o lugar de corrigir",
        "é lá.",
        "",
    ]
    for caminho in sorted((hl.REPO / "harness" / "schemas").glob("*.json")):
        try:
            schema = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:  # pragma: no cover - validate_metadata já reprova antes
            continue
        partes.append(f"## `{caminho.name}`")
        partes.append("")
        if schema.get("title"):
            partes.append(f"**{schema['title']}**")
            partes.append("")
        if schema.get("description"):
            partes.append(f"> {schema['description']}")
            partes.append("")
        linhas = _linhas_de(schema)
        if linhas:
            partes.append("| Campo | Tipo | Obrigatório | Descrição |")
            partes.append("|---|---|---|---|")
            for nome, tipo, obrigatorio, desc in linhas:
                desc = desc.replace("|", "\\|").replace("\n", " ")
                partes.append(f"| `{nome}` | {tipo} | {'sim' if obrigatorio else '—'} | {desc} |")
            partes.append("")
    return "\n".join(partes) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    doc = render()
    destino = hl.REPO / DOC

    if "--stdout" in argv:
        print(doc)
        return 0
    if "--check" in argv:
        atual = destino.read_text(encoding="utf-8") if destino.exists() else ""
        if atual != doc:
            print(f"✗ {DOC} desatualizado — rode: python ci/generate_schema_docs.py",
                  file=sys.stderr)
            return 1
        print(f"✓ {DOC} em dia.")
        return 0

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(doc, encoding="utf-8")
    print(f"✓ escrito {DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
