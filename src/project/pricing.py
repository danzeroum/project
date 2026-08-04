"""Precificação: uma função pura sobre um pedido, dependendo da porta de catálogo.

Ramos reais (linha vazia, imposto, arredondamento) para o inventário ter estrutura para catalogar.
"""

from __future__ import annotations

from dataclasses import dataclass

from project.ports import CatalogoProdutos


@dataclass(frozen=True)
class Linha:
    """Uma linha de pedido: um SKU e uma quantidade."""

    sku: str
    quantidade: int


def subtotal_centavos(linhas: list[Linha], catalogo: CatalogoProdutos) -> int:
    """Soma o preço de cada linha em centavos. Pedido vazio custa zero."""
    total = 0
    for linha in linhas:
        if linha.quantidade <= 0:
            continue
        total += catalogo.preco_de(linha.sku) * linha.quantidade
    return total


def total_com_imposto_centavos(
    linhas: list[Linha], catalogo: CatalogoProdutos, taxa: float
) -> int:
    """Aplica a taxa de imposto (ex.: 0.1 = 10%) ao subtotal, arredondando para o centavo."""
    if not 0.0 <= taxa < 1.0:
        raise ValueError("taxa deve estar em [0, 1)")
    base = subtotal_centavos(linhas, catalogo)
    return round(base * (1.0 + taxa))


# ── INJEÇÃO DE TESTE — NÃO MERGEAR ────────────────────────────────────────────
# Quebra deliberadamente a inversão de dependência do ADR-005: o módulo de
# precificação passa a depender do adaptador concreto em vez da porta.
# Serve para provar que `governance` fica VERMELHO num PR real, e não só que o
# passo negativo detecta a injeção numa cópia.
from project.ports import CatalogoEmMemoria


def _catalogo_padrao() -> CatalogoEmMemoria:
    return CatalogoEmMemoria({})
