#!/usr/bin/env python3
"""Gera o relatório do repositório: uma vista de leitura do que hoje exige abrir 28 YAMLs.

Artefato DERIVADO, nunca fonte: lê o metadado declarado e emite `docs/relatorio/report.json`
(a interface, para quem consome) e `docs/relatorio/index.html` (a vista, para quem lê). Os dois
saem sempre juntos — o JSON é o contrato e o HTML é uma projeção dele, então gerar um sem o outro
produziria duas descrições que derivam em silêncio.

O QUE ESTE GERADOR NÃO CONTÉM, e é a decisão central (CP-045, ADR-031):

    Ele não contém a informação, ele a deriva.

Nenhuma lista escrita à mão aqui dentro. Nenhum identificador literal. Nenhum contador escrito na
tela. Todo número é `len()` de uma coleção real, toda coleção vem de um caminho declarado, e a
tabela de caminhos abaixo é o único acoplamento admitido — porque *o caminho é o contrato, o
conteúdo é dado*.

A armadilha é imediata e já se mediu neste repositório: `CLAUDE.md` afirma "as treze etapas" e
`harness/stages.yaml` tem catorze. O documento passou a mentir na etapa que alguém acrescentou sem
reler a prosa, e nada o fiscalizava. Esta tela será a mais lida do repositório; se ela restatar
contadores, multiplica esse defeito por vinte. É por isso que a asserção do ADR recusa identificador
literal aqui dentro, e não é regra de estilo.

Uso:
  python ci/generate_report.py             # escreve os dois artefatos
  python ci/generate_report.py --check     # sai 1 se o que está na árvore está desatualizado
  python ci/generate_report.py --redigir   # troca os campos do inventário por contagens
  python ci/generate_report.py --stdout    # imprime o JSON
  python ci/generate_report.py --quiet     # só fala em caso de falha
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

# O ÚNICO leitor: reimplementar leitura criaria a segunda descrição, que deriva em silêncio.
#
# O import é guardado porque um clone fresco não tem pyyaml (extra `[dev]`), e sem a guarda este
# módulo morreria de ImportError ANTES de conseguir dizer o que fazer — com traceback e exit 1,
# que é o código de "encontrei divergência". Quem mais precisa da mensagem é exatamente quem
# acabou de clonar, e "não consegui fiscalizar" nunca pode se parecer com "fiscalizei e reprovei".
try:
    import harness_lib as hl
except ImportError as exc:  # pragma: no cover - exercitado por subprocesso na mordida
    hl = None
    _ERRO_IMPORT: ImportError | None = exc
else:
    _ERRO_IMPORT = None

SAIDA_DIR = "docs/relatorio"
SAIDA_JSON = f"{SAIDA_DIR}/report.json"
SAIDA_HTML = f"{SAIDA_DIR}/index.html"

AVISO = "GENERATED: não editar; rodar ci/generate_report.py"

EXIT_OK = 0
EXIT_DESATUALIZADO = 1
EXIT_CEGO = 2

# Os três estados do vazio, e nunca se pintam igual. "nenhum" e "não sei olhar" saindo iguais na
# tela é o estado em que alguém avança achando que não há trabalho — a família de defeito da CP-040,
# e o motivo de RISK-INCUBA-001 continuar aberto.
VAZIO_DECLARADO = "declarado vazio"
VAZIO_NAO_INGERIDO = "ainda não ingerido"
VAZIO_ILEGIVEL = "não consegui ler"


class FonteIlegivel(Exception):
    """Não consegui fiscalizar — exit 2, jamais 0.

    Separada de "declarado vazio" de propósito: um fiscal que trata fonte ilegível como coleção
    vazia responde "nada a ver aqui" quando a resposta honesta é "não sei olhar".
    """


# --------------------------------------------------------------------------------------
# As fontes. O caminho é o contrato; o conteúdo é dado.
# --------------------------------------------------------------------------------------
# (chave da coleção, caminho, caminho-de-chave dentro do documento)
# Um caminho-de-chave com ponto desce no documento. A chave AUSENTE é erro, não vazio — ver _colecao.
FONTES_YAML: tuple[tuple[str, str, str], ...] = (
    ("metrics", "business/vision.yaml", "product.success_metrics"),
    ("capabilities", "business/capabilities.yaml", "capabilities"),
    ("requirements", "business/requirements/backlog.yaml", "items"),
    ("components", "architecture/components.yaml", "components"),
    ("interfaces", "architecture/interfaces.yaml", "interfaces"),
    ("adrs", "architecture/adr/index.yaml", "adrs"),
    ("ui_surfaces", "design/ui-surfaces.yaml", "ui_surfaces"),
    ("risks", "governance/risk-register.yaml", "risks"),
    ("threats", "security/threat-model.yaml", "threats"),
    ("dependencies", "security/dependencies.yaml", "dependencies"),
    ("stages", "harness/stages.yaml", "stages"),
    ("ingest_phases", "harness/pipeline/ingest.yaml", "phases"),
)

# Coleções que vêm de um diretório, não de um arquivo. O glob é o contrato.
FONTES_GLOB: tuple[tuple[str, str], ...] = (
    ("rules", "business/rules/*.yaml"),
    ("change_proposals", "harness/change-proposals/*.yaml"),
    ("policies", "harness/policies/*.md"),
    ("agents", "harness/agents/*/AGENT.md"),
    ("releases", "harness/releases/*.manifest.json"),
    ("schemas", "harness/schemas/*.json"),
    ("workflows", ".github/workflows/*.yml"),
)

# Documentos lidos inteiros, para os blocos que não são coleção.
DOCS_AVULSOS: tuple[str, ...] = (
    "project.yaml",
    "harness/harness.yaml",
    "governance/data-inventory.yaml",
    "governance/privacy-review.yaml",
    "governance/conformance-review.yaml",
    "design/design-system.yaml",
    "tests/qa/config.yaml",
)


def _desce(doc: Any, caminho: str, rel: str) -> Any:
    """Desce um caminho-de-chave, distinguindo ausência de vazio.

    Chave ausente levanta. É a recusa do idioma `.get(x) or []`, que converte *não declarado* em
    *declarado vazio* — e num fiscal essa diferença é a diferença entre indeterminação e permissão.
    """
    atual = doc
    for parte in caminho.split("."):
        if not isinstance(atual, dict):
            raise FonteIlegivel(f"FISCAL_CEGO: {rel} não é um mapa em {parte!r}")
        if parte not in atual:
            raise FonteIlegivel(
                f"FISCAL_CEGO: {rel} não declara {caminho!r} — chave ausente não é lista vazia, "
                f"e tratá-las igual transformaria 'não sei' em 'nada a declarar'")
        atual = atual[parte]
    return atual


def _colecao(rel: str, caminho_chave: str) -> tuple[list[dict], str | None]:
    """Uma coleção e, se vazia, a RAZÃO do vazio. Nunca um zero solto."""
    if not hl.rel_exists(rel):
        return [], VAZIO_NAO_INGERIDO
    try:
        doc = hl.read_yaml(rel)
    except Exception as exc:  # HarnessError, erro de parse — a distinção não muda a resposta
        raise FonteIlegivel(f"FISCAL_CEGO: {rel} ilegível: {exc}") from exc
    if doc is None:
        return [], VAZIO_DECLARADO
    itens = _desce(doc, caminho_chave, rel)
    if itens is None:
        return [], VAZIO_DECLARADO
    if not isinstance(itens, list):
        raise FonteIlegivel(f"FISCAL_CEGO: {rel}:{caminho_chave} não é lista")
    limpos = [x for x in itens if isinstance(x, dict)]
    return limpos, (VAZIO_DECLARADO if not limpos else None)


def _fiscalizado_por(texto: str) -> list[str]:
    """Extrai o rodapé `Fiscalizado por:` de uma política, sem restatar a tabela do README."""
    achados: list[str] = []
    for linha in texto.splitlines():
        corte = linha.partition("Fiscalizado por:")
        if corte[1]:
            valor = corte[2].strip().strip("`*_ ")
            if valor:
                achados.append(valor)
    return achados


def _raiz_do_glob(padrao: str) -> str:
    """O diretório antes do primeiro curinga — para saber se o vazio é declarado ou não-ingerido."""
    partes = []
    for parte in padrao.split("/"):
        if "*" in parte or "?" in parte or "[" in parte:
            break
        partes.append(parte)
    return "/".join(partes)


def _por_glob(chave: str, padrao: str) -> tuple[list[dict], str | None]:
    """Coleções que moram num diretório. Ordenadas por caminho — determinismo antes de estética.

    O vazio aqui tem DUAS causas e elas não se confundem: um diretório que existe e não tem nada
    dentro é uma declaração ("não há releases publicadas"); um diretório que não existe é ingestão
    que não aconteceu. Pintá-los igual é a família de defeito da CP-040, e num derivado recém-criado
    — que é quem mais abre esta tela — quase tudo cai no segundo caso.
    """
    caminhos = sorted(hl.resolve_glob(padrao), key=lambda p: hl.rel(p))
    if not caminhos:
        raiz = _raiz_do_glob(padrao)
        return [], (VAZIO_DECLARADO if hl.rel_exists(raiz) else VAZIO_NAO_INGERIDO)
    itens: list[dict] = []
    for p in caminhos:
        rel = hl.rel(p)
        try:
            if p.suffix == ".md":
                texto = hl.read_text(rel)
                titulo = next((ln.lstrip("# ").strip() for ln in texto.splitlines()
                               if ln.startswith("#")), p.stem)
                itens.append({"id": p.stem, "path": rel, "title": titulo,
                              "enforced_by": _fiscalizado_por(texto)})
            elif p.suffix == ".json":
                doc = hl.read_json(rel)
                nome = doc.get("$id") if isinstance(doc, dict) else None
                itens.append({"id": p.stem, "path": rel,
                              "title": nome if isinstance(nome, str) else p.stem})
            else:
                doc = hl.read_yaml(rel)
                if not isinstance(doc, dict):
                    itens.append({"id": p.stem, "path": rel, "title": p.stem})
                    continue
                # Uma proposta declara-se em `proposal`; uma regra em `rules`. Descobrir qual é
                # olhando o documento evita uma tabela paralela de "que forma tem cada arquivo".
                if "proposal" in doc and isinstance(doc["proposal"], dict):
                    prop = doc["proposal"]
                    itens.append({"id": prop.get("id", p.stem), "path": rel,
                                  "title": prop.get("title", p.stem),
                                  "status": prop.get("status"),
                                  "level": (prop.get("risk_assessment") or {}).get("level")
                                  if isinstance(prop.get("risk_assessment"), dict) else None,
                                  "created_at": prop.get("created_at")})
                elif "rules" in doc and isinstance(doc["rules"], list):
                    for r in doc["rules"]:
                        if isinstance(r, dict):
                            itens.append({**r, "path": rel})
                else:
                    itens.append({"id": p.stem, "path": rel, "title": p.stem})
        except FonteIlegivel:
            raise
        except Exception as exc:
            raise FonteIlegivel(f"FISCAL_CEGO: {rel} ilegível: {exc}") from exc
    return itens, (VAZIO_DECLARADO if not itens else None)


def _ultimo_laudo() -> dict:
    """O resultado da última execução dos fiscais, lido de `harness/reports/` COM a data.

    Executar os fiscais aqui dentro seria circular — `validate_all` chama este gerador com
    `--check`, que chamaria `validate_all`. O ciclo se quebra lendo o laudo já produzido e
    ROTULANDO-O: número velho rotulado é honesto, número velho sem rótulo não é.
    """
    caminhos = sorted(hl.resolve_glob("harness/reports/*.json"), key=lambda p: hl.rel(p))
    if not caminhos:
        return {"disponivel": False, "razao": VAZIO_NAO_INGERIDO}
    ultimo = caminhos[-1]
    rel = hl.rel(ultimo)
    try:
        doc = hl.read_json(rel)
    except Exception as exc:
        raise FonteIlegivel(f"FISCAL_CEGO: {rel} ilegível: {exc}") from exc
    if not isinstance(doc, dict):
        return {"disponivel": False, "razao": VAZIO_ILEGIVEL, "path": rel}
    return {"disponivel": True, "path": rel,
            "generated_at": doc.get("generated_at"), "summary": doc.get("summary")}


def _inventario(doc: Any, redigir: bool) -> dict:
    """O inventário de dado pessoal — e a decisão de privacidade que não pode ser default.

    No molde ele está vazio. Num derivado, contém finalidades, campos e bases legais do alvo: um
    HTML publicado com isso não vaza o dado do titular, vaza o MAPA de onde ele está, que é o que
    se procura primeiro. Com `--redigir`, os campos viram contagens.
    """
    if not isinstance(doc, dict):
        return {"disponivel": False, "razao": VAZIO_NAO_INGERIDO}
    campos = doc.get("fields")
    finalidades = doc.get("purposes")
    campos = campos if isinstance(campos, list) else []
    finalidades = finalidades if isinstance(finalidades, list) else []
    base = {
        "redigido": redigir,
        "total_campos": len(campos),
        "total_finalidades": len(finalidades),
        "vazio_declarado": not campos and not finalidades,
    }
    if redigir:
        return base
    return {**base,
            "purposes": [p for p in finalidades if isinstance(p, dict)],
            "fields": [c for c in campos if isinstance(c, dict)]}


def coletar(redigir: bool = False) -> dict:
    """Lê tudo e monta o relatório. Determinístico: nada de relógio, nada de conjunto sem ordenar."""
    colecoes: dict[str, list[dict]] = {}
    razoes: dict[str, str] = {}
    lidos: list[str] = []

    for chave, rel, caminho_chave in FONTES_YAML:
        itens, razao = _colecao(rel, caminho_chave)
        colecoes[chave] = itens
        if razao:
            razoes[chave] = razao
        if hl.rel_exists(rel):
            lidos.append(rel)

    for chave, padrao in FONTES_GLOB:
        itens, razao = _por_glob(chave, padrao)
        colecoes[chave] = itens
        if razao:
            razoes[chave] = razao
        lidos.extend(sorted(hl.rel(p) for p in hl.resolve_glob(padrao)))

    docs: dict[str, Any] = {}
    for rel in DOCS_AVULSOS:
        if not hl.rel_exists(rel):
            docs[rel] = None
            continue
        try:
            docs[rel] = hl.read_yaml(rel)
        except Exception as exc:
            raise FonteIlegivel(f"FISCAL_CEGO: {rel} ilegível: {exc}") from exc
        lidos.append(rel)

    projeto_doc = docs.get("project.yaml")
    projeto = projeto_doc.get("project", {}) if isinstance(projeto_doc, dict) else {}

    pin, erros_pin = hl.exact_pin()
    if erros_pin:
        raise FonteIlegivel(f"FISCAL_CEGO: pin do padrão ilegível: {'; '.join(erros_pin)}")

    priv = docs.get("governance/privacy-review.yaml")
    conf = docs.get("governance/conformance-review.yaml")

    def _fingerprint(doc: Any) -> str | None:
        if not isinstance(doc, dict):
            return None
        review = doc.get("review")
        if not isinstance(review, dict):
            return None
        valor = review.get("scope_fingerprint")
        return valor if isinstance(valor, str) else None

    lidos_unicos = sorted(set(lidos))

    relatorio = {
        "schema_version": "1.0",
        "metadata_version": "1.0",
        "source_of_truth": False,
        "generated_from": lidos_unicos,
        "provenance": {
            "repository": projeto.get("repository") or projeto.get("name"),
            "kind": projeto.get("kind"),
            # O SHA do commit NÃO entra aqui, e a ausência é decisão. Embutir o HEAD tornaria o
            # artefato diferente a cada commit: gera, commita, o HEAD muda, `--check` reprova,
            # regenera — o laço que a §6 do handoff descreve como "transformar o --check em ruído
            # que as pessoas acabam desligando". O que identifica o estado do metadado é o digest
            # das fontes, que é determinístico e mais preciso que o commit: dois commits que não
            # tocam metadado têm o mesmo digest, e é isso que se quer comparar.
            "sources_digest": hl.fingerprint(
                (rel, hl.sha256_file(hl.REPO / rel)) for rel in lidos_unicos),
            "standard": {"version_source": "requirements-qa.txt", "pin_declared": bool(pin)},
            "fingerprints": {"privacy_review": _fingerprint(priv),
                             "conformance_review": _fingerprint(conf)},
        },
        "project": {
            "name": projeto.get("name"),
            "kind": projeto.get("kind"),
            "description": projeto.get("description"),
            "owners": projeto.get("owners") if isinstance(projeto.get("owners"), list) else [],
        },
        "collections": {k: colecoes[k] for k in sorted(colecoes)},
        "counts": {k: len(v) for k, v in sorted(colecoes.items())},
        "computed": {
            "last_report": _ultimo_laudo(),
            "inventory": _inventario(docs.get("governance/data-inventory.yaml"), redigir),
            "risk_matrix": _matriz(colecoes["risks"]),
            "open_risks": _riscos_abertos(colecoes["risks"]),
        },
        "empty_reasons": {k: razoes[k] for k in sorted(razoes)},
    }
    return relatorio


def _matriz(riscos: list[dict]) -> dict:
    """Contagem por par probabilidade × impacto. Chaves ordenadas — `dict` de inserção não serve."""
    matriz: dict[str, int] = {}
    for r in riscos:
        p = r.get("likelihood")
        i = r.get("impact")
        if not isinstance(p, str) or not isinstance(i, str):
            continue
        matriz[f"{p}|{i}"] = matriz.get(f"{p}|{i}", 0) + 1
    return {k: matriz[k] for k in sorted(matriz)}


def _riscos_abertos(riscos: list[dict]) -> list[dict]:
    abertos = [{"id": r.get("id"), "area": r.get("area"), "due": r.get("due"),
                "owner": r.get("owner"), "title": r.get("title")}
               for r in riscos if r.get("status") == "open"]
    return sorted(abertos, key=lambda x: (str(x.get("due") or ""), str(x.get("id") or "")))


# --------------------------------------------------------------------------------------
# A vista. HTML autocontido: sem CDN, sem bundler, sem estado no navegador.
# --------------------------------------------------------------------------------------
# As fontes do protótipo (Caprasimo/Figtree) vêm do Google Fonts e ficaram DE FORA: um laudo de
# auditoria que depende de rede para renderizar é um laudo que some quando a rede some. A escolha
# declarada é o fallback `system-ui`, e está escrita em harness/policies/relatorio.md.

CSS = """
:root{--bg:#f5ead8;--surface:#ebddc5;--text:#201e1d;--accent:#c67139;
--divider:rgba(32,30,29,.16);--radius:16px;--radius-sm:8px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font-family:system-ui,-apple-system,Segoe UI,sans-serif;line-height:1.55}
header{padding:2.5rem 1.5rem 1.5rem;max-width:1100px;margin:0 auto}
h1{font-size:2rem;margin:0 0 .25rem}
h2{font-size:1.25rem;margin:2.5rem 0 .75rem;border-bottom:2px solid var(--divider);
padding-bottom:.35rem}
main{max-width:1100px;margin:0 auto;padding:0 1.5rem 4rem}
.sub{opacity:.72;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.75rem}
.card{background:var(--surface);border-radius:var(--radius);padding:.9rem 1rem;
box-shadow:0 1px 2px rgba(46,43,37,.14)}
.card .n{font-size:1.75rem;font-weight:700;display:block;line-height:1.1}
.card .k{font-size:.8rem;opacity:.75}
.card .why{font-size:.72rem;opacity:.65;font-style:italic;display:block;margin-top:.2rem}
table{width:100%;border-collapse:collapse;font-size:.88rem;
display:block;overflow-x:auto;white-space:nowrap}
th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--divider)}
th{font-weight:700;opacity:.8}
code{background:rgba(32,30,29,.07);padding:.1rem .35rem;border-radius:4px;font-size:.85em}
.empty{background:var(--surface);border-left:4px solid var(--accent);
padding:.7rem .9rem;border-radius:var(--radius-sm);font-size:.88rem}
.empty b{font-style:normal}
footer{max-width:1100px;margin:0 auto;padding:1.5rem;border-top:1px solid var(--divider);
font-size:.82rem;opacity:.8}
footer dt{font-weight:700;margin-top:.5rem}
footer dd{margin:0 0 .1rem;word-break:break-all}
.warn{background:var(--accent);color:#fff;padding:.6rem .9rem;border-radius:var(--radius-sm);
font-size:.85rem;margin:1rem 0}
@media (prefers-color-scheme:dark){
:root{--bg:#201e1d;--surface:#2b2825;--text:#f0e7d8;--divider:rgba(240,231,216,.18)}
code{background:rgba(240,231,216,.1)}}
"""


def _esc(v: Any) -> str:
    s = "" if v is None else str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _tabela(itens: list[dict], colunas: tuple[str, ...]) -> str:
    cab = "".join(f"<th>{_esc(c)}</th>" for c in colunas)
    linhas = []
    for it in itens:
        celulas = "".join(f"<td>{_esc(it.get(c))}</td>" for c in colunas)
        linhas.append(f"<tr>{celulas}</tr>")
    return f"<table><thead><tr>{cab}</tr></thead><tbody>{''.join(linhas)}</tbody></table>"


def _bloco_vazio(chave: str, razao: str) -> str:
    """O vazio explicado. Um `0` solto seria a mesma tela para 'nada' e para 'não sei olhar'."""
    return (f'<p class="empty"><b>{_esc(chave)}</b>: {_esc(razao)}. '
            f'Este estado é uma afirmação do metadado, não uma omissão desta tela.</p>')


def render_html(rel: dict) -> str:
    proj = rel["project"]
    contagens = rel["counts"]
    razoes = rel["empty_reasons"]
    prov = rel["provenance"]

    cartoes = []
    for chave in sorted(contagens):
        n = contagens[chave]
        porque = razoes.get(chave)
        extra = f'<span class="why">{_esc(porque)}</span>' if porque else ""
        cartoes.append(f'<div class="card"><span class="n">{n}</span>'
                       f'<span class="k">{_esc(chave)}</span>{extra}</div>')

    secoes = []
    vistas: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("capabilities", ("id", "name", "status", "risk_level")),
        ("components", ("id", "name", "status", "capability")),
        ("requirements", ("id", "title", "status", "priority")),
        ("risks", ("id", "area", "status", "likelihood", "impact", "due")),
        ("adrs", ("id", "title", "status")),
        ("threats", ("id", "target", "severity")),
        ("stages", ("id", "order", "name")),
        ("policies", ("id", "title")),
        ("change_proposals", ("id", "title", "status", "level")),
        ("dependencies", ("name", "scope", "owner")),
    )
    for chave, colunas in vistas:
        itens = rel["collections"].get(chave, [])
        corpo = _tabela(itens, colunas) if itens else _bloco_vazio(chave, razoes.get(
            chave, VAZIO_DECLARADO))
        secoes.append(f"<h2>{_esc(chave)} <small>({len(itens)})</small></h2>{corpo}")

    inv = rel["computed"]["inventory"]
    if inv.get("redigido"):
        inv_html = ('<p class="warn">Inventário <b>redigido</b>: campos e finalidades aparecem '
                    f'como contagens ({inv.get("total_campos")} campos, '
                    f'{inv.get("total_finalidades")} finalidades). O conteúdo é material de '
                    'conformidade e não acompanha um artefato de destino público.</p>')
    elif inv.get("vazio_declarado"):
        inv_html = _bloco_vazio("inventário de dado pessoal", VAZIO_DECLARADO)
    else:
        inv_html = _tabela(inv.get("fields", []), ("name", "purpose", "legal_basis", "owner"))

    laudo = rel["computed"]["last_report"]
    if laudo.get("disponivel"):
        laudo_html = (f'<p>Último laudo lido de <code>{_esc(laudo.get("path"))}</code>, gerado em '
                      f'<b>{_esc(laudo.get("generated_at"))}</b>. É o resultado daquela execução, '
                      f'não uma nova: rodar os fiscais aqui dentro seria circular.</p>')
    else:
        laudo_html = _bloco_vazio("último laudo", laudo.get("razao", VAZIO_NAO_INGERIDO))

    return f"""<!-- {AVISO} -->
<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório do repositório — {_esc(proj.get('name'))}</title>
<style>{CSS}</style></head><body>
<header>
<h1>{_esc(proj.get('name')) or 'Repositório'}</h1>
<p class="sub">{_esc(proj.get('description'))}</p>
<p class="sub">papel declarado: <code>{_esc(proj.get('kind'))}</code></p>
</header>
<main>
<h2>Contadores</h2>
<div class="grid">{''.join(cartoes)}</div>
<h2>Fiscais</h2>
{laudo_html}
<h2>Inventário de dado pessoal</h2>
{inv_html}
{''.join(secoes)}
</main>
<footer>
<p><b>Artefato derivado.</b> Não editar à mão: <code>ci/generate_report.py --check</code>
contradiz a edição na hora mais cara.</p>
<dl>
<dt>digest das fontes</dt><dd><code>{_esc(prov.get('sources_digest'))}</code></dd>
<dt>fingerprint do parecer de privacidade</dt>
<dd><code>{_esc(prov['fingerprints'].get('privacy_review'))}</code></dd>
<dt>fingerprint da revisão de conformidade</dt>
<dd><code>{_esc(prov['fingerprints'].get('conformance_review'))}</code></dd>
<dt>versão do padrão</dt>
<dd>por referência a <code>{_esc(prov['standard'].get('version_source'))}</code> — nunca
restatada aqui, porque cópias derivam</dd>
<dt>fontes lidas</dt><dd>{len(rel['generated_from'])} arquivos</dd>
</dl>
</footer>
</body></html>
"""


def _serializa(rel: dict) -> str:
    return json.dumps(rel, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o relatório derivado do repositório.")
    parser.add_argument("--check", action="store_true",
                        help="sai 1 se o artefato na árvore está desatualizado")
    parser.add_argument("--stdout", action="store_true", help="imprime o JSON")
    parser.add_argument("--quiet", action="store_true", help="só imprime em caso de falha")
    parser.add_argument("--redigir", action="store_true",
                        help="troca campos do inventário por contagens (destino público)")
    args = parser.parse_args(argv)

    if hl is None:
        print(f"✗ FISCAL_CEGO: dependência ausente ({_ERRO_IMPORT}). "
              f"Próximo passo: pip install -e '.[dev]'", file=sys.stderr)
        return EXIT_CEGO

    try:
        rel = coletar(redigir=args.redigir)
    except FonteIlegivel as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return EXIT_CEGO

    json_novo = _serializa(rel)
    html_novo = render_html(rel)

    # O JSON é a INTERFACE — uma ferramenta de auditoria o consome sem parsear HTML — então ele
    # responde ao próprio contrato antes de ser escrito. Gerar um artefato que viola o schema que
    # o descreve seria publicar uma interface quebrada com aparência de válida, e quem descobriria
    # é o consumidor, longe daqui.
    erros = hl.schema_errors(SAIDA_JSON, "repo-report.schema.json", json.loads(json_novo))
    if erros:
        print(f"✗ FISCAL_CEGO: o relatório gerado viola o próprio contrato "
              f"(harness/schemas/repo-report.schema.json): {'; '.join(erros)}", file=sys.stderr)
        return EXIT_CEGO

    if args.stdout:
        print(json_novo, end="")
        return EXIT_OK

    if args.check:
        divergentes = []
        for caminho, novo in ((SAIDA_JSON, json_novo), (SAIDA_HTML, html_novo)):
            atual = hl.read_text(caminho) if hl.rel_exists(caminho) else None
            if atual != novo:
                divergentes.append(caminho)
        if divergentes:
            print(f"✗ relatório desatualizado: {', '.join(divergentes)}. "
                  f"Rode: python ci/generate_report.py", file=sys.stderr)
            return EXIT_DESATUALIZADO
        if not args.quiet:
            print("✓ relatório em dia.")
        return EXIT_OK

    destino = hl.REPO / SAIDA_DIR
    destino.mkdir(parents=True, exist_ok=True)
    (hl.REPO / SAIDA_JSON).write_text(json_novo, encoding="utf-8")
    (hl.REPO / SAIDA_HTML).write_text(html_novo, encoding="utf-8")
    if not args.quiet:
        print(f"✓ relatório gerado: {SAIDA_HTML} e {SAIDA_JSON}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
