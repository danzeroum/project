#!/usr/bin/env python3
"""Gera o mapa de relacionamento dos metadados a partir dos IDs reais.

Artefato DERIVADO, não fonte de verdade: lê capacidades, componentes, interfaces, regras,
superfícies, ADRs e riscos, e emite um diagrama Mermaid determinístico em docs/metadata-graph.md.

Uso:
  python ci/generate_graph.py            # escreve docs/metadata-graph.md
  python ci/generate_graph.py --stdout   # imprime o markdown
  python ci/generate_graph.py --check     # sai 1 se o arquivo commitado está desatualizado
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "metadata-graph.md"


def load(rel: str) -> dict:
    p = REPO / rel
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_dir(rel: str) -> list[dict]:
    d = REPO / rel
    if not d.exists():
        return []
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.yaml"))]


def nid(x: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in x)


def esc(x: str) -> str:
    return x.replace('"', "'")


def build_mermaid() -> str:
    caps = load("business/capabilities.yaml").get("capabilities", [])
    comps = load("architecture/components.yaml").get("components", [])
    ifaces = load("architecture/interfaces.yaml").get("interfaces", [])
    surfaces = load("design/ui-surfaces.yaml").get("ui_surfaces", [])
    adrs = load("architecture/adr/index.yaml").get("adrs", [])
    risks = load("governance/risk-register.yaml").get("risks", [])
    rule_files = load_dir("business/rules")
    backlog = load("business/requirements/backlog.yaml").get("items", [])
    metrics = load("business/vision.yaml").get("product", {}).get("success_metrics", [])
    project = load("project.yaml").get("project", {})

    lines: list[str] = ["graph TD"]
    classes: dict[str, list[str]] = {k: [] for k in
                                     ("project", "cap", "cmp", "ifc", "rule", "ui", "req", "met",
                                      "test", "adr", "risk")}

    # Camada de testes: um nó por caminho de teste referenciado em qualquer lugar.
    test_paths: set[str] = set()
    for item in backlog:
        test_paths.update(item.get("validated_by", []))
    for rf in rule_files:
        for rule in rf.get("rules", []):
            test_paths.update(rule.get("verified_by", []))
    for comp in comps:
        test_paths.update(comp.get("tested_by", []))
    tnode = lambda p: nid("TEST_" + p)

    # Projeto (raiz)
    pid = project.get("id", "project")
    pnode = nid("PROJ_" + pid)
    lines.append(f'  {pnode}["{esc(pid)}"]')
    classes["project"].append(pnode)

    # Nós de teste (hexágono)
    for p in sorted(test_paths):
        n = tnode(p)
        lines.append(f'  {n}{{{{"{esc(Path(p).name)}"}}}}')
        classes["test"].append(n)

    # Capacidades
    for cap in sorted(caps, key=lambda c: c.get("id", "")):
        n = nid(cap["id"])
        lines.append(f'  {n}["{cap["id"]}<br/>{esc(cap.get("name", ""))}"]')
        classes["cap"].append(n)
        lines.append(f"  {pnode} -->|capacidade| {n}")

    # Componentes → capacidade e dependências
    for comp in sorted(comps, key=lambda c: c.get("id", "")):
        n = nid(comp["id"])
        src = comp.get("source_paths", [])
        leaf = Path(src[0]).name if src else comp.get("kind", "")
        lines.append(f'  {n}["{comp["id"]}<br/>{esc(leaf)}"]')
        classes["cmp"].append(n)
        if comp.get("capability"):
            lines.append(f"  {n} -->|realiza| {nid(comp['capability'])}")
        for dep in sorted(comp.get("depends_on", [])):
            lines.append(f"  {n} -->|depende| {nid(dep)}")
        for req in sorted(comp.get("implements", [])):
            lines.append(f"  {n} -.->|implementa| {nid(req)}")
        for t in sorted(comp.get("tested_by", [])):
            lines.append(f"  {n} -.->|testa| {tnode(t)}")

    # Interfaces: provedor provê; consumidores consomem
    for ifc in sorted(ifaces, key=lambda i: i.get("id", "")):
        n = nid(ifc["id"])
        lines.append(f'  {n}(["{ifc["id"]}<br/>{esc(ifc.get("name", ""))}"])')
        classes["ifc"].append(n)
        if ifc.get("provider"):
            lines.append(f"  {nid(ifc['provider'])} -.->|provê| {n}")
        for cons in sorted(ifc.get("consumers", [])):
            lines.append(f"  {n} -.->|consome| {nid(cons)}")

    # Regras de negócio → capacidade
    for rf in rule_files:
        cap_ref = rf.get("capability")
        for rule in sorted(rf.get("rules", []), key=lambda r: r.get("id", "")):
            n = nid(rule["id"])
            lines.append(f'  {n}["{rule["id"]}"]')
            classes["rule"].append(n)
            if cap_ref:
                lines.append(f"  {nid(cap_ref)} -->|regra| {n}")
            for t in sorted(rule.get("verified_by", [])):
                lines.append(f"  {n} -.->|verifica| {tnode(t)}")

    # Superfícies de UI → capacidade e requisitos satisfeitos
    for s in sorted(surfaces, key=lambda s: s.get("id", "")):
        n = nid(s["id"])
        lines.append(f'  {n}["{s["id"]}"]')
        classes["ui"].append(n)
        if s.get("capability"):
            lines.append(f"  {n} -->|experiência| {nid(s['capability'])}")
        for req in sorted(s.get("satisfies", [])):
            lines.append(f"  {n} -.->|satisfaz| {nid(req)}")

    # Métricas de sucesso (da vision)
    for m in sorted(metrics, key=lambda m: m.get("id", "")):
        n = nid(m["id"])
        lines.append(f'  {n}[["{m["id"]}"]]')
        classes["met"].append(n)

    # Requisitos de backlog → capacidade, dependências e métricas movidas
    for item in sorted(backlog, key=lambda i: i.get("id", "")):
        n = nid(item["id"])
        lines.append(f'  {n}["{item["id"]}<br/>{esc(item.get("status", ""))}"]')
        classes["req"].append(n)
        if item.get("capability"):
            lines.append(f"  {n} -->|requisito| {nid(item['capability'])}")
        for dep in sorted(item.get("depends_on", [])):
            lines.append(f"  {n} -.->|depende| {nid(dep)}")
        for met in sorted(item.get("metrics", [])):
            lines.append(f"  {n} ==>|move| {nid(met)}")
        for rule in sorted(item.get("governed_by", [])):
            lines.append(f"  {n} -.->|regido por| {nid(rule)}")
        for t in sorted(item.get("validated_by", [])):
            lines.append(f"  {n} -.->|validado por| {tnode(t)}")

    # Riscos
    for r in sorted(risks, key=lambda r: r.get("id", "")):
        n = nid(r["id"])
        lines.append(f'  {n}["{r["id"]}"]')
        classes["risk"].append(n)

    # ADRs → capacidade e risco
    for a in sorted(adrs, key=lambda a: a.get("id", "")):
        n = nid(a["id"])
        lines.append(f'  {n}["{a["id"]}"]')
        classes["adr"].append(n)
        for cap in sorted(a.get("related_capabilities", [])):
            lines.append(f"  {n} -->|decide| {nid(cap)}")
        for cmp in sorted(a.get("related_components", [])):
            lines.append(f"  {n} -->|decide| {nid(cmp)}")
        for rk in sorted(a.get("related_risks", [])):
            lines.append(f"  {n} -->|mitiga| {nid(rk)}")

    # Estilo por tipo (claro/escuro-neutro)
    styles = {
        "project": "fill:#1f2937,stroke:#111827,color:#fff",
        "cap": "fill:#2563eb,stroke:#1e40af,color:#fff",
        "cmp": "fill:#0891b2,stroke:#0e7490,color:#fff",
        "ifc": "fill:#7c3aed,stroke:#5b21b6,color:#fff",
        "rule": "fill:#16a34a,stroke:#15803d,color:#fff",
        "ui": "fill:#db2777,stroke:#9d174d,color:#fff",
        "req": "fill:#0d9488,stroke:#0f766e,color:#fff",
        "met": "fill:#ea580c,stroke:#c2410c,color:#fff",
        "test": "fill:#57534e,stroke:#44403c,color:#fff",
        "adr": "fill:#ca8a04,stroke:#a16207,color:#fff",
        "risk": "fill:#dc2626,stroke:#991b1b,color:#fff",
    }
    for cls, style in styles.items():
        lines.append(f"  classDef {cls} {style};")
        if classes[cls]:
            lines.append(f"  class {','.join(classes[cls])} {cls};")

    return "\n".join(lines)


def render_doc() -> str:
    return (
        # Cabeçalho CANÔNICO (CP-029). Um formato só para os dois geradores: duas convenções
        # para a mesma promessa é como a terceira nasce sem nenhuma.
        "<!-- GENERATED: não editar; rodar ci/generate_graph.py -->\n"
        "# Mapa de relacionamento dos metadados\n\n"
        "> Artefato DERIVADO dos metadados reais, não fonte de verdade. Editar aqui é trabalho\n"
        "> perdido: o `--check` do CI contradiz a edição na hora mais cara.\n\n"
        "Legenda: azul-escuro = projeto · azul = capacidade (`CAP-`) · ciano = componente (`CMP-`) ·\n"
        "roxo = interface (`IFC-`) · verde = regra (`RULE-`) · rosa = superfície de UI (`UI-`) ·\n"
        "amarelo = ADR · vermelho = risco (`RISK-`).\n\n"
        "```mermaid\n" + build_mermaid() + "\n```\n"
    )


def main(argv: list[str]) -> int:
    doc = render_doc()
    if "--stdout" in argv:
        print(doc)
        return 0
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != doc:
            print("✗ docs/metadata-graph.md desatualizado — rode: python ci/generate_graph.py")
            return 1
        print("✓ docs/metadata-graph.md em dia.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"✓ escrito {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
