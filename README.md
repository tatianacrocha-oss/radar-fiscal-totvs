# Radar Fiscal TOTVS

Um painel que reúne, todo dia, as notícias fiscais e tributárias mais importantes
(Reforma Tributária, ICMS, ISS, NFe, NFSe, Simples Nacional, etc.), separadas por
"o quanto isso pode te afetar" (impacto alto, médio ou baixo).

## Acesse online

**https://tatianacrocha-oss.github.io/radar-fiscal-totvs/**

Esse link é público — qualquer pessoa pode abrir direto no navegador (computador ou
celular), sem precisar de login nem instalar nada. É só compartilhar o link.

O conteúdo desse link se atualiza **sozinho, todo dia às 8h** (horário de Brasília),
através de uma automação no GitHub (veja a seção 4). Não é necessário deixar nenhum
computador ligado para isso funcionar.

Repositório (código-fonte): https://github.com/tatianacrocha-oss/radar-fiscal-totvs

---

## Rodando localmente (opcional)

As instruções abaixo servem para quem quer rodar o buscador de notícias na própria
máquina (por exemplo, para testar mudanças antes de publicar). Para só *ver* o
painel, o link acima já é suficiente.

Tem duas partes:

- **`radar_fiscal_totvs.html`** → o painel. Você abre esse arquivo no navegador (Chrome, Edge, etc.) clicando duas vezes nele. Não precisa de internet nem de instalar nada para só olhar o painel.
- **`radar_fiscal_scraper.py`** → o "buscador". Um programinha que visita os sites do governo e dos portais de notícias, junta o que é relevante, e atualiza o painel. Esse sim precisa do Python instalado (é gratuito).

---

## 1. Instalando o que é necessário (só uma vez)

1. Instale o **Python** (gratuito): baixe em [python.org/downloads](https://www.python.org/downloads/) e instale marcando a opção "Add Python to PATH" durante a instalação.
2. Abra o **Prompt de Comando** (ou PowerShell) nesta pasta (a pasta onde estão os arquivos `radar_fiscal_scraper.py`, `radar_fiscal_totvs.html`, etc.).
   - Dica: dentro do Explorador de Arquivos do Windows, com a pasta aberta, digite `cmd` na barra de endereço e aperte Enter.
3. Digite o comando abaixo e aperte Enter. Ele instala as "ferramentas" que o buscador usa para ler sites e feeds de notícias:

   ```
   python -m pip install -r requirements.txt
   ```

Pronto, só precisa fazer isso uma vez neste computador.

---

## 2. Buscando as notícias do dia

Na mesma pasta, com o Prompt de Comando aberto, digite:

```
python radar_fiscal_scraper.py
```

O programa vai:
- Visitar todas as fontes configuradas (Receita Federal, PGFN, Ministério da Fazenda, Câmara, Senado, portais contábeis e as Secretarias da Fazenda dos estados);
- Separar o que é notícia de verdade do que é menu/propaganda dos sites;
- Classificar cada notícia por impacto e por assunto (tags);
- Atualizar o arquivo `noticias_data.js`, que é o que alimenta o painel.

Isso leva cerca de 1 a 2 minutos. No final aparece um resumo no terminal dizendo quantas notícias foram encontradas.

---

## 3. Vendo o painel

Depois de rodar o passo 2, basta abrir o arquivo **`radar_fiscal_totvs.html`** (duas vezes com o mouse) — ele abre no seu navegador normal.

No painel você tem:
- **Relógio** e **última atualização** no topo;
- **Menu** para trocar entre Radar do Dia, Reforma Tributária, Federal, Estadual, Municipal e Internacional;
- **Placar da Reforma Tributária** (IBS, CBS, Imposto Seletivo);
- **Filtros** por esfera, período, fonte e impacto;
- **Botão "Boletim do dia"**, que mostra um resumo só das notícias da última busca, agrupadas por impacto.

Quer ver notícias mais novas? Rode o passo 2 de novo e atualize a página do navegador (F5).

---

## 4. Deixando isso automático todo dia às 8h

### Versão online (já está configurada e funcionando)

O link público (https://tatianacrocha-oss.github.io/radar-fiscal-totvs/) já atualiza
sozinho — não depende do seu computador estar ligado. Isso funciona através de um
"robô" gratuito do GitHub (GitHub Actions), configurado no arquivo
`.github/workflows/atualizar-radar.yml`, que todo dia às 8h (horário de Brasília):

1. Roda o `radar_fiscal_scraper.py` na nuvem;
2. Salva as notícias encontradas;
3. Publica automaticamente no link.

Se quiser forçar uma atualização fora do horário (por exemplo, para testar), acesse
https://github.com/tatianacrocha-oss/radar-fiscal-totvs/actions/workflows/atualizar-radar.yml
e clique em **Run workflow**.

### Versão local (opcional, só se você quiser rodar no seu próprio computador)

O Windows também tem uma ferramenta própria para "lembrar" de rodar programas em um
horário — o **Agendador de Tarefas**. Use isso só se quiser gerar o painel localmente
também (por exemplo, para testar algo antes de publicar).

1. Abra o **Agendador de Tarefas** do Windows (pesquise por esse nome no menu Iniciar).
2. Clique em **Criar Tarefa Básica**.
3. Dê um nome, por exemplo "Radar Fiscal TOTVS".
4. Em "Disparador", escolha **Diariamente** e defina o horário **08:00**.
5. Em "Ação", escolha **Iniciar um programa** e aponte para o `python.exe` (o caminho aparece se você digitar `where python` no Prompt de Comando).
6. No campo de **argumentos**, coloque o caminho completo do arquivo `radar_fiscal_scraper.py`.
7. No campo "Iniciar em" (pasta), coloque o caminho desta pasta.
8. Salve.

*(Se preferir, existe também um modo alternativo rodando `python radar_fiscal_scraper.py --continuo`, que mantém o programa aberto esperando o horário. Mas ele precisa ficar rodando o tempo todo, então o Agendador de Tarefas é o jeito mais simples.)*

---

## 5. Boletim por e-mail (desligado por padrão)

O script já sabe enviar o boletim do dia por e-mail, mas isso está **desligado** até você configurar. Para ligar:

1. Abra o arquivo `config/config.json` em um editor de texto simples.
2. Preencha `email_remetente` e `email_destinatario`, e mude `"ativo": false` para `"ativo": true`.
3. Nunca escreva sua senha nesse arquivo. Em vez disso, configure uma "variável de ambiente" no Windows chamada `RADAR_FISCAL_EMAIL_SENHA` com a senha do seu e-mail (ou, se usar Gmail/Outlook, uma "senha de app", que é mais segura que a senha normal).
   - No Prompt de Comando: pesquise "Editar variáveis de ambiente do sistema" no menu Iniciar do Windows, clique em "Variáveis de Ambiente", e crie uma nova variável de usuário com esse nome e valor.
4. Para testar sem esperar o horário configurado, rode: `python radar_fiscal_scraper.py --enviar-email`

Você pediu para deixar o WhatsApp de lado por enquanto — o e-mail já está pronto para quando quiser, e o WhatsApp pode ser adicionado depois (existem serviços gratuitos simples para isso, como o CallMeBot).

---

## 6. Personalizando

- **Foco e estados prioritários**: veja `config/config.json`.
- **Quais sites são monitorados**: veja `config/sources.json`. Cada fonte tem um "tipo": `rss` (feed de notícias), `gov_br_html` (padrão dos sites do governo federal) ou `generic_html` (tentativa genérica para sites sem RSS).
- **Palavras-chave de classificação** (tags e impacto): veja `config/classificacao.json` — pode adicionar palavras livremente.
- **Placar da Reforma Tributária**: veja `config/reforma_status.json`. Os percentuais não são calculados automaticamente (para não arriscar mostrar um número errado) — você atualiza manualmente quando sair uma notícia oficial confirmando um novo marco. O terminal avisa quando aparecem notícias sobre isso, como lembrete.
- **Logo e cores**: a logo está em `assets/logo-totvs.png`. As cores estão no topo do arquivo `radar_fiscal_totvs.html`, dentro do bloco `:root { ... }` — são fáceis de trocar, cada cor tem um nome (`--totvs-azul`, `--totvs-roxo`, `--totvs-verde`).
- Você pode simplesmente pedir para o Claude ajustar qualquer uma dessas coisas por você.

---

## 7. Testando uma fonte específica

Se quiser ver o que uma fonte está trazendo (por exemplo, para saber por que um estado não aparece), rode:

```
python radar_fiscal_scraper.py --testar-fonte sefaz-sp
```

Troque `sefaz-sp` pelo `id` da fonte (a lista de ids está em `config/sources.json`).

---

## 8. O que já funciona bem e o que ainda tem limitação

- **Funcionam bem**: Receita Federal, PGFN, Ministério da Fazenda, Câmara dos Deputados, Senado Federal, MAPA, CFC, Portal Contábeis, Jornal Contábil, e boa parte das Secretarias da Fazenda estaduais.
- **Limitação conhecida**: alguns sites estaduais (hoje: SP, PR, RS, entre outros) carregam as notícias por dentro do site usando uma tecnologia (JavaScript) que o buscador simples não consegue ler — ele só lê o "HTML puro" da página, como um leitor de tela faria. Nesses casos, a fonte aparece no log como "não retornou notícias" em vez de mostrar algo errado. Se quiser, no futuro dá para evoluir o buscador para conseguir ler esses sites também (usando um "navegador automático" por trás, tipo Selenium/Playwright) — é só pedir.
- O buscador nunca inventa notícia: se não encontra nada relevante e confiável em uma fonte, ele simplesmente não mostra nada daquela fonte naquele dia.

---

## 9. Sobre a publicação online

O painel já está publicado e se atualiza sozinho — veja a seção **"Acesse online"**
no topo deste arquivo, e a seção 4 para entender como a automação funciona.

Se um dia quiser mover para outro serviço (Netlify, Vercel, etc.) em vez do GitHub
Pages, basta apontar o novo serviço para este mesmo repositório GitHub — não precisa
reescrever nada.

---

Feito com o Claude Code, para uso pessoal de Tatiana Cristine da Rocha (TOTVS).
