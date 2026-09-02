# Hikvision Access Control para Home Assistant

Integração comunitária para controlar e acompanhar localmente terminais de acesso
Hikvision pelo protocolo HTTPS/ISAPI. A comunicação ocorre diretamente entre o
Home Assistant e o equipamento na rede local; não usa nuvem, MQTT nem o SDK da
porta 8000.

> Esta é uma integração independente e não oficial. Ela não é desenvolvida,
> homologada nem suportada pela Hikvision.

## Compatibilidade conhecida e testes

- Modelo-alvo e origem das amostras informadas: **Hikvision DS-K1T344MX-E1**.
- Controlador seguro associado informado: **DS-K2M062**.
- Transporte: HTTPS/ISAPI na porta 443 com autenticação HTTP Digest.
- Ambiente-alvo: Home Assistant OS 18.2 e Home Assistant Core 2026.8.3.
- Os testes automatizados cobrem parser multipart JSON/JPEG fragmentado,
  autenticação Digest, reconexão do `alertStream` e encerramento do cliente.

O preparo desta versão não incluiu acesso a um equipamento físico. Portanto, a
versão publicada deve ser validada no DS-K1T344MX-E1 real antes de ser considerada
homologada para produção. Outros modelos e firmwares não estão confirmados.

## Funcionalidades e entidades

Uma entrada de configuração representa um único terminal e cria um único
dispositivo no Home Assistant.

| Plataforma | Entidade | Função |
| --- | --- | --- |
| Button | Abrir portão | Pulsa a porta 1 por ISAPI |
| Event | Evento de acesso | Emite autenticações e alterações confirmadas do relé |
| Sensor | Último usuário | Nome ou matrícula do último acesso autorizado |
| Sensor | Matrícula do último usuário | Identificador recebido do terminal |
| Sensor | Último método | Método de verificação informado pelo evento |
| Sensor | Último resultado | Resultado do último evento de autenticação confirmado |
| Sensor | Horário do último acesso | Data e hora enviada pelo equipamento |
| Sensor | Último evento | Tipo e metadados do último evento recebido |
| Sensor | Conexão ISAPI | Estado `online`/`offline` do `alertStream` |
| Binary sensor | Relé de abertura | Último estado lógico de travamento/destravamento |
| Camera | Foto do último acesso | Último JPEG recebido no multipart, mantido em memória |

Mapeamentos confirmados pelas amostras descritas para o DS-K1T344:

- `majorEventType: 5`, `subEventType: 75`: autenticação facial autorizada.
- `majorEventType: 5`, `subEventType: 21`: relé/fechadura destravado.
- `majorEventType: 5`, `subEventType: 22`: relé/fechadura travado.

Outros códigos são publicados como `unknown_access_event`; não são classificados
sem documentação ou amostra real.

> **Importante:** os eventos 5/21 e 5/22 indicam somente o comando/estado lógico do
> relé. Eles não comprovam que o portão abriu ou fechou fisicamente. Para essa
> confirmação, instale um sensor magnético adequado e integre-o ao Home Assistant.

## Instalação pelo HACS como repositório personalizado

1. Abra o HACS no Home Assistant.
2. Entre em **Integrações**.
3. Abra o menu no canto superior direito e escolha **Repositórios personalizados**.
4. Em **Repositório**, informe
   `https://github.com/titogarrido/ha-hikvision-access-control`.
5. Em **Categoria**, selecione **Integração** e clique em **Adicionar**.
6. Procure por **Hikvision Access Control** no HACS e clique em **Baixar**.
7. Reinicie o Home Assistant.

Depois de instalada, as atualizações publicadas como GitHub Releases aparecerão
normalmente no HACS. Este repositório não precisa ser submetido ao catálogo padrão
do HACS para funcionar como repositório personalizado.

## Instalação manual

1. Baixe o código da release desejada.
2. Copie a pasta `custom_components/hikvision_access_control` para
   `/config/custom_components/hikvision_access_control`.
3. Reinicie o Home Assistant.

## Configuração pela interface

1. Abra **Configurações → Dispositivos e serviços → Adicionar integração**.
2. Procure por **Hikvision Access Control**.
3. Informe o endereço do terminal, porta (normalmente `443`), usuário, senha e um
   nome para o dispositivo.
4. Mantenha HTTPS habilitado. Para o certificado autoassinado padrão do terminal,
   desabilite **Verificar certificado HTTPS**. Habilite a verificação se o terminal
   usar um certificado confiável para o nome/endereço configurado.

As credenciais ficam na entrada de configuração protegida do Home Assistant e não
são gravadas no código, em logs de diagnóstico ou nas imagens. É possível alterar
todos os dados posteriormente pela opção **Reconfigurar** da integração; falhas de
autenticação também iniciam o fluxo de reautenticação.

## Permissões do usuário Hikvision

Crie no terminal um usuário local dedicado, com o menor privilégio possível. Ele
precisa conseguir:

- ler `/ISAPI/System/deviceInfo`;
- ler continuamente `/ISAPI/Event/notification/alertStream`;
- executar `PUT /ISAPI/AccessControl/RemoteControl/door/1` para usar o botão.

Os nomes das permissões variam conforme o firmware. Habilite acesso ISAPI, leitura
de eventos e controle remoto da porta; não use a conta de administrador se um
perfil restrito puder executar essas três operações.

## Automação de exemplo

Substitua os `entity_id` pelos identificadores criados na sua instalação:

```yaml
alias: Avisar acesso pelo portão social
triggers:
  - trigger: state
    entity_id: event.portao_social_evento_de_acesso
conditions:
  - condition: template
    value_template: >-
      {{ trigger.to_state.attributes.event_type == 'face_authenticated' }}
actions:
  - action: notify.notify
    data:
      title: Portão social
      message: >-
        Acesso autorizado para
        {{ states('sensor.portao_social_ultimo_usuario') }}.
mode: queued
```

## Solução de problemas

- **A integração não aparece:** confirme o caminho exato da pasta e reinicie o
  Home Assistant após instalar ou atualizar manualmente.
- **Credenciais inválidas:** confirme que o usuário é local, que a senha está
  correta e que as três permissões ISAPI acima estão habilitadas.
- **Erro de certificado:** desabilite a verificação apenas para um certificado
  autoassinado conhecido ou instale um certificado confiável no terminal.
- **Conexão ISAPI offline:** verifique se o Home Assistant alcança
  `https://192.168.1.100:443`. O fluxo se reconecta automaticamente com espera
  progressiva de 2 a 30 segundos.
- **Sem foto:** gere uma autenticação facial. Eventos de relé normalmente não
  carregam JPEG.
- **Horário ausente:** confirme que o terminal envia `dateTime` válido e mantenha
  o fuso horário/NTP do dispositivo configurado.
- **Portão não corresponde ao relé:** use um sensor magnético; a integração não
  infere posição física a partir dos eventos 21/22.

## Publicando uma nova versão

Para publicar `0.1.1`, atualize `version` no `manifest.json` e o `CHANGELOG.md`,
execute os testes, faça commit e envie a branch `main`. Depois crie a tag anotada
`v0.1.1`, envie a tag e publique uma GitHub Release chamada `v0.1.1`. Não é
necessário gerar ZIP personalizado: o HACS instala diretamente
`custom_components/hikvision_access_control` do código-fonte da release.

## Referências

- [Publicação de integrações no HACS](https://hacs.xyz/docs/publish/integration/)
- [Manifesto de integrações do Home Assistant](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [Imagens locais para integrações personalizadas](https://developers.home-assistant.io/docs/core/integration/brand_images/)

## Licença

MIT. Consulte [LICENSE](LICENSE).
