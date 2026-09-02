# Hikvision Access Control para Home Assistant

Integração local, criada para terminais Hikvision MinMoe como o DS-K1T344.

Ela não depende do SDK na porta 8000, MQTT, Frigate nem de serviço em nuvem. A
comunicação é feita diretamente com o terminal por HTTPS/ISAPI na porta 443.

## Entidades

- Botão para acionar a porta 1 pelo ISAPI.
- Evento em tempo real para autenticação e mudança do relé.
- Último usuário, matrícula, método, resultado e horário.
- Estado do relé de abertura.
- Foto JPEG anexada ao último evento de autenticação.
- Estado da conexão ISAPI.

## Compatibilidade verificada

- Hikvision DS-K1T344MX-E1.
- ISAPI por HTTPS na porta 443.
- Autenticação HTTP Digest.
- Evento facial `5/75` com imagem JPEG anexa.
- K2M062 associado ao terminal como unidade de controle de porta segura.

## Instalação manual

1. Descompacte o pacote.
2. Copie a pasta `custom_components/hikvision_access_control` para `/config/custom_components/` no Home Assistant.
3. Reinicie o Home Assistant.
4. Abra **Configurações → Dispositivos e serviços → Adicionar integração**.
5. Procure por **Hikvision Access Control**.
6. Informe IP, porta `443`, usuário, senha, HTTPS ativado e verificação SSL desativada.

O terminal aparecerá como um dispositivo com todas as entidades agrupadas.

Se o Home Assistant estiver em contêiner, confirme antes que o contêiner alcança
`https://IP_DO_K1T344:443`. Não é necessário abrir a porta 8000.

## Observações

- A integração usa `/ISAPI/Event/notification/alertStream` e autenticação HTTP Digest.
- A foto fica apenas na memória do Home Assistant e é substituída pela próxima foto.
- O evento `5/75` é tratado como autenticação facial autorizada.
- Os eventos `5/21` e `5/22` representam destravamento e travamento do relé.
- A entidade de relé não confirma a abertura física do portão. Para isso, instale e configure um sensor magnético no controlador seguro.
- Use preferencialmente um usuário dedicado no terminal com as permissões ISAPI necessárias.

## Automação de exemplo

```yaml
alias: Avisar acesso pelo portão social
triggers:
  - trigger: state
    entity_id: event.portao_social_evento_de_acesso
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type == 'face_authenticated' }}"
actions:
  - action: notify.notify
    data:
      title: Portão social
      message: >-
        Acesso autorizado para
        {{ states('sensor.portao_social_ultimo_usuario') }}.
mode: queued
```

Os nomes reais das entidades podem ganhar um sufixo se já existirem entidades com
o mesmo nome. Selecione-as pelo editor visual ou confirme o `entity_id` em
**Ferramentas do desenvolvedor → Estados**.

## Solução de problemas

- **Não aparece na busca de integrações:** confirme a pasta
  `/config/custom_components/hikvision_access_control/` e reinicie o Home Assistant.
- **Credenciais inválidas:** use um usuário local do terminal com permissão ISAPI.
- **Certificado inválido:** mantenha a verificação SSL desativada para o certificado
  autoassinado do terminal.
- **Conexão ISAPI offline:** teste a rota entre o Home Assistant e a porta 443 do
  terminal; a integração reconecta automaticamente.
- **Sem foto:** gere uma nova autenticação facial. Eventos de relé normalmente não
  incluem imagem.
