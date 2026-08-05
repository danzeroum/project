# Política: toda trava prova que morde

Todos os fiscais desta casa perguntam *"o repositório está conforme?"*. Esta política responde por
outra pergunta:

> **As travas ainda mordem?**

Um repositório verde com travas que não mordem é **indistinguível** de um repositório verde. É o
único estado que este sistema existe para impedir — e era o único que ele não detectava.

## Como a mutação é obtida

**Derivada da asserção**, porque cada tipo tem inverso bem definido: o que existe passa a não
existir, o padrão exigido some, a trava de schema muda de valor.

Uma asserção pode **declarar** `mutation`, e a declaração vence. É o escape para o que a derivação
não alcança — hoje, dez asserções `file_lacks` com regex expressiva, onde gerar um texto que case
exige entender a **intenção** da regra e não só a sua forma.

Escrever as 118 à mão seria a lista duplicada que o §12 proíbe na mesma frase em que pede a
declaração: ela derivaria da asserção real no primeiro dia em que alguém mudasse um `pattern` e
esquecesse o bloco.

## O que dá dentes

A mutação é **verificada**. O fiscal aplica e exige que a asserção fique vermelha. Se não ficar, o
achado não é sobre o repositório — é sobre a asserção, que passa a ser decorativa.

## O que a prova acusou primeiro: ela mesma

Na primeira execução o fiscal apontou **19 asserções** como decorativas. Nenhuma era. **As 19 eram
defeitos da própria mutação:**

- **cinco** porque o inverso de *"o arquivo contém o padrão"* apagava **uma** ocorrência de um
  padrão que aparecia várias — o arquivo continuava casando, e a asserção continuava
  (corretamente) verde;
- **uma** porque a mutação escolhia, num glob, justamente o arquivo que a asserção **exclui**;
- **uma** porque apagar o símbolo de um `import` deixava o arquivo com erro de sintaxe, e o fiscal
  passava a reportar **erro** (*"não consegui fiscalizar"*) em vez de **achado** — dois estados que
  esta casa separa por desenho, e que a mutação não pode confundir.

A lição vale mais que o resultado: **um fiscal de fiscais erra primeiro no próprio lado.** E o
achado dele é caro de um jeito específico — *"a asserção é decorativa"* manda consertar o lugar
errado. Quem o recebe vai reescrever uma trava que estava funcionando. Por isso a mutação é
**verificada** e não assumida, e por isso cada um dos três defeitos virou comentário no código, ao
lado da correção.

## A mutação que certificaria uma trava decorativa

O modo de falha mais perigoso deste fiscal não é deixar passar — é **carimbar**. Um caso concreto,
evitado ao escrever a cláusula B do ADR-026.

A regra era *"nenhum manifesto em `harness/releases/`"*, e a forma óbvia seria `path_absent` com
glob:

```yaml
kind: path_absent
paths: ["harness/releases/*.manifest.json"]     # ARMADILHA
```

`assert_path_absent` usa `rel_exists`, que é **literal**: o glob nunca casaria e a asserção passaria
sempre. Mas o problema não é esse. O problema é que **a prova de mutação a aprovaria**: o inverso
canônico `criar_caminho` criaria um arquivo chamado *literalmente* `v*.manifest.json`, `rel_exists`
o encontraria, a asserção ficaria vermelha depois de mutada — e a trava sairia da prova com selo de
que morde, sem nunca ter mordido um manifesto de verdade.

> **Um fiscal de fiscais enganado é pior que fiscal nenhum, porque produz um selo.**

Daí o tipo `dir_allowlist`, que **enumera** a lotação do diretório em vez de perguntar por um nome
que precisaria adivinhar. Seu inverso — pôr qualquer outra coisa lá dentro — não tem como coincidir
com a forma da pergunta, que era o buraco.

A lição generaliza: **quando a mutação e a asserção compartilham a mesma string, o acordo entre elas
pode não ser sobre o mundo.**

## O teste de mordida involuntário

O mais convincente da série não foi escrito: foi sofrido.

Ao rodar o smoke test da higiene de ambiente estendida (CP-025), o autor da trava exportou
`HTTPS_PROXY` no próprio comando — e **o hook recusou**, citando a política que ele acabara de
escrever. A trava mordeu quem a construiu, sem saber quem era, no minuto em que ele foi o primeiro
a passar por ela.

É o que separa uma trava de uma placa. Uma placa depende de o leitor concordar; e quem escreve a
regra é sempre o primeiro a ter um bom motivo para abrir uma exceção.

## Por que fica fora da validação total

A prova copia o repositório e roda o fiscal de conformidade 118 vezes: cerca de um minuto. O hook
`Stop` roda a validação total a cada turno do agente.

**Um fiscal que torna o loop de trabalho insuportável é desligado, não obedecido.** Ela é passo
próprio do CI.

## Conflito de dependências (§10)

Três arquivos declaram dependência, cada um respondendo a uma pergunta diferente. Três respostas
iguais são redundância barata; três **diferentes** são uma pergunta sem resposta, e o que se
instala passa a depender de qual arquivo o comando leu.

O fiscal só acusa `==` contra `==`. Um `>=8` no pyproject com um `==9.1.1` no lock **não** se
contradizem — o segundo é resolução válida do primeiro, e acusá-lo seria reprovar o funcionamento
normal de um lockfile.

Fiscalizado por: `ci/audit_mutations.py::provar`, `ci/check_dependency_conflict.py::conflitos`, `.github/workflows/governance.yml`
Declarado em: `harness/change-proposals/CP-030-prova-de-mutacao-canonica.yaml`, `architecture/adr/ADR-024-toda-trava-prova-que-morde.md`
Falha como: asserção que não reprova sua mutação ⇒ exit 1 com `nao_morde`; asserção nova sem mutação derivável ⇒ `mutacao_nao_derivavel`.
