"""Portas do domínio: contratos que o negócio depende, e uma implementação em memória.

Existe para que o inventário veja mais de um módulo e uma aresta de import real
(``pricing`` depende de ``ports``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Produto:
    """Um item vendável, com preço em centavos para evitar aritmética de ponto flutuante."""

    sku: str
    preco_centavos: int


class CatalogoProdutos(Protocol):
    """Contrato de leitura do catálogo. O negócio depende da porta, não da implementação."""

    def preco_de(self, sku: str) -> int:
        """Retorna o preço em centavos do SKU, ou levanta ``KeyError`` se não existir."""
        ...


@dataclass
class CatalogoEmMemoria:
    """Implementação trivial de :class:`CatalogoProdutos` para testes e exemplo."""

    produtos: dict[str, Produto] = field(default_factory=dict)

    def registrar(self, produto: Produto) -> None:
        self.produtos[produto.sku] = produto

    def preco_de(self, sku: str) -> int:
        return self.produtos[sku].preco_centavos
