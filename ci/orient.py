#!/usr/bin/env python3
"""Orientação DERIVADA: onde estou, o que muda junto, o que roda em cima disso.

Não é fiscal e não julga: não reprova nada, não escreve nada, e sai 0 mesmo com o repositório
inteiro vermelho. Quem reprova são os sete fiscais de ci/validate_all.py. Este script existe
porque saber *como* trabalhar aqui exigia ler CLAUDE.md, harness/stages.yaml e sete políticas —
ou descobrir no CI.

A regra de desenho que o mantém honesto: **ele não contém a informação, ele a deriva.** Etapas
vêm de stages.yaml, fiscais de enforced_by, caminhos protegidos de harness.yaml, a pergunta de
privacidade da própria etapa, a cobertura do alvo do inventário. Nenhuma lista escrita à mão aqui
dentro — porque uma segunda descrição do repositório derivaria da primeira em silêncio, e com a
aparência de documentação cuidadosa. Seria o ADR-002 violado pela ferramenta que ensina o ADR-002.

Uso:
  python ci/orient.py                     panorama: papel, âncora, fiscais, próximo passo
  python ci/orient.py --tocar <caminho>…  o que uma mudança nesses caminhos aciona
  python ci/orient.py --pronto            o que falta para estar pronto (R-10: modo, não script)
  python ci/orient.py --json              o mesmo, para consumo por agente

Sai sempre 0. Estado do repositório é assunto de ci/validate_all.py.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import harness_lib as hl
from harness_lib import HarnessError

STAGES = "harness/stages.yaml"
HARNESS = "harness/harness.yaml"


# --------------------------------------------------------------------------------------
# Papel e âncora
# --------------------------------------------------------------------------------------

def papel() -> dict:
    projeto = hl.read_yaml("project.yaml") or {}
    lock = hl.read_yaml("target.lock") or {} if hl.rel_exists("target.lock") else {}
    alvo = projeto.get("target") or {}
    return {
        "kind": (projeto.get("project") or {}).get("kind"),
        "alvo": alvo.get("repo"),
        "ref": alvo.get("ref"),
        "sha": lock.get("target_sha"),
        "code_roots": alvo.get("code_roots") or [],
        "test_roots": alvo.get("test_roots") or [],
        "workspace_materializado": hl.rel_exists("workspace/target"),
    }


# --------------------------------------------------------------------------------------
# Quem é dono de cada caminho — derivado de stages.yaml, nunca listado aqui
# --------------------------------------------------------------------------------------

def _dono_por_arquivo() -> dict[str, str]:
    """arquivo -> etapa. Mesma resolução de artefatos que check_repo_partition usa."""
    mapa: dict[str, str] = {}
    for stage in (hl.read_yaml(STAGES) or {}).get("stages", []):
        for artefato in stage.get("artifacts", []):
            for p in hl.resolve_glob(artefato):
                if p.is_file():
                    mapa[hl.rel(p)] = stage["id"]
                else:
                    for filho in p.rglob("*"):
                        if filho.is_file():
                            mapa[hl.rel(filho)] = stage["id"]
    return mapa


def _etapa(sid: str) -> dict:
    for stage in (hl.read_yaml(STAGES) or {}).get("stages", []):
        if stage["id"] == sid:
            return stage
    return {}


def _protegido(rel: str) -> str | None:
    doc = hl.read_yaml(HARNESS) or {}
    for p in (doc.get("repository") or {}).get("protected_paths") or []:
        raiz = p.rstrip("/")
        if rel == raiz or rel.startswith(raiz + "/"):
            return p
    return None


def _fiscais(stage: dict) -> list[str]:
    out = []
    for e in stage.get("enforced_by", []):
        ref = e.get("ref", "?")
        out.append(f"{ref}::{e['symbol']}" if e.get("symbol") else ref)
    return out


def tocar(caminhos: list[str]) -> list[dict]:
    """O que uma mudança em cada caminho aciona. Tudo derivado; nada declarado aqui."""
    donos = _dono_por_arquivo()
    fora = {"não pertence a nenhuma etapa": True}
    out = []
    for bruto in caminhos:
        # removeprefix, nunca lstrip: lstrip("./") remove QUALQUER ponto ou barra
        # inicial e transformaria ".claude/…" em "claude/…" — um caminho que não
        # existe, e a orientação passaria a falar de outro arquivo.
        rel = bruto.removeprefix("./").rstrip("/")
        alvos = ([rel] if rel in donos else
                 sorted(k for k in donos if k.startswith(rel.rstrip("/") + "/")))
        sids = sorted({donos[a] for a in alvos}) if alvos else []
        item = {
            "caminho": rel,
            "existe": hl.rel_exists(rel),
            "etapas": [],
            "protegido_por": _protegido(rel),
        }
        if not sids:
            item["aviso"] = ("caminho novo: nenhuma etapa o reivindica ainda — "
                             "declare-o em harness/stages.yaml antes que a partição reprove")
            _ = fora
        for sid in sids:
            st = _etapa(sid)
            item["etapas"].append({
                "id": sid,
                "nome": st.get("name"),
                "fiscais": _fiscais(st),
                "pergunta_de_privacidade": (st.get("privacy_lens") or {}).get("question"),
            })
        out.append(item)
    return out


# --------------------------------------------------------------------------------------
# Estado dos fiscais e cobertura do alvo
# --------------------------------------------------------------------------------------

def fiscais_agora() -> dict[str, int]:
    """Roda os fiscais que validate_all roda — reusando a lista dele, nunca uma cópia."""
    import validate_all

    try:
        passos = validate_all._steps()
    except ImportError:
        return {}
    codigos: dict[str, int] = {}
    for nome, fn, extra in passos:
        argv = list(extra) + ([] if nome == "grafo" else ["--quiet"])
        # A saída dos fiscais é engolida de propósito: este painel reporta os CÓDIGOS, e quem
        # quer o detalhe roda ci/validate_all.py. Repetir o laudo aqui criaria duas versões da
        # mesma resposta — e a versão resumida é a que as pessoas acabariam citando.
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                codigos[nome] = fn(argv)
        except SystemExit as exc:
            codigos[nome] = int(exc.code or 0)
        except HarnessError:
            codigos[nome] = 2
    return codigos


def cobertura_do_alvo() -> dict | None:
    """Quanto do código já tem dono. É o 'quanto falta' da ingestão, em número."""
    import inventory_code

    try:
        inventory_code.reset_cache()
        inv = inventory_code.build()
    except HarnessError as exc:
        return {"erro": str(exc)}

    comps = hl.read_yaml("architecture/components.yaml") or {}
    donos = {p for c in comps.get("components", []) for p in c.get("source_paths", [])}
    isentos = {e["path"] for e in comps.get("exemptions", []) or []}
    codigo = [m["path"] for m in inv["modulos"] if m["kind"] == "code"]
    orfaos = [p for p in codigo if p not in donos and p not in isentos]
    return {
        "arquivos_de_codigo": len(codigo),
        "com_dono": len(codigo) - len(orfaos),
        "orfaos": orfaos[:10],
        "total_orfaos": len(orfaos),
        "adapters": {n: i for n, i in inv["adapters"].items()},
    }


def panorama() -> dict:
    p = papel()
    return {
        "papel": p,
        "fiscais": fiscais_agora(),
        "cobertura": cobertura_do_alvo(),
        "proximo_passo": _proximo(p),
    }


def pronto() -> dict:
    """"O que falta para este repositório estar pronto?" — MODO do orientador, não script novo.

    A proposta original era um `/verificar-pronto` separado, rejeitada no R-10 por duplicar o que
    este arquivo já sabe (e errando o caminho do lock ao duplicar). Aqui ele reusa `papel()`,
    `fiscais_agora()` e `cobertura_do_alvo()` — as mesmas funções, então não há segunda resposta
    que possa divergir da primeira.

    E ele NÃO REPROVA, como nada neste arquivo: o ADR-014 decidiu que um orientador que também
    fiscaliza vira o oitavo fiscal, sem política e sem teste de mordida. Aqui se responde "o que
    falta"; quem reprova é `validate_all.py`.
    """
    p = papel()
    fiscais = fiscais_agora()
    pendencias: list[dict] = []

    for nome, code in fiscais.items():
        if code:
            pendencias.append({
                "item": f"fiscal '{nome}'",
                "estado": "divergência" if code == 1 else "não conseguiu fiscalizar",
                "comando": "python ci/validate_all.py",
            })

    if p["kind"] == "derived":
        if not p.get("sha"):
            pendencias.append({"item": "target.lock:target_sha", "estado": "ausente",
                               "comando": "/adotar <url-do-alvo>"})
        if not p.get("workspace_materializado"):
            pendencias.append({"item": "workspace/target", "estado": "não materializado",
                               "comando": "python ci/bootstrap.py"})
        try:
            lock = hl.read_yaml("target.lock") or {}
        except HarnessError:
            lock = {}
        if not lock.get("mold_release"):
            pendencias.append({"item": "target.lock:mold_release", "estado": "sem âncora de molde",
                               "comando": "/atualizar-carcaca"})

    cob = cobertura_do_alvo()
    if cob and "erro" not in cob and cob.get("total_orfaos"):
        pendencias.append({
            "item": f"{cob['total_orfaos']} arquivo(s) de código sem dono",
            "estado": "órfão",
            "comando": "declarar em architecture/components.yaml:source_paths ou em exemptions",
        })

    return {"papel": p, "pendencias": pendencias, "pronto": not pendencias}


def _imprime_pronto(d: dict) -> None:
    if d["pronto"]:
        print("■ Pronto: nenhuma pendência derivável do estado atual.")
        print("  (isto NÃO é aprovação — quem reprova é python ci/validate_all.py)")
        return
    print(f"■ Faltam {len(d['pendencias'])} item(ns):\n")
    for pend in d["pendencias"]:
        print(f"  · {pend['item']} — {pend['estado']}")
        print(f"      {pend['comando']}")
    print("\nEste comando não reprova nada: ele deriva o que falta. O gate é ci/validate_all.py.")


def _proximo(p: dict) -> str:
    if p["kind"] == "mold":
        return "/adotar <url-do-alvo>  (este repositório não governa alvo algum)"
    if not p["workspace_materializado"]:
        return "/bootstrap  (o alvo não está materializado)"
    return "/ingerir  ou  /sincronizar, conforme a cobertura acima"


# --------------------------------------------------------------------------------------
# Saída legível
# --------------------------------------------------------------------------------------

def _imprime_panorama(d: dict) -> None:
    p = d["papel"]
    print(f"■ Papel: {p['kind'] or '(indefinido)'}")
    if p["kind"] == "derived":
        print(f"  alvo {p['alvo']} @ {p['ref']} · SHA {(p['sha'] or '?')[:12]}")
        print(f"  raízes de código: {', '.join(p['code_roots']) or '(nenhuma)'} · "
              f"de teste: {', '.join(p['test_roots']) or '(nenhuma)'}")
        print(f"  workspace: {'materializado' if p['workspace_materializado'] else 'AUSENTE'}")

    print("\n■ Fiscais agora")
    for nome, code in d["fiscais"].items():
        marca = {0: "✓", 1: "✗ divergência", 2: "✗ não conseguiu fiscalizar"}[code]
        print(f"  {marca:28} {nome}")

    cob = d["cobertura"]
    if cob and "erro" not in cob:
        print(f"\n■ Cobertura do código: {cob['com_dono']}/{cob['arquivos_de_codigo']} com dono")
        for nome, info in sorted(cob["adapters"].items()):
            nota = "" if info["semantico"] else f" — não lido: {info.get('nao_lido', '?')}"
            print(f"  · adapter {nome}: {info['arquivos']} arquivo(s){nota}")
        for orfao in cob["orfaos"]:
            print(f"  · órfão: {orfao}")
        if cob["total_orfaos"] > len(cob["orfaos"]):
            print(f"  · … e mais {cob['total_orfaos'] - len(cob['orfaos'])}")
    elif cob:
        print(f"\n■ Cobertura do código: {cob['erro']}")

    print(f"\n■ Próximo passo: {d['proximo_passo']}")
    print("\nPara saber o que uma mudança aciona:  python ci/orient.py --tocar <caminho>…")


def _imprime_tocar(itens: list[dict]) -> None:
    for item in itens:
        print(f"■ {item['caminho']}{'' if item['existe'] else '  (ainda não existe)'}")
        if item["protegido_por"]:
            print(f"  ⚠ protected_path '{item['protegido_por']}': começa por uma change-proposal "
                  f"em harness/change-proposals/ (ADR-004)")
        if item.get("aviso"):
            print(f"  ⚠ {item['aviso']}")
        for etapa in item["etapas"]:
            print(f"  etapa {etapa['id']} — {etapa['nome']}")
            for fiscal in etapa["fiscais"]:
                print(f"    fiscal: {fiscal}")
            if etapa["pergunta_de_privacidade"]:
                print(f"    lente de privacidade: {etapa['pergunta_de_privacidade']}")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Orientação derivada do estado do repositório.")
    parser.add_argument("--tocar", nargs="+", metavar="CAMINHO",
                        help="o que uma mudança nesses caminhos aciona")
    parser.add_argument("--pronto", action="store_true",
                        help="o que falta para este repositório estar pronto (não reprova)")
    parser.add_argument("--json", action="store_true", help="saída estruturada")
    args = parser.parse_args(argv)

    try:
        if args.tocar:
            dados = tocar(args.tocar)
        elif args.pronto:
            dados = pronto()
        else:
            dados = panorama()
    except HarnessError as exc:
        print(f"• não deu para orientar: {exc}", file=sys.stderr)
        print("  Próximo passo:  python ci/bootstrap.py", file=sys.stderr)
        return 0

    if args.json:
        print(json.dumps(dados, indent=2, ensure_ascii=False))
    elif args.tocar:
        _imprime_tocar(dados)
    elif args.pronto:
        _imprime_pronto(dados)
    else:
        _imprime_panorama(dados)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
