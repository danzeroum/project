"""Testes do catálogo em memória — entrada real para o inventário (Trabalho B)."""

import pytest

from project.ports import CatalogoEmMemoria, Produto


def test_preco_de_sku_registrado():
    catalogo = CatalogoEmMemoria()
    catalogo.registrar(Produto(sku="X", preco_centavos=500))
    assert catalogo.preco_de("X") == 500


def test_preco_de_sku_ausente_levanta_keyerror():
    with pytest.raises(KeyError):
        CatalogoEmMemoria().preco_de("inexistente")
