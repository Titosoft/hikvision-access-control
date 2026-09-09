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
- Os testes automatizados cobrem parser multipart XML/JSON/JPEG fragmentado,
  autenticação Digest, reconexão do `alertStream` e encerramento do cliente.

O preparo desta versão não incluiu acesso a um equipamento físico. Portanto, a
versão publicada deve ser validada no DS-K1T344MX-E1 real antes de ser considerada
homologada para produção. Outros modelos e firmwares não estão confirmados.

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
- `eventType: changedCallStatus` com `status: ring`: chamada de vídeo porteiro;
- `5/25` a `5/28`: porta aberta, fechada, aberta de forma anormal ou por tempo
  excessivo;
- `1/0x404`, `1/0x406` e `1/0x40f`: violação do terminal, leitor ou módulo de
  segurança;
- falhas e tempos esgotados dos métodos de autenticação mais comuns.

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
- ler `/ISAPI/AccessControl/RemoteControl/door/capabilities` para anunciar o botão;
- ler continuamente `/ISAPI/Event/notification/alertStream`;
- ler `/Streaming/channels/101/picture` para a foto do visitante quando o evento
  da campainha não incluir uma imagem;
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
