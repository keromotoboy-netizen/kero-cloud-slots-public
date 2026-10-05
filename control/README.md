# Kero Control Bus

Canal público de **comandos não sensíveis e allowlisted** para o gateway KIDS.

Regras:
- nunca armazenar segredo, senha, token, chave privada ou dado sensível;
- jobs são escritos apenas por identidades com permissão de escrita no repositório;
- o KIDS nunca executa shell arbitrário vindo deste diretório;
- somente ações presentes na allowlist local podem executar;
- risk=3 é sempre recusado;
- jobs expiram e são deduplicados por UUID;
- resultados são assinados com Ed25519 no KIDS e enviados ao Render Free;
- detalhes administrativos ficam fora de endpoints públicos.
