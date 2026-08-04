#!/usr/bin/env python3
"""Registro de adapters de linguagem — plugins, não um `if` que cresce.

Acrescentar linguagem NÃO edita o dispatcher: escreve-se um módulo aqui e ele se registra. É a
diferença entre um molde que suporta N linguagens e um molde que suporta as linguagens que alguém
lembrou de acrescentar num elif.

Três níveis de leitura, e o terceiro é o que importa para a honestidade do laudo:

  semantico=True   lê símbolos e arestas de import de verdade (python)
  semantico=False  + `nao_lido`: resolve pertencimento e DECLARA o que não soube ler
                   (typescript por parser próprio; genérico para o resto)

Nenhum arquivo escapa: o adapter genérico casa qualquer extensão. Isso é deliberado — a invariante
do código órfão é sobre PERTENCIMENTO, e pertencimento não depende de entender a linguagem. O que
uma linguagem sem leitor semântico perde são as arestas de dependência, e a perda aparece no laudo
em vez de virar silêncio verde.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# --------------------------------------------------------------------------------------


@dataclass
class Modulo:
    """Um arquivo de código lido por um adapter.

    Os quatro campos de import formam uma PARTIÇÃO, e ci/inventory_code.py recusa o inventário
    quando ela não fecha (exit 2). A conta existe porque o modo de falha real não é resolver
    errado — é engolir: um especificador que some sem cair em nenhuma das três listas deixa uma
    aresta invisível, e nenhum teste de caso específico pega o próximo caminho de código que
    fizer o mesmo. Aritmética pega.
    """

    path: str                                  # relativo à raiz do inventário
    language: str
    exposes: list[str] = field(default_factory=list)

    # Arestas para consumo: alvos internos, sem duplicata e sem o próprio arquivo.
    imports: list[str] = field(default_factory=list)

    # A PARTIÇÃO. Três listas CRUAS — uma entrada por especificador encontrado no arquivo, com
    # duplicatas preservadas. É o que torna a conta capaz de pegar um descarte: `imports` é
    # deduplicado e por isso nunca serviria de prova.
    internos_crus: list[str] = field(default_factory=list)   # resolveram para dentro da raiz
    externos: list[str] = field(default_factory=list)        # fora da raiz: dependência, não aresta
    unresolved: list[str] = field(default_factory=list)      # parecem internos e não resolveram
    total_especificadores: int = 0                           # contados ANTES de classificar

    def conta_fecha(self) -> bool:
        """Todo especificador caiu em exatamente um balde. Sem isto, um caminho de código novo
        que engolisse um import passaria — e nenhum teste de caso específico o pegaria."""
        return self.total_especificadores == (
            len(self.internos_crus) + len(self.externos) + len(self.unresolved))


@dataclass
class Adapter:
    name: str
    extensions: tuple[str, ...]
    semantico: bool
    analyze: Callable[[Path, Path], Modulo]
    # O que este adapter reconhecidamente NÃO lê. Vazio só quando semantico=True.
    nao_lido: str = ""


_REGISTRY: list[Adapter] = []


def register(adapter: Adapter) -> Adapter:
    """Substitui por nome em vez de recusar duplicata.

    Recusar parecia a escolha estrita e era a errada: quando este pacote é recarregado (os testes
    de mordida recarregam os fiscais para apontá-los a uma cópia), o registro zera enquanto os
    módulos-plugin seguem em sys.modules — e a recusa transformava um segundo registro legítimo em
    exceção. Substituir mantém a invariante que interessa (um adapter por nome) sem inventar um
    modo de falha que só aparece sob reload.
    """
    global _REGISTRY
    _REGISTRY = [a for a in _REGISTRY if a.name != adapter.name] + [adapter]
    return adapter


def registry() -> list[Adapter]:
    """Ordem de registro, com o genérico sempre por último (ele casa tudo)."""
    _load()
    return sorted(_REGISTRY, key=lambda a: a.extensions == ("*",))


def for_path(path: Path) -> Adapter:
    suffix = path.suffix.lower()
    for adapter in registry():
        if suffix in adapter.extensions:
            return adapter
    return next(a for a in registry() if a.extensions == ("*",))


PLUGINS = ("python", "typescript", "generico")


def _load() -> None:
    """Garante que todo plugin está registrado. Import tardio evita ciclo com o dispatcher.

    A condição é o REGISTRO estar completo, não um sinalizador de "já importei": um módulo já
    presente em sys.modules não reexecuta seu register() no import, então depois de um reload
    deste pacote o registro ficaria vazio e for_path não acharia nem o fallback.
    """
    import importlib

    for nome in PLUGINS:
        if any(a.name == nome for a in _REGISTRY):
            continue
        mod = importlib.import_module(f"{__name__}.{nome}")
        if not any(a.name == nome for a in _REGISTRY):
            importlib.reload(mod)
