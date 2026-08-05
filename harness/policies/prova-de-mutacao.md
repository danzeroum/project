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
