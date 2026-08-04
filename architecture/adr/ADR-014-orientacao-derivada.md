# ADR-014 — A orientação deriva do repositório; ela não o descreve

- **Status:** accepted
- **Data:** 2026-08-05
- **Riscos relacionados:** RISK-ORIENT-001, RISK-META-001

## Contexto

Treze ADRs depois, este repositório sabe se validar muito bem e continua difícil de **começar**.
`BOOTSTRAP.md` diz por onde entrar; os comandos dizem como executar cada passo. Nada responde a
pergunta que uma pessoa — ou um agente — faz de verdade ao receber uma tarefa:

> *vou mexer nestes arquivos: que etapas isso aciona, que fiscais vão rodar, o que precisa mudar
> junto, e o que já está vermelho?*

Hoje isso se descobre lendo `CLAUDE.md`, `harness/stages.yaml` e sete políticas — ou descobrindo
no CI, que é o caminho caro.

A saída óbvia é escrever um guia com os caminhos certos. E é justamente a saída errada. Um guia
que **enumera** etapas, fiscais e caminhos vira uma segunda descrição do repositório, e segunda
descrição deriva da primeira — em silêncio, e com a aparência de documentação cuidadosa. Pior:
seria o ADR-002 violado pela ferramenta criada para ensinar o ADR-002.

## Decisão

**1. A orientação deriva, não descreve.** `ci/orient.py` lê o estado vivo: etapas de
`stages.yaml`, fiscais de `enforced_by`, caminhos protegidos de `harness.yaml`, a pergunta de
privacidade da própria etapa, a cobertura do código do inventário, e os códigos dos fiscais
reusando a lista de `validate_all._steps()`. Nenhuma lista escrita à mão dentro dele.

**2. A skill é magra de propósito.** `.claude/skills/desenvolver/SKILL.md` não contém a
informação — ela manda perguntar. É o que a mantém correta sem manutenção.

**3. Restatement é reprovado, não desencorajado.** `ADR-014-A3` recusa qualquer id de etapa
escrito à mão no `SKILL.md`, exatamente como `stages.schema.json` já recusa artefato que seja um
ID. A regra que vale para o índice vale para quem ensina o índice.

**4. Orientar não é fiscalizar.** `orient.py` **sai sempre 0**. Não reprova, não escreve, não
julga. Um orientador que também reprovasse viraria o oitavo fiscal — com regras próprias, sem
política e sem teste de mordida, e seria o primeiro lugar onde alguém iria afrouxar algo.

**5. Ele reporta códigos, não laudos.** A saída dos fiscais é engolida; quem quer o detalhe roda
`ci/validate_all.py`. Repetir o laudo criaria duas versões da mesma resposta, e a resumida é a que
as pessoas acabariam citando.

## Consequências

- Um agente que chega ao repositório tem dois comandos em vez de sete documentos, e as respostas
  são verdadeiras por construção — mudou `stages.yaml`, mudou a orientação.
- `orient.py` roda os fiscais para reportar o estado, então não é grátis. É aceitável porque ele é
  invocado no começo de uma tarefa, não a cada edição — o hook barato continua sendo o `Stop`.
- Custo assumido: a skill não ensina *julgamento*. Ela diz o que roda em cima da mudança, não se a
  mudança é boa. Quem responde isso é a revisão humana e o agente `conformance`, e fingir que uma
  página de markdown responderia seria a mesma promessa vazia que o ADR-002 proíbe.
- O próprio `--tocar` encontrou um bug em `orient.py` na primeira execução sobre si mesmo
  (`lstrip("./")` comendo o ponto de `.claude/`). Ferramenta que se aplica a si própria é barata
  de testar, e isso não é acidente: é a mesma propriedade que faz o molde fiscalizar o molde.

## Fiscal

`ci/audit_governance.py` (executa as asserções abaixo); `harness/policies/orientacao.md`;
`.github/workflows/governance.yml`. **Nenhum fiscal novo**: `orient.py` é derivado e não
fiscaliza — quem reprova continua sendo `ci/validate_all.py`.
