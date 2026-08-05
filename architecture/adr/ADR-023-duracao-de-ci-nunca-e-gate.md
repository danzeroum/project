# ADR-023 — Duração de CI nunca é gate; paridade local é

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-028 · **Revoga:** o gate de cache da v2.1 (R-12)

## Contexto

A v2.1 do plano aprovou um gate para o cache de dependências: *"≥30% de ganho medido em 5 runs"*
como critério de merge.

## Decisão 1 — o gate está revogado, e a revogação é explícita

Um threshold de duração mistura, num único número: cold start contra warm start, fila do GitHub
Actions, variação de rede e tamanho do runner. Como **critério de merge**, isso produz um fiscal
instável — uma fonte nova de flakiness num repositório cujo argumento inteiro é que verde e
vermelho significam alguma coisa.

**Duração de CI nunca é gate de merge.**

O cache é aprovado pela **propriedade funcional**:

- a chave inclui o lockfile e a versão do runtime;
- a restauração é observável no log (`cache_hit`);
- falha de restore **nunca** vira artefato de fiscal — o hash recusa antes;
- o CI permanece correto em cache miss.

Ganho de tempo é **observabilidade**: medido e registrado. Se não aparecer depois de duas janelas
de medição, abre-se CP de remoção ou ajuste — não um vermelho automático.

Este é o segundo registro de revisão de decisão própria neste plano (o primeiro foi a promessa
"o schema proíbe PII"). Registrá-la é o que a distingue de esquecimento.

## Decisão 2 — paridade local com integridade

`harness/local_validate.sh` instala do **mesmo** `requirements-ci.txt` que o CI, com
`--require-hashes`. Sem os hashes, um cache poderia esconder dependência adulterada, ou uma
resolução diferente localmente produziria um verde que o CI limpo contradiz — e *"na minha máquina
passa"* é o oposto do que um repositório de governança pode tolerar.

**O custo honesto, declarado porque vai doer um dia:** `--require-hashes` fixa **artefatos**, e
wheel é específico de plataforma. O lockfile é gerado para o que o CI usa (Linux x86_64, CPython
3.11). Em outra plataforma a instalação **falha explicitamente**, com mensagem que diz o que fazer.

Falhar explícito é o comportamento certo. A alternativa seria cair para outra resolução em
silêncio — exatamente a divergência que o lockfile existe para impedir. Containerização por digest
fica como CP posterior, **condicionada a divergência medida**, não a preferência.

## Decisão 3 — achado sem remediação deixa de ser representável

Medido antes de decidir: **38 dos 49** achados de `audit_governance.py` não traziam `remediation`.

Acrescentar a linha 38 vezes seria uma lista mantida à mão, que deriva na primeira adição
esquecida — a mesma classe de defeito que este repositório recusa em toda parte. Em vez disso,
`Findings.add` ganhou um mapa **origem → o que fazer**, aplicado quando o chamador não diz algo
mais específico. O específico continua vencendo.

Um achado que não diz o que fazer transfere para quem lê o trabalho de descobrir — que é
exatamente onde uma trava deixa de proteger e passa a atrapalhar.

**A fronteira do R-01 permanece intacta:** o fiscal **sugere** o comando, jamais o executa. Um
fiscal que conserta o que acusa é juiz e parte.

## Decisão 4 — o checklist de PR não é trava

`ci/pr_checklist.py` deriva de `stages.yaml` quais etapas o PR aciona, quais fiscais vão rodar e
qual pergunta de privacidade cada etapa faz. Ele **não reprova** e **não entra** em
`validate_all.py`: um checklist que reprovasse viraria o nono fiscal, sem política e sem teste de
mordida.

## Consequências

O CI para de reinstalar o mundo a cada run, e *"passa aqui"* volta a significar *"passa lá"* — com
a ressalva de plataforma escrita em três lugares (lockfile, script e política), para que ninguém
descubra a limitação num vermelho.

## Fiscal

`requirements-ci.txt` com hashes reais; `harness/local_validate.sh`; a chave de cache em
`.github/workflows/governance.yml`; `harness_lib.REMEDIACAO_POR_ORIGEM`. As asserções `ADR-023-A*`
provam que o lockfile continua com hash, que o CI continua instalando com `--require-hashes`, e
que nenhum threshold de duração voltou como gate.
