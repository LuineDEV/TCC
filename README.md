# Organizador de E-mails Desktop

Protótipo acadêmico para TCC com foco em classificação local de e-mails usando NLP, TF-IDF, Scikit-Learn e armazenamento local.

## Funcionalidades

- Importação direta por IMAP com TLS, sem navegador aberto, e extração do conteúdo original das mensagens.
- Importação de e-mails por CSV.
- Treinamento de modelo supervisionado com TF-IDF e Regressão Logística.
- Classificação nas categorias `Urgente`, `Trabalho` e `Pessoal`.
- Interface desktop em Python com CustomTkinter.
- Persistência em MySQL local quando configurado.
- Cache JSON local para demonstração quando o MySQL ainda não estiver disponível.
- Filtros por categoria e correção manual da classificação.
- Retreinamento com os e-mails salvos localmente, incluindo correções manuais.

## Importação do Gmail

### Coleta recomendada: IMAP (KingHost)

1. Abra **Importar via IMAP**.
2. Configure `IMAP_USERNAME` e `IMAP_PASSWORD` uma vez no arquivo `.env` da pasta do projeto, usando o e-mail completo e a senha da conta. Por padrão, o servidor é `imap.kinghost.net`, porta `993`; em domínios de revenda, confirme se deve usar `imap.uni5.net`.
3. Mantenha a pasta `INBOX` e comece com 20 mensagens. O limite considera as mensagens mais recentes por UID.
4. **Testar conexão** confirma o acesso, sem baixar e-mails. Em seguida, clique em **Importar** para buscar as mensagens.
5. Acompanhe o resultado no diálogo; **Parar** preserva as mensagens já salvas. Uma operação de rede pode aguardar o timeout de 15 segundos.

O navegador pode ficar fechado. A conta configurada fica no `.env` local, excluído do Git; a senha não é salva no banco, no cache nem exibida em logs. A conexão usa TLS com validação de certificado. A pasta é aberta somente para leitura e o corpo é obtido com `BODY.PEEK[]`, preservando o estado lido/não lido.

São extraídos remetente, assunto, data e corpo. Texto simples tem preferência; HTML é convertido em texto quando necessário, sem scripts e estilos. Esta versão não extrai o conteúdo de anexos nem executa OCR em imagens IMAP. Mensagens com mais de 10 MB são ignoradas antes do download. A chave de conta/pasta/UIDVALIDITY/UID evita reimportar a mesma mensagem.

Não é necessário apagar dados antigos: eles são preservados, mas exemplos antigos sem indicação de revisão precisam ser revisados antes de participar do treino.

### Coleta anterior: Gmail por tela (legado)

O botão **Importar do Gmail** usa a janela do Google Chrome que já está aberta e autenticada pelo usuário. Antes de iniciar a leitura, deixe o Gmail aberto na Caixa de Entrada, com a janela maximizada e zoom em 100%.

A coleta abre até 10 mensagens da primeira página da Caixa de Entrada, copia o conteúdo visível e classifica automaticamente os registros importados. Durante a coleta, não use o mouse ou o teclado. O protótipo usa automação assistida de tela e não envia, exclui ou arquiva mensagens.

## Estrutura do CSV

Para importar e-mails, o arquivo CSV deve conter pelo menos:

```csv
sender,subject,body,category
usuario@email.com,Assunto da mensagem,Texto do e-mail,Trabalho
```

Para importação, `category` é opcional. Quando a coluna `category` existe, ela entra como categoria inicial do e-mail.

## Aprendizado com correções

O botão **Treinar modelo** usa os e-mails que já estão salvos na aplicação. Assim, o fluxo fica:

```text
Importar e-mails -> corrigir categorias na tela -> Treinar modelo -> modelo salvo
```

As categorias corrigidas manualmente entram na próxima rodada de treinamento. O novo modelo é salvo em `models/email_classifier.joblib` e será usado nas próximas execuções do aplicativo.

Somente categorias revisadas pelo usuário (com **Salvar categoria**) ou fornecidas em CSV rotulado entram no treino. Previsões automáticas e registros antigos sem origem de rótulo são excluídos para evitar reforçar erros. É necessário revisar pelo menos seis exemplos em duas categorias. **Classificar** preserva rótulos manuais e de CSV.

## Configuração do MySQL

1. Crie um arquivo `.env` a partir de `.env.example`.
2. Ajuste usuário, senha, host, porta e nome do banco.
3. O sistema cria automaticamente o banco e as tabelas ao iniciar, se o usuário tiver permissão.

Exemplo:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=sua_senha
DB_NAME=email_classifier_tcc
```

Se o MySQL não estiver disponível, o aplicativo entra em modo de demonstração usando `cache/emails_cache.json`.

## Como executar

No Windows, prepare o ambiente na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m email_classifier_app.main
```

Se as dependências já estiverem instaladas no Python ativo:

```bash
python -m email_classifier_app.main
```

Na primeira execução, o modelo é treinado automaticamente com `data/sample_emails.csv` se ainda não existir arquivo em `models/email_classifier.joblib`.

Para atualizar uma cópia existente ou preparar outro computador, consulte o [guia de atualização em PDF](output/pdf/Guia_atualizacao_Mail_Desk_2026-11-16.pdf).

Consulte [MAPA_DO_PROJETO.md](MAPA_DO_PROJETO.md) para o mapa de funcionalidades, arquitetura e limitações conhecidas.

Para executar os testes automatizados:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```

## Escopo acadêmico

Este projeto é um protótipo de classificação e visualização local de e-mails. Ele não pretende substituir um cliente completo de e-mail, nem implementar resposta automática ou resumo de mensagens como funcionalidades principais.
