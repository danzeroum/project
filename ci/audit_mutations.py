#!/usr/bin/env python3
"""Prova de fogo 4 — toda regra bloqueante reprova a mutação canônica que a nega.

A PERGUNTA QUE ESTE FISCAL FAZ é diferente de todas as outras: não "o repositório está conforme?",
mas "as travas ainda mordem?". Um repositório verde com travas que não mordem é indistinguível de
um repositório verde — e é o único estado que este sistema inteiro existe para impedir.

COMO A MUTAÇÃO É OBTIDA, e aqui houve uma decisão. O plano pede que "cada controle bloqueante
declare nos metadados a mutação mínima que deve reprovar" e, na mesma frase, que a suíte seja
"derivada dos metadados, nunca de lista duplicada". Com 123 asserções, escrever 118 blocos
`mutation:` à mão SERIA a lista duplicada — ela derivaria da asserção real no primeiro dia em que
alguém mudasse um `pattern` e esquecesse o bloco.

A leitura adotada: **a mutação é DERIVADA da asserção**, porque cada tipo de asserção tem um
inverso bem definido (o que existe passa a não existir; o padrão exigido some; a trava de schema
muda de valor). Uma asserção pode DECLARAR `mutation` explicitamente, e a declaração vence — é o
escape para os casos que a derivação não alcança.

E a parte que dá dentes: **a mutação derivada é VERIFICADA**. O fiscal aplica a mutação e exige
que a asserção correspondente fique vermelha. Se não ficar, o achado não é sobre o repositório —
é sobre a própria asserção, que passa a ser decorativa. É a regra bloqueante reprovando a si
mesma, como o plano pede.

Uso:  python ci/audit_mutations.py [--quiet] [--json] [--only ADR-XXX-AN]
Saída: 0 todas mordem · 1 alguma não morde ou não tem mutação · 2 não foi possível provar.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AUDITOR_VERSION = "1.0"
REPORT_PATH = "harness/reports/mutation-audit.json"

# Não copiados para a cópia mutada: só custariam tempo, e nenhum fiscal os percorre.
SKIP = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules",
        ".ruff_cache", ".mypy_cache", "build", "dist"}

# Texto injetado para violar um `file_lacks`. Simples de propósito: o objetivo é casar o padrão,
# não parecer código real.
_MARCA = "MUTACAO-CANONICA"


def _texto_que_casa(pattern: str) -> str | None:
    """Um texto que satisfaz o padrão — ou None quando não é mecanicamente derivável.

    Heurística deliberadamente simples: tira âncoras e quantificadores e devolve o literal. Ela
    ACERTA em padrões literais (a maioria) e ERRA em regex expressiva — e errar aqui é seguro,
    porque o chamador confere se o texto de fato casa antes de usá-lo. Adivinhação verificada é
    barata; adivinhação confiada seria a fonte de um verde falso.
    """
    literal = pattern
    for marca in ("^", "$", "\\b", "(?s)", "(?m)"):
        literal = literal.replace(marca, "")
    literal = re.sub(r"\\([./\-:*+?()\[\]{}|])", r"\1", literal)
    literal = literal.replace("\\s*", " ").replace("\\s+", " ").replace("\\d+", "1")
    if re.search(r"[\[\](){}|*+?]", literal):
        return None
    try:
        if re.search(pattern, literal, re.MULTILINE):
            return literal
    except re.error:
        return None
    return None


def derivar_mutacao(a: dict) -> dict | None:
    """O inverso canônico de uma asserção. None = não derivável (a asserção precisa declarar).

    'Mínima' aqui significa: toca um alvo só, e nega exatamente o que a asserção afirma. Uma
    mutação maior provaria menos — se ela quebra cinco coisas, o vermelho não diz qual trava
    mordeu.
    """
    if "mutation" in a:
        return a["mutation"]
    kind = a.get("kind")

    if kind == "path_present":
        return {"op": "remover_caminho", "alvo": a["paths"][0]}
    if kind == "path_absent":
        return {"op": "criar_caminho", "alvo": a["paths"][0]}
    if kind == "dir_allowlist":
        # O inverso de "só isto pode estar aqui" é pôr QUALQUER OUTRA COISA. Um nome que não está
        # na allowlist, escolhido para não se confundir com nada real do diretório.
        return {"op": "criar_caminho",
                "alvo": f"{a['dir'].rstrip('/')}/{_MARCA}-intruso"}
    if kind == "file_matches":
        return {"op": "apagar_padrao", "alvo": a["files"][0], "pattern": a["pattern"],
                "exclude": a.get("exclude") or []}
    if kind == "file_lacks":
        texto = _texto_que_casa(a["pattern"])
        if texto is None:
            return None
        return {"op": "injetar_texto", "alvo": a["files"][0], "texto": texto}
    if kind == "schema_lock":
        return {"op": "quebrar_ponteiro", "alvo": a["file"], "pointer": a["pointer"]}
    if kind == "import_required":
        return {"op": "apagar_linha", "alvo": a["module_glob"],
                "contendo": a["symbols"][0].rsplit(".", 1)[-1]}
    if kind == "import_forbidden":
        return {"op": "injetar_texto", "alvo": a["module_glob"],
                "texto": f"\nfrom {a['symbols'][0].rsplit('.', 1)[0]} import "
                         f"{a['symbols'][0].rsplit('.', 1)[-1]}  # {_MARCA}\n"}
    return None


def _resolver(raiz: Path, alvo: str, exclude: list[str] | None = None) -> Path:
    """O alvo pode ser um glob — asserções sobre famílias de arquivo existem (harness/policies/*.md).

    Sem isto, a mutação "não encontrava" o alvo e o fiscal acusava a asserção de vigiar o que não
    existe. Era um defeito da mutação disfarçado de defeito da asserção, que é a pior forma de
    achado: ele manda consertar o lugar errado.
    """
    if any(ch in alvo for ch in "*?["):
        proibidos = {p for padrao in (exclude or []) for p in raiz.glob(padrao)}
        casados = [p for p in sorted(raiz.glob(alvo)) if p not in proibidos]
        if casados:
            return casados[0]
    return raiz / alvo


def aplicar(mut: dict, raiz: Path) -> dict[str, bytes | None]:
    """Aplica e devolve o estado ANTERIOR dos arquivos tocados, para restaurar depois.

    Restaurar em vez de recopiar o repositório: 118 cópias custariam minutos, e a prova não fica
    melhor por ser lenta.
    """
    alvo = _resolver(raiz, mut["alvo"], mut.get("exclude"))
    antes: dict[str, bytes | None] = {}

    chave = alvo.relative_to(raiz).as_posix()

    if mut["op"] == "remover_caminho":
        if alvo.is_dir():
            destino = alvo.with_name(alvo.name + ".mutado")
            alvo.rename(destino)
            antes[chave] = b"__DIR__" + str(destino).encode()
        elif alvo.exists():
            antes[chave] = alvo.read_bytes()
            alvo.unlink()
        return antes

    if mut["op"] == "criar_caminho":
        antes[chave] = None
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(f"{_MARCA}\n", encoding="utf-8")
        return antes

    if not alvo.exists():
        return antes
    original = alvo.read_bytes()
    antes[chave] = original
    texto = original.decode("utf-8", errors="replace")

    if mut["op"] == "apagar_linha":
        alvo.write_text("\n".join(l for l in texto.splitlines()
                                   if mut["contendo"] not in l) + "\n", encoding="utf-8")
    elif mut["op"] == "apagar_padrao":
        # TODAS as ocorrências, e a correção veio da própria prova: com count=1, cinco asserções
        # ficaram verdes depois da mutação e o fiscal as acusou de decorativas. Elas não eram — a
        # mutação é que era insuficiente. O inverso de "o arquivo contém o padrão" é "não contém
        # mais", e um padrão que aparece cinco vezes continua aparecendo depois de apagar uma.
        alvo.write_text(re.sub(mut["pattern"], f"# {_MARCA}", texto, flags=re.MULTILINE),
                        encoding="utf-8")
    elif mut["op"] == "substituir_texto":
        # O inverso de uma DECISÃO BINÁRIA declarada não é apagar a linha — é declarar o contrário.
        # `enabled: true` sem a chave é erro de schema, um terceiro estado com outra reação; quem
        # desliga a autoridade escreve `false` e continua válido perante o schema. Mutar para o
        # estado que não é erro é o que prova que a asserção pega o gesto real, e não só o
        # desleixo. Sem `de` no arquivo a mutação seria um no-op silencioso — o chamador vê
        # `antes` vazio? Não: o arquivo existe, então devolvemos o original e o passo seguinte
        # (a asserção continuar verde) acusa. Por isso a substituição é conferida aqui.
        if mut["de"] not in texto:
            return antes
        alvo.write_text(texto.replace(mut["de"], mut["para"]), encoding="utf-8")
    elif mut["op"] == "injetar_apos":
        # Injeta DENTRO do escopo do marcador. As asserções de pureza (verify_chain,
        # verify_approval) usam padrão temperado, que só casa entre a assinatura e o próximo
        # `def` de topo — anexar no fim do arquivo não as violaria, e a mutação provaria nada.
        marcador = mut["marcador"]
        pos = texto.find(marcador)
        if pos < 0:
            return antes
        corte = texto.find("\n", texto.find(":", pos)) + 1
        alvo.write_text(texto[:corte] + mut["texto"] + "\n" + texto[corte:], encoding="utf-8")
    elif mut["op"] == "injetar_texto":
        alvo.write_text(texto + "\n" + mut["texto"] + "\n", encoding="utf-8")
    elif mut["op"] == "quebrar_ponteiro":
        doc = json.loads(texto)
        partes = [p for p in mut["pointer"].split("/") if p]
        node = doc
        for p in partes[:-1]:
            node = node[int(p)] if isinstance(node, list) else node[p]
        ultimo = partes[-1]
        if isinstance(node, list):
            del node[int(ultimo)]
        else:
            node.pop(ultimo, None)
        alvo.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return antes


def restaurar(antes: dict[str, bytes | None], raiz: Path) -> None:
    for rel, conteudo in antes.items():
        alvo = raiz / rel
        if conteudo is None:
            if alvo.exists():
                alvo.unlink()
        elif conteudo.startswith(b"__DIR__"):
            Path(conteudo[len(b"__DIR__"):].decode()).rename(alvo)
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(conteudo)


def _asserções_bloqueantes(doc: dict) -> list[tuple[str, dict]]:
    out = []
    for adr in (doc or {}).get("adrs", []):
        for a in adr.get("assertions") or []:
            if a.get("kind") == "manual":
                continue  # existe para dizer que NÃO é verificável; mutá-la não prova nada
            out.append((adr.get("id", "?"), a))
    return out


def provar(raiz: Path, apenas: str | None = None) -> tuple[list[dict], int]:
    """Aplica cada mutação e exige que a asserção correspondente fique vermelha."""
    import importlib
    import os

    os.environ["HARNESS_REPO_ROOT"] = str(raiz)
    import harness_lib as hl
    importlib.reload(hl)
    import audit_governance as ag
    importlib.reload(ag)

    doc = hl.read_yaml("architecture/adr/index.yaml")
    achados: list[dict] = []
    provadas = 0

    for adr_id, a in _asserções_bloqueantes(doc):
        aid = a.get("id", "?")
        if apenas and aid != apenas:
            continue
        mut = derivar_mutacao(a)
        if mut is None:
            achados.append({
                "assertion": aid, "adr": adr_id, "problema": "mutacao_nao_derivavel",
                "detalhe": f"o inverso de {a.get('kind')} com este padrão não é mecanicamente "
                           f"derivável, e a asserção não declara `mutation` — uma regra bloqueante "
                           f"sem mutação não pode provar que morde.",
            })
            continue

        antes = aplicar(mut, raiz)
        if not antes:
            achados.append({
                "assertion": aid, "adr": adr_id, "problema": "alvo_inexistente",
                "detalhe": f"a mutação não encontrou '{mut['alvo']}' — asserção que vigia o que "
                           f"não existe está quebrada, não satisfeita (ADR-006).",
            })
            continue
        try:
            findings, errors = hl.Findings(), hl.Errors()
            ag.check_adr_conformance(hl.read_yaml("architecture/adr/index.yaml"), findings, errors)
            mordeu = any(f.get("assertion") == aid for f in findings.blocking())
        finally:
            restaurar(antes, raiz)

        if mordeu:
            provadas += 1
        else:
            achados.append({
                "assertion": aid, "adr": adr_id, "problema": "nao_morde",
                "detalhe": f"a mutação canônica ({mut['op']} em {mut['alvo']}) foi aplicada e "
                           f"{aid} continuou verde — a asserção é decorativa.",
            })
    return achados, provadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prova de mutação canônica.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--only", help="prova uma asserção só (ex.: ADR-001-A1)")
    parser.add_argument("--report", default=REPORT_PATH)
    args = parser.parse_args(argv)

    origem = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="mutacao-") as tmp:
        copia = Path(tmp) / "repo"
        shutil.copytree(origem, copia, ignore=shutil.ignore_patterns(*SKIP))
        try:
            achados, provadas = provar(copia, args.only)
        except Exception as exc:  # noqa: BLE001 - não conseguir provar é exit 2, nunca 0
            print(f"✗ mutação: não foi possível provar ({exc})", file=sys.stderr)
            return 2

    laudo = {
        "schema_version": "1.0",
        "auditor": "ci/audit_mutations.py",
        "auditor_version": AUDITOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assertions_proved": provadas,
        "findings": achados,
        "result": "fail" if achados else "pass",
    }
    destino = origem / args.report
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(laudo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(laudo, indent=2, ensure_ascii=False))
    elif achados:
        print(f"✗ mutação: {len(achados)} regra(s) bloqueante(s) não provaram que mordem "
              f"({provadas} provadas):", file=sys.stderr)
        for a in achados:
            print(f"  - [{a['problema']}] {a['assertion']} ({a['adr']}): {a['detalhe']}",
                  file=sys.stderr)
    elif not args.quiet:
        print(f"✓ mutação: {provadas} regra(s) bloqueante(s) reprovaram sua mutação canônica.")

    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
