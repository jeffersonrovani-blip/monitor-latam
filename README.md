# Monitor LATAM — GHCR + Hostinger

## 1. Publicar imagem
1. Crie um repositório GitHub (por exemplo, `monitor-latam`).
2. Envie `Dockerfile`, `monitor.py`, `config.json`, `requirements.txt`, `.dockerignore` e `.github/workflows/docker-publish.yml` preservando os caminhos.
3. Na aba Actions, execute `Publicar imagem Monitor LATAM` ou faça push na branch `main`.
4. Em GitHub → Packages, deixe a imagem **Public** para que a Hostinger possa baixar sem autenticação (ou configure autenticação privada separadamente).
5. Verifique o nome exato publicado. O exemplo do workflow usa `ghcr.io/SEU_USUARIO/monitor-latam:latest`.

## 2. Hostinger
1. No `docker-compose.yml`, substitua `SEU_USUARIO` pelo proprietário do GitHub (normalmente minúsculo).
2. Cole ou importe o YAML no Gerenciador Docker da Hostinger e implante.
3. O container permanecerá ligado para diagnósticos. **Não executa consultas periódicas nem coleta preço automaticamente**.
4. Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID via variáveis de ambiente do painel quando necessário. Não coloque credenciais no repositório.

## 3. Diagnóstico
Pelo terminal da VPS:
`docker exec monitor-latam python monitor.py status`
`docker logs monitor-latam`

Para testar captura com URL de busca real:
`docker exec monitor-latam python monitor.py capturar --url 'https://www.latamairlines.com/...' --somente-captura`

A navegação do site LATAM, eventual consentimento, resultados e confirmação de preço final ainda precisam ser validados. Captura não é cotação automática confirmada.

**Observação:** preço-meta R$ 1.800 por 1 adulto, GRU–IMP, 25/12/2026 a 03/01/2027, Light, bagagem de mão.
