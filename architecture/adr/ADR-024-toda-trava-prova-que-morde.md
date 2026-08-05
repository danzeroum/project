# ADR-024 — Toda trava prova que morde

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-030

## Contexto

Todos os fiscais deste repositório perguntam a mesma coisa: *"o repositório está conforme?"*.

Nenhum perguntava: ***"as travas ainda mordem?"***

Um repositório verde com travas que não mordem é **indistinguível** de um repositório verde. É o
único estado que este sistema inteiro existe para impedir — e era o único que ele não conseguia
detectar.

## Decisão

**Toda regra bloqueante reprova a mutação canônica que a nega, e isso é verificado.**

### A mutação é derivada, e a declaração é o escape

O plano pede que cada controle *declare* a mutação e, na mesma frase, que a suíte seja *derivada
dos metadados, nunca de lista duplicada*. Com 123 asserções, escrever 118 blocos `mutation:` à mão
**seria** a lista duplicada: derivaria da asserção real no primeiro dia em que alguém mudasse um
`pattern` e esquecesse o bloco.

A mutação é portanto **derivada** — cada tipo de asserção tem inverso bem definido:

| Asserção | Inverso canônico |
|---|---|
| `path_present` | remover o caminho |
| `path_absent` | criar o caminho |
| `file_matches` | apagar **todas** as ocorrências do padrão |
| `file_lacks` | injetar texto que case |
| `schema_lock` | remover o que o ponteiro aponta |
| `import_required` | apagar a linha do import |
| `import_forbidden` | injetar o import |

Uma asserção pode **declarar** `mutation`, e a declaração vence. Dez das 118 precisaram — todas
`file_lacks` com regex expressiva, onde gerar um texto que case exige entender a **intenção** da
regra, não só a sua forma.

### A verificação é o que dá dentes

O fiscal aplica a mutação e **exige que a asserção fique vermelha**. Se não ficar, o achado não é
sobre o repositório: é sobre a asserção, que passa a ser decorativa. É a regra bloqueante
reprovando a si mesma, como o §12 pede.

## O que a prova encontrou ao ser escrita

Ela acusou **19 asserções** na primeira execução. Nenhuma delas era uma trava quebrada — **as 19
eram defeitos da própria mutação**:

1. **Cinco** porque o inverso de *"o arquivo contém o padrão"* apagava **uma** ocorrência de um
   padrão que aparecia várias. O arquivo continuava casando, e a asserção continuava (corretamente)
   verde.
2. **Uma** porque a mutação escolhia, num glob, justamente o arquivo que a asserção **exclui**.
3. **Uma** porque apagar o símbolo de um `import` deixava o arquivo com erro de sintaxe — e o
   fiscal passava a reportar **erro** ("não consegui fiscalizar") em vez de **achado**. São dois
   estados que esta casa separa por desenho, e que a mutação não pode confundir.

A lição, registrada porque vale mais que o resultado: **um fiscal de fiscais erra primeiro no
próprio lado**, e *"a asserção é decorativa"* é um achado caro — ele manda consertar o lugar errado.
Os três defeitos viraram comentário no código, ao lado da correção.

## Por que fica fora da validação total

A prova copia o repositório e roda o fiscal de conformidade 118 vezes: cerca de um minuto. O hook
`Stop` roda `validate_all.py` a cada turno do agente.

**Um fiscal que torna o loop de trabalho insuportável é desligado, não obedecido.** Ela é passo
próprio do CI, onde o minuto não incomoda ninguém.

## Consequências

Uma asserção nova nasce tendo de provar que morde. Uma asserção que deixar de morder — porque o
alvo mudou de forma, porque o padrão ficou frouxo — passa a acusar a si mesma no PR seguinte.

## Fiscal

`ci/audit_mutations.py::provar`, aplicado por `.github/workflows/governance.yml`. As asserções
`ADR-024-A*` provam que ele continua existindo e que o escape declarado continua no schema.
