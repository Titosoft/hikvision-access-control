# Hikvision Access Control para Home Assistant

Integração comunitária para controlar e acompanhar localmente terminais de acesso
Hikvision pelo protocolo HTTPS/ISAPI. A comunicação ocorre diretamente entre o
Home Assistant e o equipamento na rede local; não usa nuvem, MQTT, SDK nativa nem
um add-on separado. Os eventos gerais usam o `alertStream`, enquanto o toque da
campainha é lido pelo estado de chamada ISAPI.

> Esta é uma integração independente e não oficial. Ela não é desenvolvida,
> homologada nem suportada pela Hikvision.

## Compatibilidade conhecida e testes

- Modelo-alvo e origem das amostras informadas: **Hikvision DS-K1T344MX-E1**.
- Controlador seguro associado informado: **DS-K2M062**.
- Transporte: HTTPS/ISAPI na porta 443 com autenticação HTTP Digest.
- Ambiente-alvo: Home Assistant OS 18.2 e Home Assistant Core 2026.8.3.
- Os testes automatizados cobrem parser multipart XML/JSON/JPEG fragmentado,
  autenticação Digest, transições do estado de chamada, reconexão do
  `alertStream` e encerramento do cliente.

O endpoint de estado de chamada foi validado em um DS-K1T344MX-E1 com firmware
V4.13.0 build 241025: ao pressionar o botão, as respostas mudam de `idle` para
`ring` e retornam a `idle`. Outros modelos e firmwares não estão confirmados.

## Funcionalidades e entidades

Uma entrada de configuração representa um único terminal e cria um único
dispositivo no Home Assistant.

| Plataforma | Entidade | Função |
| --- | --- | --- |
| Button | Abrir portão | Pulsa a porta 1 por ISAPI quando o dispositivo anuncia essa capacidade |
| Event | Evento de acesso | Emite autenticações, estados da porta, alarmes de segurança e chamadas |
| Sensor | Último usuário | Nome ou matrícula do último acesso autorizado |
| Sensor | Matrícula do último usuário | Identificador recebido do terminal |
| Sensor | Último método | Método de verificação informado pelo evento |
| Sensor | Último resultado | Resultado do último evento de autenticação confirmado |
| Sensor | Horário do último acesso | Data e hora enviada pelo equipamento |
| Sensor | Último evento | Tipo e metadados do último evento recebido |
| Sensor | Conexão ISAPI | Estado `online`/`offline` do `alertStream` |
| Binary sensor | Relé de abertura | Último estado lógico de travamento/destravamento |
| Binary sensor | Campainha tocando | Liga na transição ISAPI de `idle` para `ring` e desliga ao sair de `ring` ou pelo timeout local |
| Binary sensor | Violação | Agrega alarmes físicos de tamper e cobertura/obstrução da câmera; expõe as fontes ativas |
| Camera | Foto do último acesso | Última parte `Picture` ligada a um acesso, sem substituir pela imagem térmica |
| Camera | Foto do último visitante | Foto ligada ao último toque da campainha, usando o anexo do evento ou um snapshot |

Mapeamentos confirmados pelas amostras descritas para o DS-K1T344:

- `majorEventType: 5`, `subEventType: 75`: autenticação facial autorizada.
- `majorEventType: 5`, `subEventType: 21`: relé/fechadura destravado.
- `majorEventType: 5`, `subEventType: 22`: relé/fechadura travado.

A integração também segue a tabela oficial de alarmes de controle de acesso da
Hikvision. Entre os eventos classificados estão:

- `majorEventType: 5`, `subEventType: 37` (`0x25`): campainha tocando;
- `majorEventType: 5`, `subEventType: 51` (`0x33`): chamada à central;
- `majorEventType: 5`, `subEventType: 29` (`0x1d`): saída de alarme ligada;
- `majorEventType: 5`, `subEventType: 30` (`0x1e`): saída de alarme desligada;
- `eventType: changedCallStatus` com `status: ring`: chamada de vídeo porteiro;
- `2/39` (`0x27`) e `2/1031` (`0x407`): rede desconectada e restabelecida;
- `2/1040` (`0x410`): módulo seguro de controle da porta online;
- `majorEventType: 3`, `subEventType: 112` (`0x70`): login remoto no terminal;
- `5/25` a `5/28`: porta aberta, fechada, aberta de forma anormal ou por tempo
  excessivo;
- `1/0x404`, `1/0x406` e `1/0x40f`: violação do terminal, leitor ou módulo de
  segurança;
- falhas e tempos esgotados dos métodos de autenticação mais comuns.

Eventos ISAPI de obstrução de vídeo (`tamperdetection` e `shelteralarm`) são
tratados como violação física da câmera: `eventState: active` gera
`camera_tamper_alarm`, e `eventState: inactive` gera `camera_tamper_restored`.
O tipo original, estado e dados do canal permanecem nos atributos. Esses nomes
fazem parte do protocolo ISAPI; a emissão ao cobrir a câmera ainda precisa ser
validada no DS-K1T344MX-E1 e no firmware instalado. A classificação depende de
receber o evento do equipamento, sem analisar imagens para detectar obstrução.

O catálogo inclui os eventos documentados de alarme (`1/*`), exceção (`2/*`),
operação (`3/*`) e evento de acesso (`5/*`), incluindo estados de alimentação,
comunicação, controladores, saídas de alarme, autenticação multifator, elevador,
antipassback e eventos de passagem. Faixas de eventos personalizados do firmware
continuam sendo exibidas com o código original, pois a Hikvision não define um
significado comum para elas.

Também são classificados os eventos de autenticação bem-sucedida documentados
pela Hikvision para cartão, cartão e PIN, digital, combinações de face e outros
fatores, PIN e autenticação combinada. O campo `currentVerifyMode` recebido do
terminal continua sendo exposto como o método do último acesso.

Os valores numéricos são aceitos tanto em decimal quanto como texto hexadecimal.
Outros códigos mantêm a classificação `unknown_access_event`, com `major` e
`sub_event` nos atributos para diagnóstico. Outros tipos ISAPI mantêm a
classificação `unknown_isapi_event`, com o conteúdo específico em `event_data`.
Nas entidades “Evento de acesso” e “Último evento”, a exibição inclui a origem:
`Evento ISAPI desconhecido (changedCallStatus)` ou
`Evento de acesso desconhecido (5/999)`. O nome ISAPI é o identificador recebido,
sem inferir o significado de um evento ainda não mapeado.

O atributo `event_code` contém a classificação estável em ambas as entidades.
Automações que comparavam `event_type` ou o estado do sensor diretamente com
`unknown_isapi_event` ou `unknown_access_event` devem usar `event_code`, pois o
texto desses eventos agora inclui os parênteses. Por exemplo:

```jinja2
{{ trigger.to_state.attributes.event_code == 'unknown_isapi_event' }}
```

Os tipos conhecidos, como `doorbell_ringing` e `face_authenticated`, continuam
iguais. O texto dos eventos desconhecidos usa o idioma geral do Home Assistant
no carregamento da integração; para mudar esse idioma, recarregue a integração.
Os registros anteriores do histórico não são renomeados.

> **Importante:** os eventos 5/21 e 5/22 indicam somente o comando/estado lógico do
> relé. Eles não comprovam que o portão abriu ou fechou fisicamente. Para essa
> confirmação, instale um sensor magnético adequado e integre-o ao Home Assistant.

## Instalação pelo HACS como repositório personalizado

1. Abra o HACS no Home Assistant.
2. Entre em **Integrações**.
3. Abra o menu no canto superior direito e escolha **Repositórios personalizados**.
4. Em **Repositório**, informe
   `https://github.com/Titosoft/hikvision-access-control`.
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

## Campainha pelo estado de chamada ISAPI

A própria integração consulta, por padrão, a cada 2 segundos:

```text
GET /ISAPI/VideoIntercom/callStatus?format=json
```

A transição para `ring` liga o binary sensor **Campainha tocando** e gera uma
única ocorrência `doorbell_ringing`. Respostas `ring` repetidas não duplicam o
evento. A transição de volta para `idle` desliga o sensor; um temporizador local
de 45 segundos também o desliga caso o equipamento deixe de responder antes de
informar o estado final.

Não é preciso instalar App/complemento, abrir a porta 8000, copiar bibliotecas ou
configurar MQTT. O `alertStream` continua ativo para autenticações, relé, alarmes
e outros eventos de acesso. Se ele também publicar a chamada, a deduplicação evita
uma segunda ocorrência. Quando o evento não traz uma imagem, a integração tenta
obter o snapshot do canal 101.

O intervalo pode ser definido entre 1 e 60 segundos durante a configuração inicial
e alterado depois em **Configurações → Dispositivos e serviços → Hikvision Access
Control → Reconfigurar**. Intervalos maiores reduzem as requisições, mas podem
perder uma chamada que toque por menos tempo que o intervalo escolhido.

Exemplo de automação usando a nova entidade:

```yaml
alias: Campainha do portão tocou
triggers:
  - trigger: state
    entity_id: binary_sensor.portao_social_campainha_tocando
    from: "off"
    to: "on"
actions:
  - action: notify.notify
    data:
      title: Portão social
      message: A campainha foi acionada.
mode: single
```

## Configuração pela interface

1. Abra **Configurações → Dispositivos e serviços → Adicionar integração**.
2. Procure por **Hikvision Access Control**.
3. Informe o endereço do terminal, porta (normalmente `443`), usuário, senha e um
   nome para o dispositivo. Defina também o intervalo de consulta da campainha,
   entre 1 e 60 segundos; o padrão é 2 segundos.
4. Mantenha HTTPS habilitado. Para o certificado autoassinado padrão do terminal,
   desabilite **Verificar certificado HTTPS**. Habilite a verificação se o terminal
   usar um certificado confiável para o nome/endereço configurado.

Depois de adicionar o terminal, use **Reconfigurar** na entrada da integração para
alterar qualquer um desses dados, incluindo o intervalo de consulta.

As credenciais ficam na entrada de configuração protegida do Home Assistant e não
são gravadas no código, em logs de diagnóstico ou nas imagens. É possível alterar
todos os dados posteriormente pela opção **Reconfigurar** da integração; falhas de
autenticação também iniciam o fluxo de reautenticação.

## Permissões do usuário Hikvision

Crie no terminal um usuário local dedicado, com o menor privilégio possível. Ele
precisa conseguir:

- ler `/ISAPI/System/deviceInfo`;
- ler `/ISAPI/AccessControl/RemoteControl/door/capabilities` para anunciar o botão;
- ler continuamente `/ISAPI/Event/notification/alertStream`;
- ler `/ISAPI/VideoIntercom/callStatus?format=json` para detectar a campainha;
- ler `/Streaming/channels/101/picture` para a foto do visitante quando o evento
  da campainha não incluir uma imagem;
- executar `PUT /ISAPI/AccessControl/RemoteControl/door/1` para usar o botão.

Os nomes das permissões variam conforme o firmware. Habilite acesso ISAPI, leitura
de eventos e controle remoto da porta; não use a conta de administrador se um
perfil restrito puder executar essas três operações.

## Observabilidade do terminal

Após carregar a integração, o Home Assistant consulta as capacidades e cria as
entidades opcionais conforme as primeiras leituras e eventos válidos. As consultas
de diagnóstico têm ciclo próprio. Uma leitura sem permissão ou sem suporte aparece
no diagnóstico do dispositivo, e a campainha continua no intervalo configurado.

| Origem | Dados disponíveis conforme o firmware |
| --- | --- |
| `GET /ISAPI/AccessControl/AcsWorkStatus?format=json` | Contato, circuito do relé e modo da porta 1, alimentação e bateria, estados SIP e VoIP, rede, cartão de memória e contagem de cartões. Entradas, saídas de alarme e leitores aparecem no diagnóstico. Consulta a cada 30 s. |
| `GET /ISAPI/System/status` | Tempo em funcionamento, CPU, memória, temperatura interna e relógio do equipamento. Consulta a cada 60 s. |
| `GET /ISAPI/AccessControl/UserInfo/Count?format=json` | Contagem de usuários cadastrados. Consulta a cada 5 min. |
| `alertStream` | Mudanças do contato, comunicação do módulo seguro, eventos de alimentação, violação e resultado de autenticação. O sensor **Conexão ISAPI** informa o último heartbeat recebido, reconexões e, quando houver, o intervalo da última interrupção em `last_gap`. |
| Capacidades ISAPI | O diagnóstico mostra os campos anunciados em `AcsWorkStatus/capabilities`, as flags de interfone em `VideoIntercom/capabilities` e os canais anunciados por `System/TwoWayAudio/channels`. |

O sensor **Contato da porta** depende de um contato magnético instalado e de um
estado que o terminal consiga ler ou receber do módulo seguro. Um curto-circuito
ou circuito interrompido aparece no sensor de circuito, com a posição física
desconhecida. Confirme no Home Assistant a mudança de estado ao abrir e fechar o
portão. **Último comando de abertura aceito** registra o horário e a latência do
botão. Seu atributo `contact_observed_at` é preenchido se uma abertura for
observada até 60 segundos após o início daquele comando.

**Último resultado** aceita `authorized`, `denied` e `timeout` para os eventos
de autenticação classificados. **Último usuário** e a hora do último acesso
continuam ligados ao último acesso autorizado.

O campo opcional `batteryVoltage` aparece no diagnóstico como
`battery_voltage_raw`. O valor representa a bateria de backup e deve ser
calibrado antes de ser apresentado em volts. A medição de corrente, tensão de
entrada e consumo do K1T344 depende da instrumentação da alimentação. Consulte
[as especificações do K1T344](https://assets.hikvision.com/prd/normal/all/doc/m000126761/DS-K1T344MX-E1_Datasheet_20250725.pdf).

### Consultar um intervalo no histórico

Em **Ferramentas de desenvolvedor → Ações**, escolha **Consultar histórico de
acesso**, selecione o terminal e informe o período. A conta ISAPI precisa ter
permissão de pesquisa em `POST /ISAPI/AccessControl/AcsEvent?format=json`.
Depois de uma reconexão, os horários em `last_gap` podem alimentar a consulta.
A resposta contém códigos, horários, números de porta e serial dos eventos,
contagens de autenticação da amostra por resultado e método, `total_matches` quando informado pelo
terminal e `truncated` quando restarem resultados. As consultas retornam até 100
registros, sem fotos e sem republicar os registros como eventos ao vivo.

### Acompanhar a chamada SIP

**Estado da chamada ISAPI** mostra o estado informado pelo terminal, com origem
`poll` ou `stream`. **Estado SIP do terminal** e **Estado VoIP do terminal**
aparecem quando o `AcsWorkStatus` retorna os campos correspondentes. O sensor
**Etapa da chamada no servidor SIP** passa a aparecer quando o VoIP Stack informa
`received`, `connected` ou `ended` pela ação `report_sip_call`. O horário de cada
etapa fica disponível para automações. Uma etapa `connected` confirma a chamada no
servidor. Para confirmar a mídia, teste voz nos dois sentidos ou consulte as
métricas RTP/RTCP do servidor quando disponíveis.

O [exemplo de automações SIP](examples/voip_observability.yaml) usa os gatilhos
do VoIP Stack para preencher esse sensor e avisar quando a campainha toca sem
uma chamada correspondente chegar ao ramal do morador. Configure o remetente e o
destino no exemplo para identificar a chamada do portão. Para obter o ID da
entrada, selecione o terminal na ação **Registrar etapa da chamada SIP** e
alterne o editor da ação para YAML. Para texto falado no interfone, veja a
configuração do contato **Recado de entrega** abaixo.

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

Para avisar quando alguém tocar a campainha e anexar a foto mais recente, use o
evento `doorbell_ringing`. O evento só é publicado depois que a imagem anexada ou
o snapshot alternativo tiver sido processado:

```yaml
alias: Avisar visitante no portão
triggers:
  - trigger: state
    entity_id: event.portao_social_evento_de_acesso
conditions:
  - condition: template
    value_template: >-
      {{ trigger.to_state.attributes.event_type == 'doorbell_ringing' }}
actions:
  - action: notify.mobile_app_seu_celular
    data:
      title: Alguém está no portão
      message: A campainha foi acionada.
      data:
        image: /api/camera_proxy/camera.portao_social_foto_do_ultimo_visitante
mode: queued
```

### Atender pelo celular e dar um recado de entrega

A campainha e o botão **Abrir portão** usam ISAPI. Para conversar com o
visitante ou reproduzir uma frase no alto-falante do terminal, o Home Assistant
também precisa receber a ligação do interfone. A Hikvision lista SIP padrão
como recurso novo da V4.47.0 para o DS-K1T344MX-E1. Em um terminal com V4.13.0,
receber `doorbell_ringing` confirma a campainha, mas ainda é preciso verificar se
o firmware oferece **SIP padrão** para conectar a voz. [Notas do fabricante](https://assets.hikvision.com/prd/normal/all/files/202510/releasenote%5CDS-K1T344_Series_MinMoe_Terminal_V4.47.0_build250722_Release_Note.pdf)

1. No **VoIP Stack**, configure um telefone de navegador para o morador e um
   ramal SIP para o terminal. Quando o terminal oferecer SIP padrão, registre
   esse ramal no servidor do Home Assistant e configure o botão de chamada para
   discar o ramal do morador. Se já houver um tronco para o porteiro, confira
   primeiro se ele entrega a chamada ao telefone do morador.
2. No painel de atendimento, adicione o cartão do telefone, a câmera do portão
   e o botão **Abrir portão** da integração Hikvision. No aviso do Companion
   para iOS, use o caminho desse painel no campo `data.url` da notificação.
   Abra o painel, habilite o microfone e toque a campainha. O telefone deve
   passar para `ringing`. Atenda e verifique a voz nos dois sentidos.
3. Na agenda do VoIP Stack, crie um contato do tipo **Automation** chamado
   **Recado de entrega**. No editor de automações, use o exemplo abaixo e
   selecione a entidade de síntese de voz da sua instalação.

```yaml
alias: Falar recado de entrega para o visitante
triggers:
  - trigger: voip_stack.call_received
    options:
      destination: Recado de entrega
actions:
  - action: voip_stack.tts_say
    data:
      tts_entity_id: tts.google_translate_en_com
      language: pt
      message: Olá! Por favor, deixe a encomenda na garagem. Muito obrigado!
mode: parallel
```

Configure o botão **Recado de entrega** no painel para executar
`voip_stack.forward`. Selecione o telefone do morador em **Phone**, informe
`Recado de entrega` em **Destination** e `ringing` em **Expected state**.
Use o botão enquanto o telefone toca. O contato atende, transmite a frase e
encerra a chamada. Para conversar pessoalmente, use **Atender** no cartão do
telefone. Para liberar a entrada, pressione **Abrir portão**. Um sensor
magnético na folha do portão permite acompanhar a abertura física.
[Guia de chamadas e recados do VoIP Stack](https://github.com/n-IA-hane/esphome-intercom/blob/v2026.11.0/docs/AUTOMATION_DIALPLAN.md)

### Alertas de violação e perda de conexão

O sensor binário **“Violação”**, com classe `tamper`, fica `on` ao receber um
alarme de violação do terminal, leitor, módulo seguro, subcontrolador, controlador
de canal ou câmera. Cada fonte permanece ativa até seu evento de restauração;
o sensor só volta para `off` quando todas as fontes ativas forem restauradas.
Eventos de acesso, campainha e outros alarmes não limpam o tamper. O atributo
`active_sources` identifica as fontes, incluindo o canal da câmera ou número do
leitor quando informados pelo equipamento.

Ao iniciar ou recarregar a integração, o sensor começa `unknown` até receber um
evento de alarme ou restauração. Sem o `alertStream`, fica `unavailable`, mesmo
se o estado de chamada ainda puder ser consultado. A desconexão não apaga as
fontes armazenadas durante essa execução. O estado reflete eventos recebidos:
restaurações perdidas enquanto desconectado não são inferidas automaticamente.

Para alertar quando o sensor passar para `on`, adapte
[examples/tamper_sensor_alert.yaml](examples/tamper_sensor_alert.yaml). Esse
exemplo é uma alternativa ao alerta por evento abaixo: use um deles para evitar
notificações duplicadas. A transição para `on` avisa a primeira violação; para
avisar cada nova ocorrência mesmo com o sensor já ativo, use o alerta por evento.
O monitoramento da conexão permanece separado.

O arquivo [examples/security_alerts.yaml](examples/security_alerts.yaml) contém
duas automações prontas para adaptar: uma alerta imediatamente para violação do
terminal, leitor de cartão, módulo seguro ou cobertura/obstrução da câmera; a
outra alerta quando o sensor “Conexão ISAPI” permanece `offline` por 30 segundos.
Troque os identificadores das entidades e `notify.mobile_app_seu_celular` pelos
da sua instalação. O arquivo é uma lista para `automations.yaml`; no editor YAML
de uma única automação, copie apenas o conteúdo do item desejado sem o hífen
inicial. A instalação da integração não habilita essas automações automaticamente.

A perda de conexão é um indício de possível corte de cabo, falta de energia ou
falha de comunicação; o sensor acompanha o `alertStream` e não distingue essas
causas. Os 30 segundos começam depois de detectar a desconexão. Um corte sem
fechamento da conexão pode levar até o timeout de leitura de 60 segundos para
ser percebido, seguido da espera de 30 segundos da automação. O Home Assistant
e o caminho de entrega da notificação precisam continuar funcionando.

Para validar, acompanhe “Evento de acesso” e cubra a câmera em um teste
controlado: procure `camera_tamper_alarm` e, ao descobrir, a restauração. Se
nenhum evento chegar, confirme o suporte/configuração de detecção de obstrução
no terminal; o mapeamento por si só não cria um sinal que o firmware não emite.
Depois teste a desconexão de rede ou energia e confira a mudança para `offline`
e a notificação após a espera configurada.

## Solução de problemas

### Logs e depuração de eventos

Os tipos de evento que a integração ainda não reconhece são registrados como
`warning` e aparecem no log padrão do Home Assistant. Eventos reconhecidos,
heartbeats, partes multipart descartadas e o payload ISAPI decodificado ficam em
`debug` para não poluir o log durante o uso normal. Dentro dos payloads, campos
pessoais e de rede, como nome, matrícula, cartão, identificador da chamada, IP e
MAC, são substituídos por `**REDACTED**`; imagens JPEG nunca são gravadas no log.

Para habilitar temporariamente pelo Home Assistant, abra **Ferramentas do
desenvolvedor → Ações**, execute `logger.set_level` e use:

```yaml
custom_components.hikvision_access_control: debug
```

Para habilitar após cada reinicialização, adicione ao `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hikvision_access_control: debug
```

Depois reproduza o evento e abra **Configurações → Sistema → Logs**, filtrando por
`hikvision_access_control`. Ao terminar, volte o nível para `warning`, pois o modo
`debug` registra todos os payloads de evento e os heartbeats. Avisos
`InsecureRequestWarning` indicam que a verificação do certificado HTTPS foi
desabilitada; eles não representam falha do fluxo de eventos.

- **A integração não aparece:** confirme o caminho exato da pasta e reinicie o
  Home Assistant após instalar ou atualizar manualmente.
- **Credenciais inválidas:** confirme que o usuário é local, que a senha está
  correta e que as três permissões ISAPI acima estão habilitadas.
- **Erro de certificado:** desabilite a verificação apenas para um certificado
  autoassinado conhecido ou instale um certificado confiável no terminal.
- **Conexão ISAPI offline:** verifique se o Home Assistant alcança
  `https://192.168.1.100:443`. O fluxo se reconecta automaticamente com espera
  progressiva de 2 a 30 segundos.
- **Campainha tocando indisponível:** confirme que o usuário consegue ler
  `/ISAPI/VideoIntercom/callStatus?format=json`. A consulta se recupera
  automaticamente, com espera progressiva de até 30 segundos após uma falha no
  intervalo padrão; intervalos configurados acima disso são respeitados.
  Nos atributos da entidade, `polling_error` informa `invalid_auth`, `http_...`,
  `isapi_...`, `invalid_response`, `cannot_connect` ou `internal_error` e
  `poll_interval_seconds` mostra o intervalo em uso.
- **Evento aparece como “Desconhecido”:** uma entidade `event` recém-criada fica
  nesse estado até receber o primeiro evento; depois confira o atributo
  `event_type`. Em ambas as entidades, `event_code: unknown_access_event` indica
  uma combinação ainda não classificada — os atributos `major` e `sub_event`
  mostram o código recebido. `event_code: unknown_isapi_event` traz o tipo em
  `raw_event_type`. A origem também aparece entre parênteses no texto do evento.
  Heartbeats (`heartBeat` ou `videoloss` com `eventState: inactive`) são ignorados
  e não substituem o último evento. A correção não remove registros antigos do
  histórico; outros tipos ainda não classificados continuam disponíveis para
  diagnóstico.
- **Sem foto:** gere uma autenticação facial. Eventos de relé normalmente não
  carregam JPEG. Para a campainha, confirme também que o usuário ISAPI pode ler
  `/Streaming/channels/101/picture`.
- **Horário ausente:** confirme que o terminal envia `dateTime` válido e mantenha
  o fuso horário/NTP do dispositivo configurado.
- **Portão não corresponde ao relé:** use um sensor magnético; a integração não
  infere posição física a partir dos eventos 21/22.

## Publicando uma nova versão

Use o script `bump_version.sh` na branch `main`, depois de fazer commit das
alterações e descrever as mudanças na seção `## [Unreleased]` do `CHANGELOG.md`.
Não é preciso atualizar o manifesto nem fazer o push antes de executar o script.

Pré-requisitos: Git, GitHub CLI autenticado (`gh auth login`) com permissão para
publicar no repositório e Python 3.12 ou superior. O script instala as dependências
de `requirements-test.txt` automaticamente quando estiverem ausentes, usando
`uv` quando disponível, o `pip` do ambiente, `ensurepip` ou um `pip3` que permita
selecionar o Python de destino. Por exemplo:

```bash
python3.12 -m venv .venv
gh auth login
```

Visualize o resultado antes de publicar, inclusive com alterações não commitadas:

```bash
./bump_version.sh --dry-run
```

Para publicar, escolha um dos comandos:

```bash
./bump_version.sh          # patch: 0.1.4 -> 0.1.5
./bump_version.sh minor    # minor: 0.1.4 -> 0.2.0
./bump_version.sh major    # major: 0.1.4 -> 1.0.0
./bump_version.sh 0.2.3    # versão explícita, maior que a atual
```

O script usa `.venv/bin/python` quando disponível; para outro ambiente, execute
`PYTHON=/caminho/do/python ./bump_version.sh`. Ele exige a árvore de trabalho
limpa, verifica a sincronização com `origin/main` e a disponibilidade da tag,
valida JSON, compila o Python, executa Ruff e os testes. Depois atualiza o
manifesto e o changelog, cria um commit de versão e uma tag anotada, envia `main`
e a tag juntos e publica a GitHub Release com as notas de `Unreleased`.
Uma seção `Unreleased` vazia fica pronta para as próximas mudanças.

Se o push ou a publicação falhar depois da criação do commit, o script mostra
como continuar usando a mesma tag. Não execute outro bump para repetir a
publicação. `--dry-run` apenas mostra a versão e as notas; não executa os testes
nem verifica autenticação ou acesso remoto.

Não é necessário gerar ZIP: o HACS instala diretamente
`custom_components/hikvision_access_control` do código-fonte da release.

## Referências

- [Publicação de integrações no HACS](https://hacs.xyz/docs/publish/integration/)
- [Manifesto de integrações do Home Assistant](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [Imagens locais para integrações personalizadas](https://developers.home-assistant.io/docs/core/integration/brand_images/)
- [Portal oficial de guias ISAPI da Hikvision](https://tpp.hikvision.com/download/ISAPI_OTAP?type=1)
- [Eventos oficiais de controle de acesso Hikvision](https://open.hikvision.com/hardware/v2/%E7%BB%93%E6%9E%84%E4%BD%93/NET_DVR_ACS_ALARM_INFO.html)
- [Capacidades oficiais de vídeo porteiro Hikvision](https://open.hikvision.com/hardware/v2/08%E5%8D%8F%E8%AE%AE%E9%80%8F%E4%BC%A0/%E5%8F%AF%E8%A7%86%E5%AF%B9%E8%AE%B2.html)
- [Caminhos HTTP oficiais para snapshots Hikvision](https://www.hikvision.com/content/dam/hikvision/de/quick-start-guide/RTSP_und_HTTP_Pfade_fuer_Bilder_und_Videostreams_bei_IP-Kameras.pdf)

## Licença

MIT. Consulte [LICENSE](LICENSE).
