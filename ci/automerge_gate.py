#!/usr/bin/env python3
"""O portão do auto-merge: este PR é *só* o atestado, e veio *mesmo* da autoridade?

POR QUE ISTO EXISTE. Desde a CP-036 o atestado vale 25h e o molde bloqueia quando ele vence. O
cron da autoridade roda todo dia e abre um PR; se esse PR depender de um humano clicar em merge,
a trava passa a ter um gargalo humano DIÁRIO. Atrito diário é como trava boa vira trava
contornada (princípio (e)): a pessoa que precisa integrar às 3h da manhã não vai admirar o
desenho, vai procurar o caminho de menor resistência — e o caminho de menor resistência de uma
trava incômoda é desligá-la.

O QUE ISTO NÃO É. Não é dispensa de validação. O canal continua sendo PR com checks, e a
liberação daqui só chega até `gh pr merge --auto`, que é o auto-merge NATIVO do GitHub: ele
espera os required status checks e o ruleset, e mergeia quando eles passam. Se um check reprovar,
o PR fica aberto e vermelho como qualquer outro. O que este portão dispensa é o CLIQUE, nunca o
julgamento.

O NÚCLEO É PURO, e a razão é a de sempre nesta casa: `decidir` não fala com a rede, não lê o
disco e não consulta o relógio, então os três cenários que importam — só-atestado/App,
atestado+extra/App, só-atestado/humano — são testáveis sem GitHub nenhum. A camada de I/O só
traduz o evento e o diff em argumentos.

TODOS OS MOTIVOS, NÃO O PRIMEIRO (princípio (h)). Um PR de humano que toca o atestado E mais um
arquivo tem DOIS problemas, e quem lê o resumo precisa dos dois. Retornar no primeiro
economizaria três linhas e faria a segunda rodada de investigação descobrir algo que já estava
ali.

E NÃO DECIDIR NÃO É LIBERAR. Sem `authorized_issuer` ou sem `attestation_path` declarados, este
portão não sabe contra o que comparar — e um portão que não sabe comparar tem exatamente uma
resposta segura. Exit 2, o mesmo código que o resto da casa usa para "não foi possível
fiscalizar".

Uso:  python ci/automerge_gate.py --arquivos <arquivo com um caminho por linha> --evento <json>
Saída: 0 decidiu (veja `liberar` na saída) · 2 não foi possível decidir.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import harness_lib as hl

HARNESS_YAML = "harness/harness.yaml"

# O sufixo que o GitHub dá ao login de um App instalado. Um App chamado `harness-authority`
# autora PRs como `harness-authority[bot]`, e o `user.type` do payload é `Bot`. Exigir os dois
# não é redundância: o login é digitável por um humano que registre uma conta com esse nome, e o
# tipo é atribuído pelo GitHub.
SUFIXO_APP = "[bot]"


@dataclass(frozen=True)
class Decisao:
    """`liberar` é a resposta; `motivos` é o que se diz a quem tiver de ler o PR amanhã."""

    liberar: bool
    codigos: tuple[str, ...] = ()
    motivos: tuple[str, ...] = field(default=())

    def resumo(self) -> str:
        if self.liberar:
            return "auto-merge liberado: o PR contém apenas o atestado e foi aberto pela autoridade."
        return "auto-merge NÃO liberado — este PR fica para revisão humana.\n" + "\n".join(
            f"  - [{c}] {m}" for c, m in zip(self.codigos, self.motivos))


def decidir(*, arquivos: list[str], autor_login: str, autor_tipo: str,
            emissor_autorizado: str, caminho_atestado: str) -> Decisao:
    """Núcleo puro. Três condições, e a ausência de qualquer uma mantém o PR com o humano.

    A identidade vem ANTES do conteúdo, espelhando `check_external_attestation`: "quem assinou"
    é a pergunta que decide o que fazer com a resposta de "o que está escrito".
    """
    codigos: list[str] = []
    motivos: list[str] = []

    # A DECLARAÇÃO. Não é uma condição sobre o PR — é sobre este repositório saber o que está
    # comparando. Sem ela, tudo abaixo compararia com string vazia e liberaria por vacuidade.
    if not emissor_autorizado or not caminho_atestado:
        return Decisao(False, ("PORTAO-SEM-DECLARACAO",), (
            f"{HARNESS_YAML} não declara `external_audit.authorized_issuer.identity` e/ou "
            f"`external_audit.attestation_path` — sem os dois este portão não sabe contra o que "
            f"comparar, e um portão que não sabe comparar não libera nada.",))

    esperado = f"{emissor_autorizado}{SUFIXO_APP}"
    if autor_login != esperado or autor_tipo != "Bot":
        codigos.append("AUTOR-NAO-E-A-AUTORIDADE")
        motivos.append(
            f"o PR foi aberto por {autor_login!r} ({autor_tipo}) e a autoridade declarada é "
            f"{esperado!r} (Bot). Auto-merge é a dispensa de um clique para UMA identidade — "
            f"estendê-la a quem quer que abra um PR com o arquivo certo devolveria ao humano com "
            f"direito de merge exatamente o poder que o atestado existe para tirar dele.")

    tocados = sorted(set(arquivos))
    if not tocados:
        codigos.append("PORTAO-SEM-DIFF")
        motivos.append(
            "o PR não lista arquivo algum. Diff vazio é 'não consegui ver o diff' com a mesma "
            "aparência de 'o diff está conforme', e as duas pedem reações opostas.")
    elif tocados != [caminho_atestado]:
        extras = [f for f in tocados if f != caminho_atestado]
        codigos.append("DIFF-ALEM-DO-ATESTADO")
        motivos.append(
            f"o PR toca {len(tocados)} arquivo(s), e o atestado é o ÚNICO conteúdo auto-mergeável "
            f"deste repositório. Fora do escopo: {', '.join(extras) or '(nenhum)'}. Um PR que "
            f"muda o atestado E outra coisa é um PR que muda outra coisa com o atestado de "
            f"carona.")

    if codigos:
        return Decisao(False, tuple(codigos), tuple(motivos))
    return Decisao(True, ("AUTORIZADO",), (
        f"diff = [{caminho_atestado}], autor = {esperado} (Bot). O auto-merge nativo assume "
        f"daqui: ele espera os checks obrigatórios e o ruleset, e mergeia se — e só se — "
        f"passarem.",))


# --------------------------------------------------------------------------------------
# Camada de I/O. Traduz evento e diff em argumentos; nenhuma decisão mora aqui.
# --------------------------------------------------------------------------------------

def _declarado() -> tuple[str, str]:
    doc = hl.read_yaml(HARNESS_YAML) or {}
    externo = (doc.get("external_audit") or {})
    return (((externo.get("authorized_issuer") or {}).get("identity") or ""),
            externo.get("attestation_path") or "")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Decide se um PR de atestado pode auto-mergear.")
    p.add_argument("--arquivos", required=True, help="arquivo com um caminho por linha")
    p.add_argument("--evento", help="payload do evento (padrão: $GITHUB_EVENT_PATH)")
    args = p.parse_args(argv)

    caminho_evento = args.evento or os.environ.get("GITHUB_EVENT_PATH", "")
    try:
        evento = json.loads(open(caminho_evento, encoding="utf-8").read())
        autor = (evento.get("pull_request") or {}).get("user") or {}
        arquivos = [l.strip() for l in open(args.arquivos, encoding="utf-8").read().splitlines()
                    if l.strip()]
        emissor, caminho = _declarado()
    except (OSError, ValueError, hl.HarnessError) as exc:
        print(f"✗ portão: não foi possível decidir ({exc}).", file=sys.stderr)
        return 2

    d = decidir(arquivos=arquivos, autor_login=autor.get("login") or "",
                autor_tipo=autor.get("type") or "", emissor_autorizado=emissor,
                caminho_atestado=caminho)

    print(("✓ " if d.liberar else "• ") + d.resumo())
    for destino, conteudo in (("GITHUB_OUTPUT", f"liberar={'true' if d.liberar else 'false'}\n"),
                              ("GITHUB_STEP_SUMMARY", f"### portão do auto-merge\n\n"
                                                      f"```\n{d.resumo()}\n```\n")):
        if os.environ.get(destino):
            with open(os.environ[destino], "a", encoding="utf-8") as fh:
                fh.write(conteudo)
    # Recusar NÃO é falhar: um PR humano que toca o atestado é legítimo e não deve ficar vermelho
    # por não ser auto-mergeável. Só a indeterminação sai diferente de 0.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
