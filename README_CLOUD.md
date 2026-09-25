# Radar Licita sem servidor Windows

Esta versão usa três serviços separados: GitHub Actions coleta a BLL a cada três horas; um projeto Supabase exclusivo guarda os dados e autentica as contas autorizadas do painel; Netlify publica apenas a interface. Não copiar o banco ou as credenciais da Agenda AutoControl.

## Foco das oportunidades

- Santo Amaro, São Francisco do Conde, Cachoeira e Saubara: telecom para a Ti.Net e monitoramento/rastreamento veicular para a AutoControl.
- Petrolina, Juazeiro e as seis cidades vizinhas monitoradas: somente monitoramento/rastreamento veicular para a AutoControl. Licitações de telecom dessa região não aparecem no foco nem geram alerta.
- Credenciamentos de saúde, alimentação, CFTV isolado, compras/locação de veículos e TI genérica não entram no painel principal nem nos alertas. Os registros já coletados permanecem no banco para auditoria; nenhuma exclusão é feita.
- A classificação é um filtro por objeto e localidade, não uma confirmação de habilitação para participar. Antes de agir, conferir edital, documentação exigida, local de execução e prazo na BLL.

## Ordem segura de ativação

1. Criar um projeto gratuito **Radar Licita** no Supabase. Guardar a senha do banco no gerenciador de senhas, sem enviá-la por mensagem. Manter a Data API habilitada, desabilitar a exposição automática de novas tabelas e habilitar RLS automático se a tela oferecer essas opções.
2. Executar `supabase/schema.sql` no SQL Editor do projeto novo. Criar apenas a conta autorizada em Authentication e inserir o e-mail dela em `public.radar_access` conforme o comentário no fim do SQL. Desabilitar novos cadastros públicos. Não usar a chave secreta no site.
3. Configurar no GitHub, como *Actions secret*, `RADAR_SUPABASE_SECRET_KEY` (chave `sb_secret_...`, **nunca no frontend**). A URL pública do projeto Supabase já está no workflow. A coleta executa a cada três horas e após alterações no coletor na branch principal; o envio de alertas fica explicitamente desligado nesta etapa. Verificar uma linha `success` em `sync_runs`, conferindo a amostra de licitações no Supabase.
4. Site Netlify: `https://radar-licita-tinet.netlify.app`. Definir `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` (chave `sb_publishable_...`, própria para uso público) como variáveis de build. Em Supabase Authentication → URL Configuration, usar esse endereço como Site URL **antes** de reenviar convite; o padrão `localhost:3000` leva a erro. O link antigo não pode ser reaproveitado. Depois do primeiro deploy, reenviar um convite novo pelo Supabase; se a conta já estiver ativa, a tela de login também oferece um link para definir ou recuperar a senha. Confirmar que a página pede login, que uma conta não autorizada não vê dados e que a conta liberada consegue ver os registros.
5. Configurar no GitHub os *Actions secrets* `RADAR_EMAIL_TO` (exatamente dois endereços, separados por vírgula), `RADAR_SMTP_HOST`, `RADAR_SMTP_USER` e `RADAR_SMTP_PASSWORD`. A porta 587 e o remetente igual ao usuário SMTP já estão definidos como no sistema anterior. Em **Actions → Coleta Radar Licita → Run workflow**, marcar somente `test_email`. Confirmar o recebimento das duas mensagens de teste.
6. Criar um bot exclusivo no Telegram com o [@BotFather](https://t.me/BotFather). Guardar o token apenas no *Actions secret* `RADAR_TELEGRAM_BOT_TOKEN`; não enviá-lo em mensagens. Cada uma das duas pessoas deve abrir o bot e enviar `/start` em uma conversa individual. Em **Run workflow**, marcar `discover_telegram`; o bot responderá em privado com o ID numérico de cada pessoa já conectada, sem exibir IDs no log público. Se somente uma pessoa tiver iniciado, ela receberá o próprio ID e o log indicará que falta a segunda; basta a outra iniciar o bot e repetir a descoberta. Conferir que são os destinatários desejados e salvar os dois IDs, separados por vírgula, no *Actions secret* `RADAR_TELEGRAM_CHAT_IDS`. Então executar `test_telegram` e confirmar uma mensagem de teste em cada conversa. Não usar grupo nem WhatsApp.
7. Só após confirmar ambos os e-mails **e** ambos os chats, alterar `RADAR_NOTIFICATIONS_ENABLED` de `0` para `1` no workflow. Até lá a coleta continua funcionando e nenhum alerta real é enviado.

As opções manuais `test_email`, `discover_telegram` e `test_telegram` executam somente o teste escolhido, sem depender da coleta na BLL. Para iniciar uma coleta manual, deixe as três opções desmarcadas. Uma falha temporária na busca da BLL não impede descobrir ou testar os destinatários.

## Botão “Coletar agora” no painel

O botão solicita a execução do workflow já existente, sem abrir o GitHub. Ele aparece para `bi@tinettecnologia.com.br` e `diegosmfranca@hotmail.com`; a função no Netlify valida novamente o token do Supabase, o e-mail e a lista `radar_access`. Outros usuários do painel não podem disparar a coleta.

Para ativá-lo, crie no GitHub um **fine-grained personal access token** limitado ao repositório `Bi-TiNet/radar-licita-tinet`, com somente a permissão de repositório **Actions: Read and write**. Defina um prazo de expiração e guarde o valor apenas na variável `RADAR_GITHUB_DISPATCH_TOKEN` nas configurações de ambiente do site Netlify; nunca use prefixo `VITE_` nem coloque o valor no Git, na interface ou em mensagens. Caso a organização exija aprovação do token, conclua essa aprovação no GitHub. Confirme que `VITE_SUPABASE_PUBLISHABLE_KEY` está disponível também para Functions (ou configure `RADAR_SUPABASE_PUBLISHABLE_KEY` no Netlify com a chave pública do projeto). Faça um novo deploy depois de salvar as variáveis. A função ficará indisponível com mensagem clara enquanto a credencial não estiver configurada.

O clique confirma apenas o agendamento no GitHub; o resultado da coleta aparece depois na aba **Coletas**. A execução automática a cada três horas e as regras de alerta não mudam.

Enquanto o envio estiver desligado, cada item coletado recebe `alert_baselined_at`: ele aparece no painel, mas não dispara mensagem antiga quando os alertas forem ligados. Cada destino confirmado é registrado separadamente, para que uma falha em um endereço não reenvie aos demais na coleta seguinte.

## Limites e cuidados

- O Telegram só pode enviar mensagem direta após a pessoa iniciar a conversa com o bot. O aceite da API nos testes não substitui a confirmação de recebimento pelas duas pessoas.
- A coleta depende do formato da página pública BLL e pode falhar se ela mudar ou bloquear automação. Consultar `sync_runs` e o resultado do GitHub Actions; ausência de novas licitações não significa coleta saudável.
- O plano gratuito Supabase pode pausar um projeto inativo. Netlify e GitHub têm limites próprios. Não prometer operação permanente sem monitoramento.
- Não publicar `.env`, senhas, `service_role`, token do bot ou dados pessoais no repositório público, em logs ou na interface.
