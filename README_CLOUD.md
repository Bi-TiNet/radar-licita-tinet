# Radar Licita sem servidor Windows

Esta versão usa três serviços separados: GitHub Actions coleta a BLL a cada três horas; um projeto Supabase exclusivo guarda os dados e autentica o único usuário do painel; Netlify publica apenas a interface. Não copiar o banco ou as credenciais da Agenda AutoControl.

## Ordem segura de ativação

1. Criar um projeto gratuito **Radar Licita** no Supabase. Guardar a senha do banco no gerenciador de senhas, sem enviá-la por mensagem. Manter a Data API habilitada, desabilitar a exposição automática de novas tabelas e habilitar RLS automático se a tela oferecer essas opções.
2. Executar `supabase/schema.sql` no SQL Editor do projeto novo. Criar apenas a conta autorizada em Authentication e inserir o e-mail dela em `public.radar_access` conforme o comentário no fim do SQL. Desabilitar novos cadastros públicos. Não usar a chave secreta no site.
3. Configurar no GitHub, como *Actions secret*, `RADAR_SUPABASE_SECRET_KEY` (chave `sb_secret_...`, **nunca no frontend**). A URL pública do projeto Supabase já está no workflow. A coleta executa a cada três horas e após alterações no coletor na branch principal; o envio de alertas fica explicitamente desligado nesta etapa. Verificar uma linha `success` em `sync_runs`, conferindo a amostra de licitações no Supabase.
4. Site Netlify: `https://radar-licita-tinet.netlify.app`. Definir `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` (chave `sb_publishable_...`, própria para uso público) como variáveis de build. Em Supabase Authentication → URL Configuration, usar esse endereço como Site URL **antes** de reenviar convite; o padrão `localhost:3000` leva a erro. O link antigo não pode ser reaproveitado. Depois do primeiro deploy, reenviar um convite novo pelo Supabase; se a conta já estiver ativa, a tela de login também oferece um link para definir ou recuperar a senha. Confirmar que a página pede login, que uma conta não autorizada não vê dados e que a conta liberada consegue ver os registros.
5. Para iniciar somente com e-mail, configurar no GitHub os *Actions secrets* `RADAR_EMAIL_TO` (exatamente dois endereços, separados por vírgula), `RADAR_SMTP_HOST`, `RADAR_SMTP_PORT`, `RADAR_SMTP_USER`, `RADAR_SMTP_PASSWORD` e `RADAR_SMTP_FROM`. O workflow já fixa `RADAR_NOTIFICATION_CHANNELS=email`; números e credenciais de WhatsApp não são usados nessa fase. Executar manualmente o workflow com a opção `test_email` marcada e confirmar o recebimento das duas mensagens claramente identificadas como teste. Só então alterar `RADAR_NOTIFICATIONS_ENABLED` de `0` para `1`.
6. Para uma futura fase de WhatsApp, confirmar a integração autorizada com o OPA e a necessidade de modelo/cobrança. A integração legada espera Evolution API **pública** (`RADAR_EVOLUTION_API_URL`, `RADAR_EVOLUTION_INSTANCE`, `RADAR_EVOLUTION_API_KEY`); o endereço antigo `127.0.0.1` não funciona no GitHub. OPA requer adaptador próprio, não o preenchimento dessas três variáveis com dados do OPA. Testar os dois números separadamente antes de incluir `whatsapp` em `RADAR_NOTIFICATION_CHANNELS`.

Enquanto o envio estiver desligado, cada item coletado recebe `alert_baselined_at`: ele aparece no painel, mas não dispara mensagem antiga quando os alertas forem ligados. Cada destino confirmado é registrado separadamente, para que uma falha em um endereço não reenvie aos demais na coleta seguinte.

## Limites e cuidados

- O envio proativo por WhatsApp oficial pode exigir modelo aprovado e gerar cobrança. Confirmar as regras e o valor no contrato do OPA/Meta antes de ativar; o objetivo de hospedagem gratuita não garante WhatsApp gratuito.
- A coleta depende do formato da página pública BLL e pode falhar se ela mudar ou bloquear automação. Consultar `sync_runs` e o resultado do GitHub Actions; ausência de novas licitações não significa coleta saudável.
- O plano gratuito Supabase pode pausar um projeto inativo. Netlify e GitHub têm limites próprios. Não prometer operação permanente sem monitoramento.
- Não publicar `.env`, senhas, `service_role`, tokens de WhatsApp ou dados pessoais no repositório público, em logs ou na interface.
