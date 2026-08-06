#!/usr/bin/env python3
"""Motor de mutação canônica — o inverso de uma asserção, aplicado e desfeito.

EXTRAÍDO de `ci/audit_mutations.py` sem mudança de comportamento, e a extração é provada por isso:
as mesmas asserções do molde reprovam as mesmas mutações antes e depois. Um motor "melhorado"
durante a mudança de lugar teria misturado duas perguntas — "ele ainda funciona?" e "ele funciona
melhor?" — e só a primeira tem resposta barata.

POR QUE FORA DE `ci/`. Este módulo não sabe nada sobre este repositório: não lê `architecture/`,
não conhece fiscal algum, não presume layout. Ele responde a uma pergunta que qualquer régua tem —
*"esta trava morde?"* — e por isso é a peça que o contrato compartilha entre o molde e as suítes.

CONSUMIDO POR PIN, NUNCA COPIADO. É a mesma regra da régua e a mesma do alvo, aplicada ao próprio
motor: `harness/suite-contract/contract-v1/contract-manifest.json` declara o sha256 deste arquivo,
e `ci/audit_suites.py` confere. Uma cópia local pode ter um operador enfraquecido, e a prova
passaria a dizer "todas mordem" sem erro nem aviso — exatamente o modo de falha que a política
`harness/policies/prova-de-mutacao.md` chama de pior que fiscal nenhum, porque produz um selo.

STDLIB PURA, de propósito: uma suíte que o consome não deveria herdar dependência por consumir uma
trava. Quem chama entra com a asserção e a raiz; sai a mutação aplicada e o estado para desfazer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Versão do MOTOR, distinta da versão do contrato. O contrato pode chegar à v2 sem que o motor
# mude, e o motor pode ganhar um operador sem que as cláusulas mudem — restatar um no outro faria
# a primeira divergência passar por acordo.
ENGINE_VERSION = "1.0"

# Não copiados para a cópia mutada: só custariam tempo, e nenhum fiscal os percorre.
SKIP = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules",
        ".ruff_cache", ".mypy_cache", "build", "dist"}

# Texto injetado para violar um `file_lacks`. Simples de propósito: o objetivo é casar o padrão,
# não parecer código real.
_MARCA = "MUTACAO-CANONICA"

# Os operadores que este motor sabe aplicar. Enumerados para que um consumidor possa perguntar
# ANTES de tentar, e para que o `op` de um schema seja conferível contra a implementação real em
# vez de contra a memória de quem escreveu o schema.
OPERADORES = (
    "remover_caminho", "criar_caminho", "apagar_linha", "apagar_padrao",
    "substituir_texto", "injetar_apos", "injetar_texto", "quebrar_ponteiro",
)


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

    Restaurar em vez de recopiar o repositório: uma cópia por asserção custaria minutos, e a prova
    não fica melhor por ser lenta.
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
