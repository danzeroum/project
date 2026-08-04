#!/usr/bin/env python3
"""Adapter genérico — o fallback que impede que ignorância vire silêncio verde.

Casa qualquer extensão. Não lê símbolo nem aresta: resolve só PERTENCIMENTO, que é exatamente o
que a invariante do código órfão precisa e que não depende de entender a linguagem. Um alvo em Go,
Rust, Elixir ou Kotlin continua respondendo "este arquivo pertence a algum componente?" mesmo sem
ninguém ter escrito um leitor semântico para ele.

A alternativa — ignorar o que não se sabe ler — produziria o pior resultado possível neste
repositório: um laudo verde porque o fiscal percorreu um conjunto vazio. Verde por vacuidade é
indistinguível de verde por cobertura, e é o modo de falha que o ADR-006 nomeia.

O preço é declarado, não escondido: `nao_lido` entra no laudo, e o check de dependência declarada
sabe que para estes arquivos ele não tem o que verificar.
"""

from __future__ import annotations

from pathlib import Path

from . import Adapter, Modulo, register


def analyze(path: Path, root: Path) -> Modulo:
    # A conta fecha em zero: ele não LÊ especificador algum, então não há o que particionar.
    # Zero declarado é diferente de zero por descarte, e é essa diferença que o laudo carrega.
    return Modulo(
        path=path.relative_to(root).as_posix(),
        language=path.suffix.lstrip(".").lower() or "sem-extensao",
        exposes=[],
        imports=[],
        total_especificadores=0,
    )


register(Adapter(
    name="generico",
    extensions=("*",),
    semantico=False,
    analyze=analyze,
    nao_lido="símbolos exportados e arestas de dependência",
))
