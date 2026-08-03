"""Testes de precificação — entrada real para o inventário (Trabalho B)."""

import pytest

from project.pricing import Linha, subtotal_centavos, total_com_imposto_centavos
from project.ports import CatalogoEmMemoria, Produto


def _catalogo() -> CatalogoEmMemoria:
    catalogo = CatalogoEmMemoria()
    catalogo.registrar(Produto(sku="A", preco_centavos=1000))
    catalogo.registrar(Produto(sku="B", preco_centavos=250))
    return catalogo


def test_subtotal_soma_linhas():
    linhas = [Linha("A", 2), Linha("B", 3)]
    assert subtotal_centavos(linhas, _catalogo()) == 2000 + 750


def test_subtotal_pedido_vazio_e_zero():
    assert subtotal_centavos([], _catalogo()) == 0


def test_subtotal_ignora_quantidade_nao_positiva():
    assert subtotal_centavos([Linha("A", 0), Linha("B", -1)], _catalogo()) == 0


def test_total_com_imposto_arredonda_para_centavo():
    linhas = [Linha("B", 1)]  # 250
    assert total_com_imposto_centavos(linhas, _catalogo(), 0.1) == 275


def test_taxa_fora_do_intervalo_levanta():
    with pytest.raises(ValueError):
        total_com_imposto_centavos([], _catalogo(), 1.0)
