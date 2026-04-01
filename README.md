# Tarifas de Energia Brasil - Integração para Home Assistant

Esta integração permite consultar e monitorar as tarifas de energia elétrica vigentes no Brasil, incluindo bandeiras tarifárias, diretamente no Home Assistant. Os dados são obtidos da ANEEL e atualizados automaticamente.

## Funcionalidades

- Consulta automática das tarifas de energia e bandeiras tarifárias.
- Sensores para exibir a tarifa vigente, a tarifa com impostos estimados e a bandeira atual.
- Atualização diária dos dados.
- Armazenamento local dos dados para histórico.
- Configuração simples via interface do Home Assistant.
- Edição da configuração pela tela de Opções da integração (sem precisar remover/reinstalar).
- Cálculo estimado de impostos por UF (ICMS + PIS/COFINS).

## Screenshots

### Adicionando a Integração
![Adicionar Integração](/docs/images/001-Adicionar_Integracao.png "Adicionar Integração")

### Tela de Configuração: Selecionando a Concessionária
![Adicionar Integração](/docs/images/002-Selecionar_Concessionaria.png "Adicionar Integração")

### Tela da Integração: Lista de Serviços
![Adicionar Integração](/docs/images/003-Lista_de_Servicos.png "Adicionar Integração")


### Tela do Serviço: Entidades
![Adicionar Integração](/docs/images/004-Dispositivo.png "Adicionar Integração")

### Painel Energia: Vinculando entidade da tarifa ao dispositivo
![Adicionar Integração](/docs/images/005-Vincular_Tarifa_Energia.png "Adicionar Integração")

## Instalação

### Via HACS
1. Abra o HACS em seu Home Assistant
2. Clique nos três pontos no canto superior direito e selecione *Custom repositories*
3. Selecione o tipo *Integration* no campo *Type* e adicione a URL do repositório: https://github.com/diogocaseca/ha_tarifas_energia_brasil
4. Busque por "*Tarifas de Energia Brasil*" e instale a integração
5. Reinicie o Home Assistant

### Instalação Manual
1. Faça o download do repositório como arquivo ZIP e faça a extração em um diretório local.
2. Copie a pasta `tarifas_energia_brasil` para o diretório `custom_components` do seu Home Assistant.
3. Reinicie o Home Assistant.
4. Adicione a integração "Tarifas Energia Brasil" via interface de configurações.

## Configuração

A configuração é feita via UI (Configurações > Integrações > Adicionar integração). Não é necessário editar arquivos YAML manualmente.

Durante a configuração inicial, é obrigatório informar:

- Concessionária
- Estado (UF)

Após configurar, é possível editar esses campos em:

- Configurações > Integrações > Tarifas de Energia Brasil > Opções

## Sensores Criados

- **sensor.tarifa_vigente**: Valor da tarifa vigente (R$/kWh).
- **sensor.tarifa_com_impostos_estimados**: Valor da tarifa estimada com impostos para a UF configurada (R$/kWh).
- **sensor.bandeira_vigente**: Bandeira tarifária atual (Verde, Amarela, Vermelha, etc).

Os sensores de tarifa também expõem atributos de impostos estimados:

- estado
- icms_estimado
- pis_cofins_estimado
- carga_tributaria_total_estimada

## Atualização dos Dados

Os dados são atualizados automaticamente uma vez por dia. O intervalo pode ser ajustado no código, se necessário.

## Pontos de Atenção

- A integração depende da disponibilidade da API da ANEEL.
- Os valores de impostos são estimativas para uso informativo e podem divergir da cobrança real da distribuidora.
- Em caso de falha temporária na atualização externa, a integração pode manter o último dado válido disponível.

## Contribuição

Sinta-se à vontade para abrir issues ou pull requests para sugerir melhorias ou reportar problemas.

## Licença

Este projeto está licenciado sob a [GNU General Public License v3.0 (GPL-3.0)](https://www.gnu.org/licenses/gpl-3.0.html).  
Você pode usar, modificar e distribuir este software, desde que qualquer trabalho derivado também seja distribuído sob a mesma licença

<!--
## Apoie o Projeto
Se você achou este ou outros projetos úteis e gostaria de apoiá-los, há várias maneiras.


[!["Me Pagua um Café"](/docs/images/me-paga-um-cafe.png "Me Paga um Café")](https://mepagaumcafe.com.br/vodikus/)


[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/vodikus)-->

## Seal

![Selo Vibe Coding by Copilot](/docs/images/selo_gemini.png "Selo Vibe Coding by Copilot")