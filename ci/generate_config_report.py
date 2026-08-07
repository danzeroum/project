#!/usr/bin/env python3
"""Painel de CONFIGURAÇÃO do repositório — o que já está decidido antes de alguém chegar.

O relatório de conteúdo responde *o que este repositório governa*. Este responde outra pergunta, e
é a que ninguém consegue responder hoje sem abrir os trinta contratos: o vocabulário fechado, a
gramática dos identificadores, as combinações que os schemas tornam inexpressáveis, o plano de
controle, e o que um derivado herda travado versus o que nasce vazio.

ELE NÃO CONTÉM A INFORMAÇÃO, ELE A DERIVA — e aqui isso é mais do que uma boa prática, porque o
modo de falha da alternativa é silencioso. Um dado velho às vezes é visivelmente velho; um
VOCABULÁRIO velho não é. Uma lista de valores escrita à mão aqui dentro continuaria renderizando
perfeita depois que o schema ganhasse um valor novo, ensinando um vocabulário que o repositório já
não usa — sem erro, sem aviso, sem nada ficar vermelho. É o RISK-ORIENT-001 e a segunda descrição
que o ADR-014 nomeia, na sua forma mais difícil de perceber.

Por isso, três regras que valem para o arquivo inteiro:

  1. Nenhum valor de enum, pattern ou const é literal aqui. Tudo sai de `percorrer`.
  2. Toda contagem é `len()` de coleção derivada. Nenhum número que descreva o repositório é
     escrito — inclusive o de fiscais agregados, que muda quando ESTE gerador entra no agregado.
  3. Deduplicação por JSON Pointer, jamais por valor: a mesma escala aparece em vários contratos
     com significados distintos, e fundi-las apagaria justamente o que o leitor precisa ver.

`_vocabulario_nao_esta_no_codigo` faz o arquivo provar isso a cada execução, lendo o próprio AST.

Saída: 0 em dia (ou escrito) · 1 desatualizado com --check · 2 o fiscal não conseguiu fiscalizar.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Any

try:
    import harness_lib as hl
    import check_dependency_conflict
    import env_guard
    import validate_metadata
except ImportError as exc:  # dependência ausente é estado a reportar, nunca traceback
    hl = None  # type: ignore[assignment]
    _FALTA: ImportError | None = exc
else:
    _FALTA = None


GERADOR = "ci/generate_config_report.py"
HTML = "docs/configuracao/index.html"
DADOS = "docs/configuracao/config.json"
CSS_FONTE = "ci/assets/organic.css"
LAUDO = "harness/reports/config-report.json"
SCHEMA = "config-report.schema.json"

SCHEMA_VERSION = "1.0"
METADATA_VERSION = "1.0"

CABECALHO = f"<!-- GENERATED: não editar; rodar {GERADOR} -->"
TITULO = "Configuração do Repositório"

# Segmentos de schema cujos FILHOS são nomes (de campo ou de definição). É a única forma correta
# de montar o nome legível: retirar "properties"/"items"/"$defs" do ponteiro a posteriori está
# errado neste repositório, porque existe uma propriedade chamada literalmente `items` — e a
# cirurgia no texto do ponteiro comeria um segmento real. Acumulando durante a descida, a classe
# de bug deixa de existir em vez de ser remendada.
POR_NOME = ("properties", "patternProperties", "$defs", "definitions")

# Descer por qualquer um destes torna tudo abaixo PREDICADO de uma trava. É o que separa um const
# que trava um valor (tela de valores) de um const que é a condição de uma trava (tela de travas).
CONDICIONAIS = ("if", "then", "else", "not")

# ── A ÚNICA decisão de apresentação deste gerador ──────────────────────────────────────────────
# Agrupamento temático dos contratos, declarado UMA vez e fail-closed nos dois sentidos: contrato
# sem grupo e grupo apontando para contrato que não existe mais abortam com exit 2 (ver `_grupos`).
# Um contrato não classificado sumiria da tela em silêncio, que é exatamente o modo de falha que
# este painel existe para não ter — e a entrada morta faz a classificação parecer completa por uma
# razão que já não existe, que é a mesma mecânica de `ungoverned` e `risk_exemptions`.
GRUPO_POR_SCHEMA = {
    "adr-index.schema.json": "arquitetura",
    "audit-report.schema.json": "governança",
    "backlog.schema.json": "negócio",
    "bootstrap-report.schema.json": "etapas",
    "business-rules.schema.json": "negócio",
    "capabilities.schema.json": "negócio",
    "change-proposal.schema.json": "mutação",
    "components.schema.json": "arquitetura",
    "config-report.schema.json": "governança",
    "conformance-review.schema.json": "governança",
    "data-inventory.schema.json": "privacidade",
    "dependencies.schema.json": "governança",
    "design-system.schema.json": "arquitetura",
    "harness.schema.json": "execução",
    "ingest-pipeline.schema.json": "etapas",
    "interfaces.schema.json": "arquitetura",
    "ledger.schema.json": "mutação",
    "privacy-review.schema.json": "privacidade",
    "project.schema.json": "identidade",
    "protection-attestation.schema.json": "governança",
    "provenance.schema.json": "identidade",
    "release-manifest.schema.json": "identidade",
    "report.schema.json": "contrato de régua",
    "risk-register.schema.json": "governança",
    "stages.schema.json": "etapas",
    "suite-contract-manifest.schema.json": "contrato de régua",
    "suite-registry.schema.json": "contrato de régua",
    "target-lock.schema.json": "identidade",
    "threat-model.schema.json": "governança",
    "ui-surfaces.schema.json": "arquitetura",
    "vision.schema.json": "negócio",
}

_REMOTO = re.compile(r"^\s*@import\s+url\([^)]*\)\s*;\s*$", re.MULTILINE)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Estrato 1 — a travessia. Não conhece tela alguma.
# ══════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class No:
    """Um nó de schema com seu endereço. `ponteiro` é RFC 6901 e resolve por `hl.json_pointer`."""

    arquivo: str
    ponteiro: str
    nome: tuple[str, ...]
    node: dict
    sob_condicional: bool
    sob_cabecalho: bool

    @property
    def campo(self) -> str:
        return ".".join(self.nome) or "(raiz)"


@dataclass
class Leitura:
    """Acumula o que foi lido, para que a procedência seja verificável em vez de afirmada."""

    arquivos: dict[str, str] = _dc_field(default_factory=dict)
    ilegiveis: list[dict] = _dc_field(default_factory=list)
    vazios: dict[str, str] = _dc_field(default_factory=dict)

    def marcar(self, rel: str) -> None:
        if hl.rel_exists(rel):
            self.arquivos[rel] = hl.sha256_file(hl.REPO / rel)

    def yaml(self, rel: str) -> Any:
        self.marcar(rel)
        return hl.read_yaml(rel)

    def json(self, rel: str) -> Any:
        self.marcar(rel)
        return hl.read_json(rel)

    def texto(self, rel: str) -> str:
        self.marcar(rel)
        return hl.read_text(rel)


def _esc(seg: str) -> str:
    return seg.replace("~", "~0").replace("/", "~1")


def _par_de_cabecalho(ramos: Any) -> tuple[str, ...] | None:
    """Duas metades exclusivas sobre o MESMO par de campos: uma fixa ambos por `const`, a outra
    abre um deles. É a invariante `source_of_truth`/`generated_from`, repetida em quase todo
    contrato — UMA invariante, não N valores travados.

    Nenhum nome de campo aparece nesta função, e isso é o ponto: renomeado o par, o card continua
    coletando, com o nome novo lido do schema. Uma lista de arquivos teria a propriedade inversa —
    continuaria certa até o dia em que deixasse de ser.
    """
    if not isinstance(ramos, list) or len(ramos) != 2:
        return None
    props = []
    for ramo in ramos:
        if not isinstance(ramo, dict):
            return None
        p = ramo.get("properties")
        if not isinstance(p, dict) or not p:
            return None
        props.append(p)
    if set(props[0]) != set(props[1]):
        return None
    fixa = all(isinstance(v, dict) and "const" in v for v in props[0].values())
    abre = any(not (isinstance(v, dict) and "const" in v) for v in props[1].values())
    return tuple(sorted(props[0])) if fixa and abre else None


def percorrer(node: Any, ponteiro: str, nome: tuple[str, ...], arquivo: str,
              saida: list[No], *, cond: bool = False, cab: bool = False) -> None:
    """Um percurso por contrato, achatando tudo numa lista de nós endereçados.

    `cond` é monótono: uma vez sob `if`/`then`/`else`/`not`, tudo abaixo continua sob. É o que faz
    um const em `/$defs/x/allOf/0/then/properties/y/const` ser reconhecido como predicado mesmo
    tendo `properties` como pai imediato.
    """
    if isinstance(node, dict):
        saida.append(No(arquivo, ponteiro, nome, node, cond, cab))
        for chave, filho in node.items():
            sub_cab = cab or (chave == "oneOf" and _par_de_cabecalho(filho) is not None)
            if chave in POR_NOME and isinstance(filho, dict):
                for prop, sub in filho.items():
                    percorrer(sub, f"{ponteiro}/{_esc(chave)}/{_esc(prop)}", nome + (prop,),
                              arquivo, saida, cond=cond, cab=sub_cab)
                continue
            percorrer(filho, f"{ponteiro}/{_esc(chave)}", nome, arquivo, saida,
                      cond=cond or chave in CONDICIONAIS, cab=sub_cab)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            percorrer(item, f"{ponteiro}/{i}", nome, arquivo, saida, cond=cond, cab=cab)


def nos_dos_schemas(leitura: Leitura) -> list[No]:
    """Todos os nós de todos os contratos, em ordem estável.

    A ordem é `(arquivo, ponteiro)` e NÃO a ordem de encontro: ordem de chave de dicionário é
    ordem do arquivo em Python, então preservá-la faria um contrato com as chaves reordenadas
    produzir um artefato diferente — e um artefato que reordena sozinho transforma o `--check` em
    gerador de ruído, cujo remédio as pessoas acabam escolhendo é desligá-lo.
    """
    saida: list[No] = []
    caminhos = hl.resolve_glob("harness/schemas/*.schema.json")
    if not caminhos:
        raise hl.HarnessError(
            "FISCAL_CEGO: harness/schemas/ não tem contrato algum. Vazio aqui não é 'repositório "
            "sem vocabulário' — é leitura que falhou, e as duas coisas não podem sair iguais.")
    for caminho in caminhos:
        rel = hl.rel(caminho)
        try:
            doc = leitura.json(rel)
        except hl.HarnessError as exc:
            raise hl.HarnessError(
                f"FISCAL_CEGO: {rel} não parseia ({exc}). Um contrato ilegível NÃO pode virar "
                f"'esse arquivo não tem valores': a seção encolheria em silêncio e a tela "
                f"continuaria bonita, que é o pior modo de falha deste painel.") from exc
        percorrer(doc, "", (), caminho.name, saida)
    return sorted(saida, key=lambda n: (n.arquivo, n.ponteiro))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Estrato 2 — derivadores. Filtros puros sobre a lista achatada, ou leituras de configuração.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _grupos(arquivos: list[str]) -> dict[str, str]:
    """Fail-closed nos dois sentidos — ver o comentário de `GRUPO_POR_SCHEMA`."""
    sem_grupo = sorted(a for a in arquivos if a not in GRUPO_POR_SCHEMA)
    mortas = sorted(a for a in GRUPO_POR_SCHEMA if a not in arquivos)
    if sem_grupo or mortas:
        raise hl.HarnessError(
            f"FISCAL_CEGO: a classificação temática de {GERADOR} está fora de dia — "
            f"sem grupo: {sem_grupo or '—'}; entrada morta: {mortas or '—'}. "
            f"Contrato sem grupo SUMIRIA da tela sem nada ficar vermelho; entrada morta faz a "
            f"classificação parecer completa por uma razão que já não existe.")
    return {a: GRUPO_POR_SCHEMA[a] for a in arquivos}


def derivar_contratos(nos: list[No], grupos: dict[str, str], leitura: Leitura) -> list[dict]:
    saida = []
    for arquivo in sorted(grupos):
        raiz = next((n for n in nos if n.arquivo == arquivo and n.ponteiro == ""), None)
        rel = f"harness/schemas/{arquivo}"
        item = {"file": arquivo, "bytes": len(leitura.texto(rel).encode("utf-8")),
                "group": grupos[arquivo]}
        titulo = (raiz.node.get("title") if raiz else None)
        if titulo:
            item["title"] = titulo
        saida.append(item)
    return saida


def derivar_vocabulario(nos: list[No], grupos: dict[str, str]) -> list[dict]:
    """Todo nó com um vocabulário fechado, deduplicado por PONTEIRO.

    Nunca por valor: a mesma escala aparece em vários contratos significando coisas diferentes —
    severidade de asserção, criticidade de negócio, nível de risco de proposta — e fundi-las
    apagaria a informação de que são escalas distintas, que é justamente o que o leitor precisa.
    """
    saida = []
    for no in nos:
        valores = no.node.get("enum")
        if not isinstance(valores, list) or not valores:
            continue
        item = {"field": no.campo, "pointer": no.ponteiro, "file": no.arquivo,
                "group": grupos[no.arquivo], "values": list(valores)}
        nota = no.node.get("description")
        if isinstance(nota, str) and nota.strip():
            item["note"] = nota.strip()
        saida.append(item)
    return saida


def _instancias_reais(leitura: Leitura) -> list[str]:
    """Todo valor de texto que existe DE FATO nos metadados deste repositório.

    A lista de documentos vem de `validate_metadata.DOCS` — a mesma que o fiscal de metadados usa.
    Manter uma segunda lista aqui seria a segunda descrição de sempre, e a primeira a divergir.
    """
    valores: list[str] = []

    def colher(node: Any) -> None:
        if isinstance(node, str):
            valores.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                colher(v)
        elif isinstance(node, list):
            for v in node:
                colher(v)

    for rel, _schema in validate_metadata.DOCS:
        if not hl.rel_exists(rel):
            continue
        try:
            colher(leitura.yaml(rel))
        except hl.HarnessError:
            continue  # documento ausente ou ilegível é assunto de validate_metadata, não daqui
    return valores


def derivar_gramatica(nos: list[No], grupos: dict[str, str], leitura: Leitura) -> list[dict]:
    """Todo nó com `pattern`, deduplicado pela REGEX.

    A mesma forma de identificador aparece em muitos contratos, e mostrá-la vinte vezes esconderia
    as vinte formas distintas — que são o conteúdo da tela.

    O EXEMPLO nunca é inventado. Ou sai de uma instância que existe no repositório, com o arquivo
    de onde saiu, ou a coluna some. Um exemplo que casa a regex mas não existe aqui é a segunda
    descrição em miniatura, e num derivado recém-criado várias formas legitimamente não terão
    instância alguma.
    """
    por_regex: dict[str, dict] = {}
    for no in nos:
        regex = no.node.get("pattern")
        if not isinstance(regex, str) or not regex:
            continue
        entrada = por_regex.setdefault(regex, {"pattern": regex, "used_in": [],
                                               "group": grupos[no.arquivo]})
        entrada["used_in"].append({"file": no.arquivo, "field": no.campo,
                                   "pointer": no.ponteiro})

    instancias = _instancias_reais(leitura)
    for regex, entrada in por_regex.items():
        try:
            compilada = re.compile(regex)
        except re.error as exc:
            raise hl.HarnessError(
                f"FISCAL_CEGO: pattern que não compila em {entrada['used_in'][0]['file']} "
                f"({entrada['used_in'][0]['pointer']}): {exc}") from exc
        # `fullmatch`, e não `search`, apesar de a semântica de `pattern` em JSON Schema ser de
        # subcadeia. A diferença importa porque o que se procura aqui é uma INSTÂNCIA da forma,
        # não um texto que a contenha: com `search`, um parágrafo de prosa que mencione um
        # identificador vira "exemplo" daquela forma — tecnicamente um casamento, e uma mentira
        # sobre o que a forma é. Onde nenhum valor casa por inteiro, a coluna some.
        for valor in instancias:
            if compilada.fullmatch(valor):
                entrada["example"] = valor
                break
        entrada["used_in"].sort(key=lambda u: (u["file"], u["pointer"]))
    return sorted(por_regex.values(),
                  key=lambda e: (e["group"], e["used_in"][0]["file"], e["pattern"]))


def derivar_consts(nos: list[No], grupos: dict[str, str]) -> list[dict]:
    """Const FORA de bloco condicional e fora da invariante de cabeçalho.

    Dentro de `if`/`then`/`else`/`not` o const é a CONDIÇÃO de uma trava, não um valor travado, e
    pertence à outra tela. Dentro do `oneOf` de cabeçalho ele é uma invariante repetida, e vira um
    card só. O que sobra aqui é o que o repositório fixou de verdade.
    """
    saida = []
    for no in nos:
        if "const" not in no.node or no.sob_condicional or no.sob_cabecalho:
            continue
        saida.append({"field": no.campo, "pointer": no.ponteiro, "file": no.arquivo,
                      "value": no.node["const"]})
    return saida


def derivar_invariante_de_cabecalho(nos: list[No], grupos: dict[str, str]) -> dict | None:
    campos: tuple[str, ...] | None = None
    presente: set[str] = set()
    porque: str | None = None
    for no in nos:
        par = _par_de_cabecalho(no.node.get("oneOf"))
        if par is None:
            continue
        campos = campos or par
        presente.add(no.arquivo)
        porque = porque or _porque_do_no(no, nos)
    if campos is None:
        return None
    invariante = {"fields": list(campos), "present_in": sorted(presente),
                  "absent_in": sorted(set(grupos) - presente)}
    if porque:
        invariante["why"] = porque
    return invariante


# ── Travas ────────────────────────────────────────────────────────────────────────────────────

def _lit(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _frase_pred(node: Any, caminho: tuple[str, ...] = ()) -> str:
    """A CONDIÇÃO de uma trava, em prosa, sintetizada da estrutura — nunca escrita à mão."""
    if not isinstance(node, dict):
        return ""
    alvo = ".".join(caminho)
    if "const" in node:
        return f"{alvo}: {_lit(node['const'])}"
    if "enum" in node:
        return f"{alvo} ∈ {{{', '.join(_lit(v) for v in node['enum'])}}}"
    if "pattern" in node:
        return f"{alvo} casa /{node['pattern']}/"
    partes = [_frase_pred(sub, caminho + (n,))
              for n, sub in (node.get("properties") or {}).items()]
    partes += [f"{'.'.join(caminho + (n,))} presente"
               for n in node.get("required") or ()
               if n not in (node.get("properties") or {})]
    return " e ".join(p for p in partes if p)


def _frase_cons(node: Any, caminho: tuple[str, ...] = ()) -> str:
    """A CONSEQUÊNCIA de uma trava, em prosa, pela mesma via."""
    if not isinstance(node, dict):
        return ""
    partes: list[str] = []
    if node.get("required"):
        partes.append("EXIGE " + ", ".join(".".join(caminho + (n,)) for n in node["required"]))
    if isinstance(node.get("not"), dict):
        dentro = _frase_cons(node["not"], caminho) or _frase_pred(node["not"], caminho)
        partes.append("PROÍBE " + dentro.removeprefix("EXIGE "))
    for n, sub in (node.get("properties") or {}).items():
        partes.append(_frase_cons(sub, caminho + (n,)) or _frase_pred(sub, caminho + (n,)))
    for chave, rotulo in (("oneOf", "EXATAMENTE UM DE"), ("anyOf", "PELO MENOS UM DE")):
        if isinstance(node.get(chave), list):
            dentro = " | ".join(_frase_cons(b, caminho) for b in node[chave])
            partes.append(f"{rotulo} ({dentro})")
    return "; ".join(p for p in partes if p)


def _pilula(node: dict) -> str:
    """O tipo do bloco é LIDO do nó. Uma pílula digitada seria a primeira coisa a divergir no dia
    em que um bloco ganhasse um `else`."""
    presentes = [k for k in ("if", "then", "else", "not", "oneOf", "anyOf") if k in node]
    return "/".join(presentes) or "estrutura"


def _regra(node: dict) -> str:
    if "if" in node:
        base = f"SE {_frase_pred(node['if'])} ENTÃO {_frase_cons(node.get('then') or {})}"
        if "else" in node:
            base += f"; SENÃO {_frase_cons(node['else'])}"
        return base
    return _frase_cons(node)


def _porque_do_no(no: No, nos: list[No]) -> str | None:
    """O porquê sobe pelos ancestrais: o `comment` mora no bloco que embrulha, não no `then`."""
    por_ponteiro = {n.ponteiro: n for n in nos if n.arquivo == no.arquivo}
    ponteiro = no.ponteiro
    while True:
        alvo = por_ponteiro.get(ponteiro)
        if alvo is not None:
            texto = alvo.node.get("comment") or alvo.node.get("description")
            if isinstance(texto, str) and texto.strip():
                return texto.strip()
        if not ponteiro:
            return None
        ponteiro = ponteiro.rsplit("/", 1)[0]


def _e_trava(no: No) -> bool:
    if no.sob_condicional or no.sob_cabecalho:
        return False  # dentro de uma trava; emiti-la de novo duplicaria o mesmo bloco
    n = no.node
    if "if" in n or "anyOf" in n:
        return True
    if isinstance(n.get("not"), dict):
        return True
    if isinstance(n.get("oneOf"), list) and _par_de_cabecalho(n["oneOf"]) is None:
        return True
    return False


def derivar_travas(nos: list[No], grupos: dict[str, str]) -> list[dict]:
    """A tela que justifica o painel: cada entrada é uma combinação que o schema torna
    inexpressável. A regra é sintetizada da estrutura por template — é isso que faz uma trava
    NOVA aparecer sozinha, sem ninguém editar a tela."""
    por_arquivo: dict[str, list[No]] = {}
    for no in nos:
        por_arquivo.setdefault(no.arquivo, []).append(no)

    saida = []
    for no in nos:
        if not _e_trava(no):
            continue
        regra = _regra(no.node)
        if not regra:
            continue
        item = {"pointer": no.ponteiro, "file": no.arquivo, "group": grupos[no.arquivo],
                "block_kind": _pilula(no.node), "rule": regra}
        porque = _porque_do_no(no, por_arquivo[no.arquivo])
        if porque:
            item["why"] = porque
        saida.append(item)
    return saida


# ── Fiscais ───────────────────────────────────────────────────────────────────────────────────

def fiscais_agregados(leitura: Leitura) -> list[dict]:
    """Lê o `return` literal de ci/validate_all.py::_steps() por AST.

    NÃO um glob sobre ci/*.py, que traria também os que rodam fora do agregado. E fail-closed: se
    `_steps` deixar de ser legível por máquina, isto é 'não consegui fiscalizar', jamais
    'zero fiscais' — a contagem da tela sai daqui, e uma contagem que zera em silêncio é pior que
    uma que falta.
    """
    rel = "ci/validate_all.py"
    leitura.marcar(rel)
    arvore = hl.parse_module(hl.REPO / rel)
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.FunctionDef) and no.name == "_steps"):
            continue
        for stmt in ast.walk(no):
            if not (isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.List)):
                continue
            saida = []
            for elt in stmt.value.elts:
                if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 3):
                    continue
                nome, fn, extra = elt.elts
                saida.append({
                    "step": nome.value,
                    "module": ast.unparse(fn).split(".")[0],
                    "argv": [a.value for a in extra.elts if isinstance(a, ast.Constant)],
                })
            if saida:
                return saida
    raise hl.HarnessError(
        "FISCAL_CEGO: ci/validate_all.py::_steps() deixou de devolver uma lista literal de "
        "triplas — a lista dos fiscais agregados saiu do alcance da máquina, e a contagem da "
        "tela passaria a ser um chute.")


def derivar_fiscais(leitura: Leitura) -> dict:
    agregados = fiscais_agregados(leitura)
    nomes_agregados = {f["module"] for f in agregados}

    def ficha(caminho) -> dict:
        rel = hl.rel(caminho)
        leitura.marcar(rel)
        doc = ast.get_docstring(hl.parse_module(caminho))
        item = {"module": rel, "bytes": caminho.stat().st_size}
        if doc:
            item["doc"] = doc.strip().splitlines()[0]
        return item

    por_modulo = {}
    avulsos = []
    for caminho in hl.resolve_glob("ci/*.py"):
        f = ficha(caminho)
        por_modulo[caminho.stem] = f
        if caminho.stem not in nomes_agregados:
            avulsos.append(f)
    for caminho in hl.resolve_glob("ci/adapters/*.py"):
        avulsos.append(ficha(caminho))

    for f in agregados:
        detalhe = por_modulo.get(f["module"])
        if detalhe is None:
            raise hl.HarnessError(
                f"FISCAL_CEGO: _steps() cita o módulo '{f['module']}', que não existe em ci/. "
                f"A lista de agregados e o diretório discordam, e a tela não pode escolher um.")
        f["bytes"] = detalhe["bytes"]
        if "doc" in detalhe:
            f["doc"] = detalhe["doc"]

    return {"aggregated": agregados,
            "standalone": sorted(avulsos, key=lambda f: f["module"])}


# ── Plano de controle ─────────────────────────────────────────────────────────────────────────

def _familias_negadas(leitura: Leitura, declaradas: list[str]) -> list[dict]:
    """As famílias de sequestro já são os blocos de comentário do próprio YAML.

    Raspar comentário só é legítimo porque a leitura tem ÁRBITRO: o conjunto lido por bloco é
    conferido contra o que `yaml.safe_load` devolveu. A raspagem não pode inventar nem perder uma
    variável em silêncio — e uma variável nova que caia fora de qualquer bloco aborta, em vez de
    sumir dos cartões.
    """
    rel = "harness/harness.yaml"
    dentro = False
    familias: list[dict] = []
    for linha in leitura.texto(rel).splitlines():
        cru = linha.strip()
        if not dentro:
            dentro = cru.startswith("env_denylist_exact:")
            continue
        if cru.startswith("#"):
            texto = cru.lstrip("# ").rstrip()
            # Um bloco de comentário ocupa várias linhas; só a PRIMEIRA depois de uma variável
            # abre família nova. Tratar cada linha como um bloco faria o rótulo virar o fragmento
            # final da frase anterior — errado de um jeito que passaria despercebido, porque
            # continuaria renderizando três cartões.
            if not familias or familias[-1]["vars"]:
                familias.append({"family": texto.split(":")[0], "why": texto})
                familias[-1]["vars"] = []
            else:
                familias[-1]["why"] = f"{familias[-1]['why']} {texto}".strip()
        elif cru.startswith("- "):
            if not familias:
                raise hl.HarnessError(
                    f"FISCAL_CEGO: {rel} nega '{cru[2:].strip()}' antes de qualquer bloco de "
                    f"família. Sem bloco, a variável sumiria dos cartões da tela de controle sem "
                    f"nada ficar vermelho.")
            familias[-1]["vars"].append(cru[2:].strip())
        elif cru and not cru.startswith("-"):
            break

    lidas = {v for f in familias for v in f["vars"]}
    if lidas != set(declaradas):
        raise hl.HarnessError(
            f"FISCAL_CEGO: a leitura por bloco e o YAML discordam sobre quais variáveis são "
            f"negadas em {rel} (só no bloco: {sorted(lidas - set(declaradas))}; só no YAML: "
            f"{sorted(set(declaradas) - lidas)}).")
    return [f for f in familias if f["vars"]]


def derivar_controle(leitura: Leitura) -> dict:
    harness = leitura.yaml("harness/harness.yaml") or {}
    higiene = harness.get("env_hygiene")
    if not isinstance(higiene, dict):
        raise hl.HarnessError(
            "FISCAL_CEGO: harness/harness.yaml não declara `env_hygiene`. Bloco ausente é "
            "'não consegui ler', jamais 'nada é negado'.")
    negadas_exatas = higiene.get("env_denylist_exact")
    if negadas_exatas is None:
        raise hl.HarnessError(
            "FISCAL_CEGO: harness/harness.yaml não declara `env_hygiene.env_denylist_exact`.")

    # A denylist EFETIVA é calculada, e é a única honesta: `env_denylist_prefix` está vazia POR
    # DERIVAÇÃO (CP-041) — os prefixos nascem das fichas de régua. Mostrar o YAML cru diria que
    # nada é negado. A função é IMPORTADA de env_guard, jamais reimplementada: uma segunda cópia
    # derivaria, e a primeira entrada a divergir seria a que alguém removeu de um dos dois lados.
    try:
        prefixos = env_guard.prefixos_efetivos(higiene)
    except env_guard.PoliticaAusente as exc:
        raise hl.HarnessError(f"FISCAL_CEGO: denylist efetiva indeterminada: {exc}") from exc

    declarados = list(higiene.get("env_denylist_prefix") or [])
    origem = []
    for caminho in hl.resolve_glob("harness/suites/*.yaml"):
        rel = hl.rel(caminho)
        ficha = (leitura.yaml(rel) or {}).get("suite") or {}
        if ficha.get("env_prefix"):
            origem.append({"prefix": ficha["env_prefix"], "from": rel})
    for p in declarados:
        origem.append({"prefix": p, "from": "harness/harness.yaml"})

    stages = leitura.yaml("harness/stages.yaml") or {}
    politicas = [hl.rel(p) for p in hl.resolve_glob("harness/policies/*.md")
                 if p.name != "README.md"]
    for rel in politicas:
        leitura.marcar(rel)

    return {
        "standard": harness.get("standard"),
        "repository": harness.get("repository"),
        "decision_policy": harness.get("decision_policy"),
        "execution_modes": harness.get("execution_modes"),
        "external_audit": harness.get("external_audit"),
        "target_feedback": harness.get("target_feedback"),
        "paths": harness.get("paths"),
        "env_hygiene": {
            "allowlist": higiene.get("env_allowlist"),
            "denylist_prefix_declarado": declarados,
            "denylist_prefix_efetiva": prefixos,
            "prefix_origem": sorted(origem, key=lambda o: (o["prefix"], o["from"])),
            "familias": _familias_negadas(leitura, list(negadas_exatas)),
            "exceptions": higiene.get("exceptions") or [],
            "fail_on_denied_env": higiene.get("fail_on_denied_env"),
        },
        "stages": [{"id": s.get("id"), "order": s.get("order"), "name": s.get("name"),
                    "artifacts": s.get("artifacts") or [],
                    "enforced_by": len(s.get("enforced_by") or [])}
                   for s in sorted(stages.get("stages") or [], key=lambda s: s.get("order", 0))],
        "ungoverned": stages.get("ungoverned") or [],
        "policies": sorted(politicas),
    }


# ── Ambiente, réguas e herança ────────────────────────────────────────────────────────────────

def derivar_ambiente(leitura: Leitura) -> dict:
    """pyproject lido como TEXTO DECLARADO, no mesmo idioma de validate_metadata.

    Sem resolver de ambiente e sem parser de TOML: o que interessa é o que o repositório DECLARA,
    não o que a máquina de quem roda tem instalado — que faria a tela mudar conforme quem a abre.
    """
    pyproject = leitura.texto("pyproject.toml")
    def _campo(chave: str) -> str | None:
        m = re.search(rf'^{re.escape(chave)}\s*=\s*(.+)$', pyproject, re.MULTILINE)
        return m.group(1).strip() if m else None

    # requirements-qa.txt entra pelo CAMINHO e pela existência, nunca pelo número: a versão do
    # padrão tem fonte única (ADR-003, RISK-DEP-001), e restatá-la aqui criaria a cópia que
    # check_version_single_source existe para impedir.
    leitura.marcar("requirements-qa.txt")
    declaracoes = check_dependency_conflict.declaracoes()
    pins = sorted(
        {(f, f"{nome}{op}{ver}") for nome, ocs in declaracoes.items() for f, op, ver in ocs
         if f != "requirements-qa.txt"})

    gitignore = [l.rstrip() for l in leitura.texto(".gitignore").splitlines()]
    for rel in ("requirements-ci.txt", "harness/local_validate.sh"):
        leitura.marcar(rel)

    return {
        "python": _campo("requires-python"),
        "testpaths": _campo("testpaths"),
        "pythonpath": _campo("pythonpath"),
        "pins": [{"file": f, "spec": s} for f, s in pins],
        "version_source": "requirements-qa.txt",
        "version_source_present": hl.rel_exists("requirements-qa.txt"),
        "gitignore": [l for l in gitignore if l and not l.startswith("#")],
        "gitignore_excecoes": [l for l in gitignore if l.startswith("!")],
        "paridade_local": [l.strip() for l in leitura.texto("harness/local_validate.sh").splitlines()
                           if l.strip().startswith("python ")],
        "hooks": _derivar_hooks(leitura),
        "workflows": sorted(hl.rel(p) for p in hl.resolve_glob(".github/workflows/*.yml")),
        "codeowners": _derivar_codeowners(leitura),
    }


def _derivar_hooks(leitura: Leitura) -> list[dict]:
    settings = leitura.json(".claude/settings.json") or {}
    saida = []
    for evento, grupos in sorted((settings.get("hooks") or {}).items()):
        for grupo in grupos or []:
            for hook in grupo.get("hooks") or []:
                saida.append({"event": evento, "matcher": grupo.get("matcher"),
                              "timeout": hook.get("timeout"),
                              "command": (hook.get("command") or "").split("/")[-1]})
    return saida


def _derivar_codeowners(leitura: Leitura) -> list[dict]:
    if not hl.rel_exists(".github/CODEOWNERS"):
        return []
    saida = []
    for linha in leitura.texto(".github/CODEOWNERS").splitlines():
        cru = linha.strip()
        if not cru or cru.startswith("#"):
            continue
        partes = cru.split()
        saida.append({"path": partes[0], "owners": partes[1:]})
    return saida


def _status_que_proibem(nos: list[No], arquivo: str, campo: str) -> list[str]:
    """Os valores de status para os quais o contrato PROÍBE um campo — lidos do contrato.

    Existe para que a tela possa dizer "proibido neste status" em vez de deixar a célula em
    branco. A distinção é a de sempre: campo ausente porque ninguém preencheu e campo ausente
    porque o contrato o recusa são estados diferentes, e só um deles é pendência.

    E é derivado de propósito. Escrever o nome do status aqui seria transcrever vocabulário: no
    dia em que o contrato passasse a proibir o campo em outro estado, esta função continuaria
    certa e a tela continuaria dizendo o estado antigo, sem nada acusar.
    """
    achados: list[str] = []
    for no in nos:
        if no.arquivo != arquivo or "if" not in no.node:
            continue
        consequencia = _frase_cons(no.node.get("then") or {})
        if f"PROÍBE {campo}" not in consequencia:
            continue
        predicado = no.node["if"]

        def colher(node: Any) -> None:
            if not isinstance(node, dict):
                return
            if "const" in node:
                achados.append(_lit(node["const"]))
            for v in (node.get("enum") or []):
                achados.append(_lit(v))
            for sub in (node.get("properties") or {}).values():
                colher(sub)

        colher(predicado)
    return sorted(set(achados))


def derivar_reguas(nos: list[No], leitura: Leitura) -> dict:
    manifesto_rel = "harness/suite-contract/contract-v1/contract-manifest.json"
    contrato = leitura.json(manifesto_rel) if hl.rel_exists(manifesto_rel) else {}
    proibem_entrypoint = _status_que_proibem(nos, "suite-registry.schema.json", "entrypoint")
    fichas, gaps = [], []
    for caminho in hl.resolve_glob("harness/suites/*.yaml"):
        rel = hl.rel(caminho)
        suite = (leitura.yaml(rel) or {}).get("suite") or {}
        fichas.append({
            "nome": suite.get("nome"), "status": suite.get("status"),
            "contract_version": suite.get("contract_version"),
            "pin_source": suite.get("pin_source"),
            # entrypoint ausente NÃO é dado faltando quando o contrato o proíbe — a tela diz isso
            # em vez de deixar em branco, e distingue pelo STATUS, nunca pela ausência.
            "entrypoint": suite.get("entrypoint"),
            "entrypoint_proibido": suite.get("status") in proibem_entrypoint,
            "perfil_path": suite.get("perfil_path"),
            "env_prefix": suite.get("env_prefix"),
            "modes": [m.get("nome") for m in suite.get("modes") or []],
            "laudo": (suite.get("laudo") or {}).get("path"),
            "file": rel,
        })
        for gap in suite.get("gaps") or []:
            gaps.append({**gap, "suite": suite.get("nome")})
    return {"contract": contrato.get("contract") or {}, "registry": fichas,
            "gaps": sorted(gaps, key=lambda g: (str(g.get("due", "")), str(g.get("id", ""))))}


def derivar_heranca(nos: list[No], leitura: Leitura, controle: dict) -> dict:
    """Vem travado vs. nasce vazio — derivado, e por isso correto quando as fases mudarem.

    `nasce vazio` são os `outputs` das fases de ingestão: literalmente a lista do que a ingestão
    escreve. O *quando* de cada item sai da fase que o produz.
    """
    projeto = leitura.yaml("project.yaml") or {}
    kind = (projeto.get("project") or {}).get("kind")

    fixos = [{"o_que": f"{c['field']} = {_lit(c['value'])}", "porque": "const no contrato",
              "file": c["file"]} for c in derivar_consts(nos, {n.arquivo: "" for n in nos})]
    fixos += [{"o_que": p, "porque": "protected_path — muda só com revisão humana",
               "file": "harness/harness.yaml"}
              for p in (controle.get("repository") or {}).get("protected_paths") or []]

    vazios = []
    ingest = leitura.yaml("harness/pipeline/ingest.yaml") or {}
    for fase in sorted(ingest.get("phases") or [], key=lambda f: f.get("order", 0)):
        for saida in fase.get("outputs") or []:
            vazios.append({"artefato": saida, "quando": fase.get("id"),
                           "como": fase.get("name")})
    return {"kind": kind, "fixed": fixos, "fill": vazios}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Estrato 3 — montagem e autoauditoria
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _vocabulario_nao_esta_no_codigo(vocabulario: list[dict]) -> None:
    """Este gerador prova, a cada execução, que não carrega aquilo que deveria derivar.

    Lê o PRÓPRIO AST, e a escolha é deliberada: um arquivo que fala sobre vocabulário fechado
    contém as palavras do assunto em toda parte, inclusive nos comentários que explicam por que
    ele não deve conter os VALORES. Procurar no texto cru ancoraria na menção — a família
    reincidente registrada em harness/policies/conformance.md, cuja última ocorrência nasceu
    dentro do fiscal escrito para vigiar as anteriores. No AST, comentário não existe.

    Chave de dicionário, índice de subscrito, primeiro argumento de .get/.setdefault/.pop e
    docstring são NOME DE CAMPO do artefato, não valor do repositório: saem da conta. O que sobra
    é literal em posição de DADO, que é onde uma transcrição moraria.
    """
    arvore = hl.parse_module(hl.REPO / GERADOR)
    ignorar: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Dict):
            ignorar.update(id(k) for k in no.keys if isinstance(k, ast.Constant))
        elif isinstance(no, ast.Subscript) and isinstance(no.slice, ast.Constant):
            ignorar.add(id(no.slice))
        elif (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
              and no.func.attr in ("get", "setdefault", "pop", "startswith", "endswith")
              and no.args and isinstance(no.args[0], ast.Constant)):
            ignorar.add(id(no.args[0]))
        elif isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant):
            ignorar.add(id(no.value))
    literais = {no.value for no in ast.walk(arvore)
                if isinstance(no, ast.Constant) and isinstance(no.value, str)
                and id(no) not in ignorar}
    proibidos = {v for item in vocabulario for v in item["values"] if isinstance(v, str)}
    intrusos = sorted(literais & proibidos)
    if intrusos:
        raise hl.HarnessError(
            f"FISCAL_CEGO: {GERADOR} carrega valores de vocabulário em posição de dado: "
            f"{intrusos}. Transcrito, um valor NÃO quebra — continua renderizando bonito depois "
            f"que o contrato mudou, e a tela passa a ensinar o que o repositório já não usa. "
            f"O conserto é renomear a string interna, nunca abrir exceção para ela.")


def _razoes(leitura: Leitura) -> dict[str, str]:
    """Os três estados de vazio, lidos do próprio contrato por ponteiro NOMEADO.

    Por ponteiro nomeado e não por posição num enum: a ordem de uma lista é um detalhe que
    ninguém prometeu manter, e acoplar a tela a ela trocaria uma transcrição por outra, mais
    difícil de ver. Assim o texto existe uma vez, no contrato, e mudá-lo lá muda a tela.
    """
    rel = f"harness/schemas/{SCHEMA}"
    schema = leitura.json(rel)
    saida = {}
    for papel, nome in (("declarada", "razao_declarada"),
                        ("nao_ingerido", "razao_nao_ingerido"),
                        ("ilegivel", "razao_ilegivel")):
        try:
            saida[papel] = hl.json_pointer(schema, f"/$defs/{nome}/const")
        except Exception as exc:
            raise hl.HarnessError(
                f"FISCAL_CEGO: {rel} não declara /$defs/{nome}/const, e é de lá que o texto do "
                f"estado de vazio sai. Sem ele a tela teria de inventar a razão — e 'nenhum' "
                f"inventado é indistinguível de 'não consegui olhar'.") from exc
    return saida


def coletar() -> dict:
    leitura = Leitura()
    nos = nos_dos_schemas(leitura)
    arquivos = sorted({n.arquivo for n in nos})
    grupos = _grupos(arquivos)

    vocabulario = derivar_vocabulario(nos, grupos)
    _vocabulario_nao_esta_no_codigo(vocabulario)

    controle = derivar_controle(leitura)
    projeto = leitura.yaml("project.yaml") or {}
    harness = leitura.yaml("harness/harness.yaml") or {}
    manifesto_rel = "harness/suite-contract/contract-v1/contract-manifest.json"

    dados = {
        "schema_version": SCHEMA_VERSION,
        "metadata_version": METADATA_VERSION,
        "source_of_truth": False,
        "generated_from": "harness/schemas/, harness/harness.yaml, harness/stages.yaml, "
                          "harness/suites/, harness/pipeline/ingest.yaml, ci/, .claude/, "
                          ".github/, project.yaml, pyproject.toml (lista completa e verificável "
                          "em provenance.inputs)",
        "vocabulary": vocabulario,
        "grammar": derivar_gramatica(nos, grupos, leitura),
        "consts": derivar_consts(nos, grupos),
        "header_invariant": derivar_invariante_de_cabecalho(nos, grupos),
        "locks": derivar_travas(nos, grupos),
        "schemas": derivar_contratos(nos, grupos, leitura),
        "control": controle,
        "fiscais": derivar_fiscais(leitura),
        "environment": derivar_ambiente(leitura),
        "suites": derivar_reguas(nos, leitura),
        "inheritance": derivar_heranca(nos, leitura, controle),
        "unreadable": leitura.ilegiveis,
    }

    # Razão do vazio, coleção por coleção. Um zero solto afirma o primeiro estado e pode ser
    # qualquer um dos três; distingui-los é o que impede a tela de pintar 'nenhum' e
    # 'não sei olhar' com a mesma cor.
    #
    # O texto de cada razão é LIDO do contrato por ponteiro NOMEADO — ver o comment de
    # `empty_reasons` em config-report.schema.json. Escrevê-lo aqui seria transcrever vocabulário
    # do próprio artefato, que foi exatamente o que `_vocabulario_nao_esta_no_codigo` acusou na
    # primeira execução deste gerador.
    razoes = _razoes(leitura)
    saidas_da_ingestao = {f["artefato"] for f in dados["inheritance"]["fill"]}
    dados["empty_reasons"] = {}
    for nome, colecao, fonte in (
        ("vocabulary", dados["vocabulary"], None),
        ("grammar", dados["grammar"], None),
        ("consts", dados["consts"], None),
        ("locks", dados["locks"], None),
        ("registry", dados["suites"]["registry"], "harness/suites"),
        ("gaps", dados["suites"]["gaps"], "harness/suites"),
        ("fill", dados["inheritance"]["fill"], "harness/pipeline/ingest.yaml"),
    ):
        if colecao:
            continue
        # Vazio porque a fase que preencheria ainda não rodou é um fato verificável: o artefato
        # está declarado como saída da ingestão e não existe no disco. Nada de olhar o rótulo de
        # ciclo de vida — o rótulo é vocabulário, o arquivo ausente é evidência.
        pendente = fonte in saidas_da_ingestao and not hl.rel_exists(fonte)
        dados["empty_reasons"][nome] = (
            razoes["nao_ingerido"] if pendente else razoes["declarada"])
    for ilegivel in leitura.ilegiveis:
        dados["empty_reasons"][ilegivel["path"]] = razoes["ilegivel"]

    leitura.marcar(CSS_FONTE)
    dados["provenance"] = {
        "repository": (projeto.get("project") or {}).get("id") or "",
        "standard": {
            "name": (projeto.get("quality_standard") or {}).get("name") or "",
            "version_source": "requirements-qa.txt",
        },
        "versions": {
            "schema": projeto.get("schema_version"),
            "metadata": projeto.get("metadata_version"),
            "harness": harness.get("schema_version"),
            "contract": ((leitura.json(manifesto_rel).get("contract") or {}).get("version")
                         if hl.rel_exists(manifesto_rel) else None),
        },
        "inputs": [{"path": p, "sha256": s} for p, s in sorted(leitura.arquivos.items())],
        "inputs_fingerprint": hl.fingerprint(sorted(leitura.arquivos.items())),
        # O commit NÃO é embutido, e dizer isso é metade do ponto. Um SHA aqui faria o --check
        # reprovar para sempre: o artefato nasce num commit e é conferido no seguinte, então o
        # valor mudaria sem que o conteúdo mudasse. O carimbo volátil vai para o laudo, que mora
        # sob harness/reports/ — caminho por onde nenhum fiscal caminha.
        "commit": {"embedded": False, "onde": LAUDO},
    }
    dados["provenance"]["versions"] = {
        k: v for k, v in dados["provenance"]["versions"].items() if v is not None}
    return dados


def payload_json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Estrato 4 — emissão
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _css() -> str:
    """O stylesheet, sem a referência remota — removida MECANICAMENTE e conferida.

    Nunca por edição à mão no arquivo copiado: a limpeza precisa rodar a cada geração, senão nada
    impede uma cópia futura de reintroduzir a referência. Um painel que depende de rede para
    renderizar some quando a rede some — e some em silêncio, porque a página ainda abre.
    """
    # A conferência procura "://" e não o nome de um protocolo: além de pegar qualquer esquema,
    # evita que este arquivo carregue um literal que também é valor de vocabulário em outro
    # contrato — que é o que `_vocabulario_nao_esta_no_codigo` recusa, com razão.
    limpo = _REMOTO.sub("", hl.read_text(CSS_FONTE)).strip() + "\n"
    if "@import" in limpo or "://" in limpo:
        raise hl.HarnessError(
            f"FISCAL_CEGO: {CSS_FONTE} mantém referência remota depois da limpeza. O artefato "
            f"precisa abrir offline; degradar para system-ui é aceitável e está declarado na "
            f"política, buscar fonte na rede não é.")
    return limpo


def render_html(dados: dict) -> str:
    corpo = payload_json(dados).rstrip("\n")
    # `</` pode aparecer DENTRO de um pattern de contrato e fecharia o <script> cedo.
    # `<\/` é escape válido em JSON e não muda o valor desserializado.
    corpo = corpo.replace("</", "<\\/")
    return "\n".join([
        "<!DOCTYPE html>",
        CABECALHO,
        "<!-- O --check do CI contradiz qualquer edição manual: edita-se a FONTE, não o derivado. -->",
        '<html lang="pt-BR">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{TITULO}</title>",
        f"<style>\n{_css()}\n{_ESTILO}\n</style>",
        "</head>",
        "<body>",
        _casca(),
        f'<script type="application/json" id="config-data">{corpo}</script>',
        f"<script>\n{_RENDERER}\n</script>",
        "</body>",
        "</html>",
        "",
    ])


# Os pontos de montagem que o renderer procura. Ficam aqui, num só lugar, porque a casca e o
# renderer precisam concordar sobre eles — e um `getElementById` sem alvo não degrada: a primeira
# chamada levanta e a página fica EM BRANCO, com o HTML inteiro presente no arquivo. O teste
# `test_casca_tem_todos_os_pontos_de_montagem` confere a concordância sem precisar de navegador.
def _casca() -> str:
    """A casca estática. Todo conteúdo é pintado pelo renderer a partir do payload embutido.

    Nenhum valor do repositório aparece neste markup, e é isso que torna a propriedade
    'zero transcrição' auditável: casca + dados + renderer, com os dados numa costura só.
    """
    # O link para o painel de conteúdo é CONDICIONAL. Ele não existe neste repositório hoje, e um
    # link fixo para artefato ausente seria a mesma mentira em miniatura que este painel existe
    # para não cometer. Se o relatório for construído, o link aparece sozinho.
    #
    # O caminho do irmão é DERIVADO de onde este artefato mora, e não escrito. Duas razões, e a
    # segunda só apareceu quando o fiscal acusou: mover docs/configuracao/ move a expectativa
    # junto; e `check_derived_vs_source` deriva "quem gera o quê" procurando caminhos de docs/ no
    # texto dos scripts, sem conseguir distinguir um caminho que o script ESCREVE de um que ele
    # apenas CONSULTA. Escrito por extenso, este teste de existência declarava que este gerador
    # produz o painel de conteúdo — que ele não produz.
    irmao_rel = (Path(HTML).parent.parent / "relatorio" / "index.html").as_posix()
    irmao = (f'<a href="../relatorio/index.html">→ ver o relatório de conteúdo</a>'
             if hl.rel_exists(irmao_rel) else
             '<span class="text-muted">relatório de conteúdo: não existe neste repositório</span>')
    return "\n".join([
        '<div class="wrap">',
        '<aside class="side">',
        '<div class="brand"><i></i><div><b>Configuração</b>'
        '<span id="marca-sub"></span></div></div>',
        '<nav id="nav"></nav>',
        f'<div class="sidefoot"><div id="proc"></div><div style="margin-top:10px">{irmao}</div>'
        '</div>',
        '</aside>',
        '<div>',
        '<header class="head"><div><h1 id="titulo"></h1><p id="sub"></p></div>'
        '<span class="sp"></span>'
        '<input id="q" class="input" type="search" placeholder="buscar em toda a configuração" '
        'style="width:280px" aria-label="buscar">'
        '</header>',
        '<main id="main" class="main"></main>',
        '</div>',
        '</div>',
        '<div id="results" class="elev-lg" hidden></div>',
    ])


_ESTILO = """
/* Painel de configuração — sage é a cor daqui; o relatório de conteúdo usa terracota, e um leitor
   com os dois abertos precisa saber onde está antes de ler o título. */
body { background: var(--color-bg); color: var(--color-text); font-family: var(--font-body);
       margin: 0; font-size: 15px; line-height: 1.55; }
.wrap { display: grid; grid-template-columns: 262px 1fr; min-height: 100vh; min-width: 1240px; }
.side { background: var(--color-surface); border-right: 1px solid var(--color-divider);
        padding: 22px 16px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }
.brand { display: flex; gap: 10px; align-items: center; margin-bottom: 20px; }
.brand i { width: 26px; height: 26px; border-radius: 8px; background: var(--color-accent-2);
           display: block; }
.brand b { font-family: var(--font-heading); font-weight: 400; font-size: 17px; display: block; }
.brand span { font-size: 12px; color: var(--color-neutral-700); }
.navgroup { font-size: 10.5px; text-transform: uppercase; letter-spacing: .08em;
            color: var(--color-neutral-600); margin: 16px 0 6px 10px; }
.navitem { display: grid; grid-template-columns: 22px 1fr auto; gap: 8px; align-items: center;
           padding: 7px 10px; border-radius: 999px; cursor: pointer; border: 0;
           background: transparent; width: 100%; text-align: left; color: inherit;
           font-family: inherit; }
.navitem:hover { background: color-mix(in srgb, #201e1d 5%, transparent); }
.navitem[aria-current="true"] { background: var(--color-accent-2); color: var(--color-accent-2-100); }
.navitem .n { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px;
              opacity: .55; }
.navitem .l { font-size: 13.5px; }
.navitem .c { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px;
              opacity: .5; }
.sidefoot { margin-top: 22px; padding-top: 14px; border-top: 1px solid var(--color-divider);
            font-size: 11px; color: var(--color-neutral-700); }
.head { position: sticky; top: 0; z-index: 30; padding: 14px 34px; display: flex;
        align-items: center; gap: 16px; border-bottom: 1px solid var(--color-divider);
        background: color-mix(in srgb, #f5ead8 92%, transparent); backdrop-filter: blur(8px); }
.head h1 { font-family: var(--font-heading); font-weight: 400; font-size: 19px; margin: 0; }
.head p { margin: 0; font-size: 11.5px; color: var(--color-neutral-600); }
.head .sp { flex: 1; }
.main { padding: 30px 34px 90px; max-width: 1250px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.sec h2 { font-family: var(--font-heading); font-weight: 400; font-size: 25px; margin: 0 0 4px; }
.sec h3 { font-size: 15px; margin: 30px 0 10px; padding-bottom: 8px;
          border-bottom: 1px solid var(--color-divider); display: flex; gap: 10px;
          align-items: baseline; }
.sec h3 .c { font-family: ui-monospace, monospace; font-size: 11px;
             color: var(--color-neutral-600); }
.lead { font-size: 14px; max-width: 76ch; color: var(--color-neutral-800); }
.vrow { display: grid; grid-template-columns: 250px 1fr; gap: 20px; padding: 10px 0;
        border-bottom: 1px solid var(--color-divider); }
.vrow .f { font-family: ui-monospace, monospace; font-size: 12.5px; font-weight: 600;
           word-break: break-all; }
.vrow .src { font-family: ui-monospace, monospace; font-size: 10.5px;
             color: var(--color-neutral-600); }
.vals { display: flex; flex-wrap: wrap; gap: 5px; }
.vals .tag { font-family: ui-monospace, monospace; font-size: 10.5px; }
.note { font-size: 12px; max-width: 74ch; margin-top: 6px; color: var(--color-neutral-700); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.lock { border: 1px solid var(--color-divider); border-radius: 22px; padding: 14px 16px;
        background: var(--color-neutral-100); }
.lock .top { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.lock .rule { font-size: 13px; font-weight: 600; font-family: ui-monospace, monospace;
              word-break: break-word; }
.lock .why { font-size: 12.5px; color: var(--color-neutral-700); margin-top: 8px; }
.lock .src { font-size: 10.5px; font-family: ui-monospace, monospace; margin-top: 10px;
             padding-top: 8px; border-top: 1px solid var(--color-divider);
             color: var(--color-neutral-600); }
.kv { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 7px 12px;
      background: var(--color-neutral-100); border-radius: 14px; margin-bottom: 6px;
      align-items: center; }
.kv .k { font-family: ui-monospace, monospace; font-size: 11.5px; word-break: break-all; }
.counters { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 24px 0; }
.counter { border: 1px solid var(--color-divider); border-radius: 22px; padding: 16px;
           background: transparent; cursor: pointer; text-align: left; color: inherit;
           font-family: inherit; }
.counter b { font-family: var(--font-heading); font-weight: 400; font-size: 29px; display: block; }
.counter span { font-size: 12px; color: var(--color-neutral-700); }
.empty { padding: 14px 16px; border-radius: 16px; background: var(--color-accent-100);
         font-size: 13px; }
table.cfg { width: 100%; border-collapse: collapse; table-layout: fixed; }
table.cfg th { text-align: left; font-size: 11px; text-transform: uppercase;
               letter-spacing: .06em; color: var(--color-neutral-600); padding: 8px 10px;
               border-bottom: 1px solid var(--color-divider); }
table.cfg td { padding: 8px 10px; border-bottom: 1px solid var(--color-divider);
               font-size: 12.5px; vertical-align: top; word-break: break-word; }
#results { position: fixed; top: 74px; right: 34px; width: 520px; max-height: 70vh;
           overflow-y: auto; border-radius: 24px; z-index: 50; background: var(--color-bg);
           border: 1px solid var(--color-divider); padding: 8px; }
#results .r { display: grid; grid-template-columns: 112px 1fr; gap: 8px; padding: 7px 10px;
              border-radius: 14px; cursor: pointer; align-items: baseline; }
#results .r:hover { background: color-mix(in srgb, #201e1d 5%, transparent); }
#results .r .lbl { font-family: ui-monospace, monospace; font-size: 12px; }
#results .r .ctx { font-size: 11px; color: var(--color-neutral-600); }
:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
"""


_RENDERER = r"""
'use strict';
var D = JSON.parse(document.getElementById('config-data').textContent);

// Heurística de APRESENTAÇÃO, e a distinção importa: colore um valor pelo que ele costuma
// significar, não por autoridade do contrato. Valor novo cai em neutro — que é o comportamento
// certo, porque neutro não afirma nada. A cor informa; nunca decide.
var SAGE = ['verified','done','mitigated','accepted','active','ok','pass','conforme','approved',
            'implemented','none','inline','true'];
var TERRA = ['open','high','critical','deferred','rejected','error','fail','nao_conforme',
             'sensivel','pending_judgment','erro','dropped','segregated','deny'];
var OUT = ['medium','proposed','planned','in_progress','draft','inconclusivo','unverifiable',
           'findings','divergencias'];
function tagClass(v) {
  var s = String(v);
  if (SAGE.indexOf(s) >= 0) return 'tag tag-accent-2';
  if (TERRA.indexOf(s) >= 0) return 'tag tag-accent';
  if (OUT.indexOf(s) >= 0) return 'tag tag-outline';
  return 'tag tag-neutral';
}
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function tags(vals) {
  return '<div class="vals">' + (vals || []).map(function (v) {
    return '<span class="' + tagClass(v) + '">' + esc(v) + '</span>';
  }).join('') + '</div>';
}
function vazio(chave, alt) {
  var r = (D.empty_reasons || {})[chave];
  return '<div class="empty">' + esc(r || alt || 'declarado vazio') +
         ' — nenhum item nesta coleção. A razão é declarada, porque "nenhum" e "não consegui ' +
         'olhar" não podem sair iguais.</div>';
}

// Agrupa qualquer coleção por uma chave, sem a tela saber quais grupos existem: grupo novo num
// contrato aparece sozinho, exatamente como um valor novo.
function porGrupo(itens, chave) {
  var m = {}, ordem = [];
  (itens || []).forEach(function (i) {
    var g = i[chave] || '(sem grupo)';
    if (!m[g]) { m[g] = []; ordem.push(g); }
    m[g].push(i);
  });
  ordem.sort();
  return ordem.map(function (g) { return [g, m[g]]; });
}

var TELAS = [
  { id: 'constituicao', grupo: 'O núcleo', n: '01', rot: 'Constituição',
    sub: 'o que não é negociável', cont: function () { return D.consts.length; } },
  { id: 'vocabulario', grupo: 'O núcleo', n: '02', rot: 'Vocabulário fechado',
    sub: 'todo valor que o repositório aceita, por campo',
    cont: function () { return D.vocabulary.length; } },
  { id: 'gramatica', grupo: 'O núcleo', n: '03', rot: 'Gramática de ids',
    sub: 'as formas que um identificador pode ter',
    cont: function () { return D.grammar.length; } },
  { id: 'travas', grupo: 'O núcleo', n: '04', rot: 'Travas estruturais',
    sub: 'as combinações que o contrato torna inexpressáveis',
    cont: function () { return D.locks.length; } },
  { id: 'controle', grupo: 'A máquina', n: '05', rot: 'Plano de controle',
    sub: 'modos, caminhos protegidos e higiene de ambiente',
    cont: function () { return (D.control.execution_modes ?
      Object.keys(D.control.execution_modes).length : 0); } },
  { id: 'fiscais', grupo: 'A máquina', n: '06', rot: 'Fiscais e entrega',
    sub: 'quem confere o quê, e em que ordem',
    cont: function () { return D.fiscais.aggregated.length; } },
  { id: 'ambiente', grupo: 'A máquina', n: '07', rot: 'Ambiente e contratos',
    sub: 'o que está fixado fora dos contratos',
    cont: function () { return D.schemas.length; } },
  { id: 'regua', grupo: 'A máquina', n: '08', rot: 'Contrato de régua',
    sub: 'o outro lado da promessa, e o que ainda não cumpre',
    cont: function () { return D.suites.registry.length; } },
  { id: 'heranca', grupo: 'Ao derivar', n: '09', rot: 'Herança do derivado',
    sub: 'o que vem travado e o que nasce vazio',
    cont: function () { return D.inheritance.fill.length; } }
];

var VIEWS = {
  constituicao: function () {
    var h = '<p class="lead">Tudo nesta tela é <em>derivado</em> dos contratos em ' +
      '<span class="mono">harness/schemas/</span> no instante da geração. Nenhum valor foi ' +
      'transcrito: acrescentado um valor a um contrato, ele aparece aqui sem ninguém editar ' +
      'esta página.</p>';
    h += '<div class="counters">' + TELAS.slice(0, 6).map(function (t) {
      return '<button class="counter" data-go="' + t.id + '"><b>' + t.cont() + '</b><span>' +
             esc(t.rot) + '</span></button>';
    }).join('') + '</div>';
    h += '<div class="grid2"><div><h3>Valores travados por <span class="mono">const</span>' +
         '<span class="c">' + D.consts.length + '</span></h3>';
    h += D.consts.length ? D.consts.map(function (c) {
      return '<div class="kv"><span class="k">' + esc(c.field) + '</span><span class="' +
             tagClass(c.value) + ' mono">' + esc(String(c.value)) + '</span></div>';
    }).join('') : vazio('consts');
    h += '</div><div>';
    if (D.header_invariant) {
      h += '<div class="lock"><div class="top"><span class="tag tag-accent mono">invariante</span>' +
        '<span class="tag tag-outline mono">oneOf</span></div><div class="rule">' +
        esc(D.header_invariant.fields.join(' / ')) + '</div>' +
        (D.header_invariant.why ? '<div class="why">' + esc(D.header_invariant.why) + '</div>' : '') +
        '<div class="src">presente em ' + D.header_invariant.present_in.length +
        ' contratos · ausente em ' + D.header_invariant.absent_in.length + ' (' +
        esc(D.header_invariant.absent_in.join(', ')) + ')</div></div>';
    }
    h += '<div class="lock" style="margin-top:14px"><div class="top">' +
      '<span class="tag tag-accent mono">exit</span></div>' +
      '<div class="rule">0 conforme · 1 divergência · 2 fiscal cego</div>' +
      '<div class="why">Um validador que passa por não ter conseguido rodar seria a trava que o ' +
      'vigiado desliga sem tocar em nada. Por isso 2 existe e nunca colapsa em 0.</div></div>';
    h += '</div></div>';
    return h;
  },

  vocabulario: function () {
    if (!D.vocabulary.length) return vazio('vocabulary');
    var h = '<p class="lead">Cada campo abaixo tem um vocabulário fechado: o contrato recusa ' +
      'qualquer valor fora da lista. Escalas com os mesmos rótulos aparecem mais de uma vez de ' +
      'propósito — são escalas distintas, e fundi-las apagaria essa informação.</p>';
    porGrupo(D.vocabulary, 'group').forEach(function (par) {
      h += '<h3>' + esc(par[0]) + '<span class="c">' + par[1].length + '</span></h3>';
      h += par[1].map(function (v) {
        return '<div class="vrow"><div><div class="f">' + esc(v.field) + '</div>' +
          '<div class="src">' + esc(v.file) + '</div></div><div>' + tags(v.values) +
          (v.note ? '<div class="note">' + esc(v.note) + '</div>' : '') + '</div></div>';
      }).join('');
    });
    return h;
  },

  gramatica: function () {
    if (!D.grammar.length) return vazio('grammar');
    var comEx = D.grammar.filter(function (g) { return g.example; }).length;
    var h = '<p class="lead">As formas que um identificador pode ter, deduplicadas pela regex. ' +
      'A coluna <em>exemplo</em> só aparece quando existe uma instância real neste repositório (' +
      comEx + ' de ' + D.grammar.length + '): um exemplo que casasse a regex mas não existisse ' +
      'aqui seria invenção com cara de documentação.</p>';
    h += '<table class="cfg"><colgroup><col style="width:330px"><col style="width:190px">' +
      '<col></colgroup><thead><tr><th>Regex</th><th>Exemplo real</th><th>Onde vale</th></tr>' +
      '</thead><tbody>';
    h += D.grammar.map(function (g) {
      return '<tr><td class="mono" style="font-size:11px;word-break:break-all">' +
        esc(g.pattern) + '</td><td class="mono">' +
        (g.example ? esc(g.example) : '<span class="text-muted">— sem instância</span>') +
        '</td><td>' + g.used_in.map(function (u) {
          return '<div class="mono" style="font-size:10.5px">' + esc(u.file) + ' · ' +
                 esc(u.field) + '</div>';
        }).join('') + '</td></tr>';
    }).join('');
    return h + '</tbody></table>';
  },

  travas: function () {
    if (!D.locks.length) return vazio('locks');
    var semPorque = D.locks.filter(function (l) { return !l.why; }).length;
    var h = '<p class="lead">Cada card é uma combinação que o contrato torna <em>inexpressável</em>' +
      '. A regra é sintetizada da estrutura do bloco; o porquê vem do <span class="mono">comment' +
      '</span> do próprio contrato. ' + semPorque + ' de ' + D.locks.length + ' não declaram ' +
      'porquê — e o lugar de escrever isso é o contrato, não uma glosa paralela.</p>';
    h += '<div class="grid2">' + D.locks.map(function (l) {
      return '<div class="lock"><div class="top"><span class="tag tag-outline mono">' +
        esc(l.block_kind) + '</span><span class="tag tag-neutral mono">' + esc(l.group) +
        '</span></div><div class="rule">' + esc(l.rule) + '</div>' +
        (l.why ? '<div class="why">' + esc(l.why) + '</div>'
               : '<div class="why text-muted">sem porquê declarado no contrato</div>') +
        '<div class="src">' + esc(l.file) + ' · ' + esc(l.pointer) + '</div></div>';
    }).join('') + '</div>';
    return h;
  },

  controle: function () {
    var c = D.control, e = c.env_hygiene;
    var h = '<h3>Política de decisão<span class="c">' +
      Object.keys(c.decision_policy || {}).length + '</span></h3><div class="grid2"><div>';
    Object.keys(c.decision_policy || {}).sort().forEach(function (k) {
      h += '<div class="kv"><span class="k">' + esc(k) + '</span><span class="' +
        tagClass(c.decision_policy[k]) + ' mono">' + esc(c.decision_policy[k]) + '</span></div>';
    });
    h += '</div><div><div class="lock"><div class="rule">Caminhos protegidos</div>' +
      tags((c.repository || {}).protected_paths) +
      '<div class="why">O fiscal real é CODEOWNERS mais branch protection; esta lista é a ' +
      'declaração.</div></div></div></div>';

    h += '<h3>Modos de execução<span class="c">' +
      Object.keys(c.execution_modes || {}).length + '</span></h3>';
    h += '<table class="cfg"><thead><tr><th>Modo</th><th>Rede</th><th>Auth</th>' +
      '<th>Agente dispara</th><th>Job</th><th>Natureza</th></tr></thead><tbody>';
    Object.keys(c.execution_modes || {}).forEach(function (m) {
      var v = c.execution_modes[m];
      h += '<tr><td class="mono">' + esc(m) + '</td><td>' + esc(v.network) + '</td><td>' +
        esc(v.requires_auth) + '</td><td>' + esc(v.agent_may_trigger) + '</td><td><span class="' +
        tagClass(v.job) + ' mono">' + esc(v.job) + '</span></td><td>' + esc(v.note) + '</td></tr>';
    });
    h += '</tbody></table>';

    h += '<h3>Higiene de ambiente<span class="c">' + e.denylist_prefix_efetiva.length + ' + ' +
      e.familias.reduce(function (a, f) { return a + f.vars.length; }, 0) + '</span></h3>';
    h += '<div class="grid2"><div><div class="lock"><div class="rule">Denylist por prefixo — ' +
      'EFETIVA</div>' + tags(e.denylist_prefix_efetiva) +
      '<div class="why">O YAML declara <span class="mono">' +
      JSON.stringify(e.denylist_prefix_declarado) + '</span>: vazia <em>por derivação</em>. Os ' +
      'prefixos nascem das fichas de régua — ' +
      e.prefix_origem.map(function (o) { return esc(o.prefix) + ' de ' + esc(o.from); }).join('; ') +
      '. Mostrar só o YAML diria que nada é negado.</div></div>' +
      '<div class="lock" style="margin-top:14px"><div class="rule">Allowlist</div>' +
      tags(e.allowlist) + '</div></div><div>';
    e.familias.forEach(function (f) {
      h += '<div class="lock" style="margin-bottom:12px"><div class="rule">' + esc(f.family) +
        '</div>' + tags(f.vars) + '</div>';
    });
    (e.exceptions || []).forEach(function (x) {
      h += '<div class="lock" style="background:var(--color-accent-2-100)">' +
        '<div class="rule">exceção declarada: ' + esc(x.name) + ' (' + esc(x.context) + ')</div>' +
        '<div class="why">' + esc(x.justification) + '</div></div>';
    });
    h += '</div></div>';
    return h;
  },

  fiscais: function () {
    var a = D.fiscais.aggregated;
    var h = '<p class="lead">Os ' + a.length + ' fiscais do agregado saem do <span class="mono">' +
      'return</span> de <span class="mono">ci/validate_all.py::_steps()</span>, lido por AST. ' +
      'A contagem é <span class="mono">len()</span> — se fosse um número escrito, ela mentiria ' +
      'no dia seguinte a alguém acrescentar um passo.</p>';
    h += '<h3>Agregados<span class="c">' + a.length + '</span></h3>';
    h += '<table class="cfg"><colgroup><col style="width:170px"><col style="width:220px">' +
      '<col style="width:90px"><col></colgroup><thead><tr><th>Etapa</th><th>Módulo</th>' +
      '<th>argv</th><th>O que faz</th></tr></thead><tbody>';
    h += a.map(function (f) {
      return '<tr><td class="mono">' + esc(f.step) + '</td><td class="mono">' + esc(f.module) +
        '</td><td class="mono">' + esc((f.argv || []).join(' ')) + '</td><td>' +
        esc(f.doc || '') + '</td></tr>';
    }).join('') + '</tbody></table>';
    h += '<h3>Fora do agregado<span class="c">' + D.fiscais.standalone.length + '</span></h3>' +
      '<div class="cards">' + D.fiscais.standalone.map(function (f) {
        return '<div class="lock"><div class="rule mono" style="font-size:12px">' +
          esc(f.module) + '</div><div class="why">' + esc(f.doc || '') + '</div></div>';
      }).join('') + '</div>';
    h += '<h3>Hooks<span class="c">' + D.environment.hooks.length + '</span></h3>' +
      '<table class="cfg"><thead><tr><th>Evento</th><th>Matcher</th><th>Comando</th>' +
      '<th>Timeout</th></tr></thead><tbody>' + D.environment.hooks.map(function (k) {
        return '<tr><td class="mono">' + esc(k.event) + '</td><td class="mono">' +
          esc(k.matcher || '—') + '</td><td class="mono">' + esc(k.command) + '</td><td>' +
          esc(k.timeout) + 's</td></tr>';
      }).join('') + '</tbody></table>';
    return h;
  },

  ambiente: function () {
    var e = D.environment;
    var h = '<div class="grid2"><div><h3>Ambiente declarado<span class="c">' +
      e.pins.length + '</span></h3>';
    ['python', 'testpaths', 'pythonpath'].forEach(function (k) {
      if (e[k]) h += '<div class="kv"><span class="k">' + k + '</span><span class="tag ' +
        'tag-neutral mono">' + esc(e[k]) + '</span></div>';
    });
    h += '<div class="kv"><span class="k">versão do padrão</span><span class="tag tag-outline ' +
      'mono">' + esc(e.version_source) + '</span></div>' +
      '<div class="note">O número da versão do padrão não aparece aqui, e essa ausência é a ' +
      'decisão: ele tem fonte única, e restatá-lo criaria a segunda cópia que diverge.</div>';
    h += '</div><div><h3>Pins declarados<span class="c">' + e.pins.length + '</span></h3>' +
      tags(e.pins.map(function (p) { return p.spec; })) + '</div></div>';
    h += '<h3>Contratos<span class="c">' + D.schemas.length + '</span></h3><div class="cards">' +
      D.schemas.map(function (s) {
        return '<div class="lock"><div class="rule mono" style="font-size:11.5px">' +
          esc(s.file) + '</div><div class="why">' + esc(s.title || '') + '</div>' +
          '<div class="src">' + s.bytes + ' bytes · <span class="tag tag-neutral">' +
          esc(s.group) + '</span></div></div>';
      }).join('') + '</div>';
    return h;
  },

  regua: function () {
    var s = D.suites;
    if (!s.registry.length) return vazio('registry');
    var h = '<h3>Fichas<span class="c">' + s.registry.length + '</span></h3><div class="grid2">';
    h += s.registry.map(function (f) {
      return '<div class="lock"><div class="top"><span class="rule">' + esc(f.nome) +
        '</span><span class="' + tagClass(f.status) + '">' + esc(f.status) + '</span></div>' +
        '<div class="kv"><span class="k">entrypoint</span><span class="mono">' +
        (f.entrypoint ? esc(f.entrypoint)
                      : (f.entrypoint_proibido ? '— proibido em planned' : '—')) + '</span></div>' +
        '<div class="kv"><span class="k">env_prefix</span><span class="tag tag-accent mono">' +
        esc(f.env_prefix) + '*</span></div>' +
        '<div class="kv"><span class="k">pin</span><span class="mono">' + esc(f.pin_source) +
        '</span></div>' + tags(f.modes) + '</div>';
    }).join('') + '</div>';
    h += '<h3>Gaps<span class="c">' + s.gaps.length + '</span></h3>';
    h += s.gaps.length ? '<table class="cfg"><thead><tr><th>Id</th><th>Régua</th>' +
      '<th>O que falta</th><th>Vence</th></tr></thead><tbody>' + s.gaps.map(function (g) {
        return '<tr><td class="mono">' + esc(g.id) + '</td><td class="mono">' + esc(g.suite) +
          '</td><td>' + esc(g.what || g.descricao || g.description || '') + '</td>' +
          '<td class="mono">' + esc(g.due || '') + '</td></tr>';
      }).join('') + '</tbody></table>' : vazio('gaps');
    return h;
  },

  heranca: function () {
    var i = D.inheritance;
    var derivado = i.kind === 'derived';
    var h = '<p class="lead">Este repositório é <span class="tag tag-accent-2 mono">' +
      esc(i.kind) + '</span>. ' + (derivado
        ? 'Como derivado, a coluna da direita é o que já foi preenchido, e por qual fase.'
        : 'Como molde, a coluna da direita é o que um derivado precisará preencher.') + '</p>';
    h += '<div class="grid2"><div><h3>Vem travado<span class="c">' + i.fixed.length +
      '</span></h3>' + i.fixed.map(function (f) {
        return '<div class="lock" style="background:var(--color-accent-2-100);margin-bottom:8px">' +
          '<div class="rule" style="font-size:12px">' + esc(f.o_que) + '</div>' +
          '<div class="why">' + esc(f.porque) + '</div></div>';
      }).join('') + '</div>';
    h += '<div><h3>' + (derivado ? 'Já preenchido' : 'Nasce vazio') + '<span class="c">' +
      i.fill.length + '</span></h3>' + (i.fill.length ? i.fill.map(function (f) {
        return '<div class="lock" style="margin-bottom:8px"><div class="rule mono" ' +
          'style="font-size:11.5px">' + esc(f.artefato) + '</div><div class="top">' +
          '<span class="tag tag-outline mono">' + esc(f.quando) + '</span></div>' +
          '<div class="why">' + esc(f.como) + '</div></div>';
      }).join('') : vazio('fill')) + '</div></div>';
    return h;
  }
};

// Índice de busca: varredura genérica das coleções. Coleção nova entra no índice e passa a ser
// buscável sem ninguém tocar na UI — mesma propriedade do resto do painel.
var INDICE = null;
function indice() {
  if (INDICE) return INDICE;
  INDICE = [];
  function add(tela, lbl, ctx) { INDICE.push({ t: tela, l: String(lbl), c: String(ctx || '') }); }
  D.vocabulary.forEach(function (v) {
    add('vocabulario', v.field, v.file);
    v.values.forEach(function (x) { add('vocabulario', x, v.field + ' · ' + v.file); });
  });
  D.grammar.forEach(function (g) { add('gramatica', g.pattern, g.used_in[0].field); });
  D.consts.forEach(function (c) { add('constituicao', c.field, String(c.value)); });
  D.locks.forEach(function (l) { add('travas', l.rule, l.file); });
  D.schemas.forEach(function (s) { add('ambiente', s.file, s.title || ''); });
  D.fiscais.aggregated.forEach(function (f) { add('fiscais', f.module, f.step); });
  D.fiscais.standalone.forEach(function (f) { add('fiscais', f.module, 'fora do agregado'); });
  (D.control.env_hygiene.familias || []).forEach(function (f) {
    f.vars.forEach(function (v) { add('controle', v, f.family); });
  });
  ((D.control.repository || {}).protected_paths || []).forEach(function (p) {
    add('controle', p, 'caminho protegido');
  });
  D.environment.pins.forEach(function (p) { add('ambiente', p.spec, p.file); });
  D.environment.workflows.forEach(function (w) { add('fiscais', w, 'workflow'); });
  Object.keys(D.control.execution_modes || {}).forEach(function (m) {
    add('controle', m, 'modo de execução');
  });
  ((D.suites.contract || {}).clauses || []).forEach(function (c) {
    add('regua', c.id || c, (c.title || ''));
  });
  D.suites.registry.forEach(function (s) { add('regua', s.nome, s.status); });
  D.suites.gaps.forEach(function (g) { add('regua', g.id, g.suite); });
  D.inheritance.fill.forEach(function (f) { add('heranca', f.artefato, f.quando); });
  return INDICE;
}

var sec = 'constituicao', q = '';

function pintar() {
  var tela = TELAS.filter(function (t) { return t.id === sec; })[0] || TELAS[0];
  document.getElementById('nav').innerHTML = (function () {
    var out = '', ultimo = null;
    TELAS.forEach(function (t) {
      if (t.grupo !== ultimo) { out += '<div class="navgroup">' + esc(t.grupo) + '</div>';
                                ultimo = t.grupo; }
      out += '<button class="navitem" data-go="' + t.id + '" aria-current="' +
        (t.id === sec) + '"><span class="n">' + t.n + '</span><span class="l">' + esc(t.rot) +
        '</span><span class="c">' + t.cont() + '</span></button>';
    });
    return out;
  })();
  document.getElementById('titulo').textContent = tela.rot;
  document.getElementById('sub').textContent = tela.sub;
  document.getElementById('main').innerHTML = '<div class="sec">' + VIEWS[tela.id]() + '</div>';

  var box = document.getElementById('results');
  if (q.length < 2) { box.hidden = true; box.innerHTML = ''; }
  else {
    var alvo = q.toLowerCase();
    var hits = indice().filter(function (r) {
      return r.l.toLowerCase().indexOf(alvo) >= 0 || r.c.toLowerCase().indexOf(alvo) >= 0;
    }).slice(0, 22);
    box.hidden = false;
    box.innerHTML = '<div class="navgroup">' + hits.length + ' resultado(s)</div>' +
      hits.map(function (r) {
        var t = TELAS.filter(function (x) { return x.id === r.t; })[0];
        return '<div class="r" data-go="' + r.t + '"><span class="tag tag-neutral">' +
          esc(t ? t.rot : r.t) + '</span><span><span class="lbl">' + esc(r.l) +
          '</span><br><span class="ctx">' + esc(r.c) + '</span></span></div>';
      }).join('');
  }
}

function ir(id) {
  if (!VIEWS[id]) return;
  sec = id; q = ''; document.getElementById('q').value = '';
  history.replaceState(null, '', '#/' + id);
  window.scrollTo(0, 0);
  pintar();
}

document.addEventListener('click', function (ev) {
  var alvo = ev.target.closest('[data-go]');
  if (alvo) ir(alvo.getAttribute('data-go'));
});
document.getElementById('q').addEventListener('input', function (ev) {
  q = ev.target.value; pintar();
});
window.addEventListener('hashchange', function () {
  var id = location.hash.replace('#/', '');
  if (VIEWS[id] && id !== sec) { sec = id; pintar(); }
});

var inicial = location.hash.replace('#/', '');
if (VIEWS[inicial]) sec = inicial;
document.getElementById('marca-sub').textContent = 'o que já está decidido';
document.getElementById('proc').innerHTML =
  '<div class="mono">' + esc(D.provenance.repository) + '</div>' +
  '<div class="mono">árvore ' + esc(D.provenance.inputs_fingerprint.slice(7, 19)) + '</div>' +
  '<div>' + D.provenance.inputs.length + ' arquivos lidos</div>';
pintar();
"""


# ══════════════════════════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Painel de configuração do repositório, derivado dos contratos.")
    parser.add_argument("--check", action="store_true",
                        help="não escreve; falha se o artefato estiver desatualizado")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if _FALTA is not None:
        print(f"✗ configuração: dependência ausente ({_FALTA}). "
              f"Próximo passo: python ci/bootstrap.py", file=sys.stderr)
        return 2

    try:
        dados = coletar()
        html = render_html(dados)
        payload = payload_json(dados)
        erros = hl.schema_errors(DADOS, SCHEMA, dados)
        if erros:
            raise hl.HarnessError(
                "o artefato não satisfaz o próprio contrato: " + "; ".join(erros))
    except hl.HarnessError as exc:
        print(f"✗ configuração: {exc}", file=sys.stderr)
        return 2

    if args.stdout:
        print(payload)
        return 0

    if args.check:
        atual_html = hl.read_text(HTML) if hl.rel_exists(HTML) else None
        atual_json = hl.read_text(DADOS) if hl.rel_exists(DADOS) else None
        divergentes = [rel for rel, atual, novo in
                       ((HTML, atual_html, html), (DADOS, atual_json, payload))
                       if atual != novo]
        if divergentes:
            print(f"✗ {', '.join(divergentes)} desatualizado — rode: python {GERADOR}",
                  file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"✓ {HTML} em dia.")
        return 0

    destino = hl.REPO / HTML
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    (hl.REPO / DADOS).write_text(payload, encoding="utf-8")
    if not args.quiet:
        print(f"✓ escrito {HTML} e {DADOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
