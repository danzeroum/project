# ADR-005 — Catálogo via porta (Protocol) e adaptador; precificação depende da porta

- **Status:** accepted
- **Data:** 2026-08-03
- **Capacidades relacionadas:** CAP-CATALOG
- **Componentes relacionados:** CMP-CATALOG, CMP-PRICING

## Contexto

A precificação precisa consultar preços de produtos. Se o módulo de precificação dependesse de uma
implementação concreta de catálogo (por exemplo uma classe ligada a um banco), trocar a fonte de
dados exigiria alterar a precificação, e testá-la exigiria a infraestrutura real.

## Decisão

O catálogo é exposto como uma **porta** — um `Protocol` (`project.ports.CatalogoProdutos`) — com um
adaptador em memória (`CatalogoEmMemoria`). O componente de precificação (`CMP-PRICING`) **depende da
porta, nunca de uma implementação concreta**. É inversão de dependência: o domínio define o contrato,
a infraestrutura o satisfaz.

## Consequências

- A precificação é testável com um catálogo em memória, sem banco nem rede.
- Trocar a fonte de dados do catálogo é adicionar um adaptador que satisfaz a porta — sem tocar a
  precificação.
- `CMP-CATALOG` (a porta) e `CMP-PRICING` (o consumidor) ficam acoplados apenas pelo contrato, o que
  o `IFC-CATALOG-PORT` registra e o fiscal cruza.

## Fiscal

`architecture/interfaces.yaml` (`IFC-CATALOG-PORT`: `exposes ⊆` provedor, consumidor declara
`depends_on`); `ci/validate_metadata.py::check_interfaces`; testes em `tests/unit/test_pricing.py`
(precificação exercida com `CatalogoEmMemoria`).
