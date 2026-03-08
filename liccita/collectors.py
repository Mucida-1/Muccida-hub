import json
import hashlib
import requests
import logging
from datetime import date
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import FonteLicitacao, Licitacao, Modalidade, ModalidadeAlias
from .functions import get_nested_value

logger = logging.getLogger(__name__)

class BaseCollector:
    registry = {}
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        tipo_coleta = getattr(cls, 'tipo_coleta', None)
        if tipo_coleta:
            cls.registry[tipo_coleta] = cls
            print(f"Coletor '{cls.__name__}' registrado para o tipo '{tipo_coleta}'.")

    def __init__(self, fonte: FonteLicitacao):
        self.fonte = fonte
        self.novos_itens = 0
        self.itens_atualizados = 0

    def run(self):
        itens_api = self.fetch() 
        if itens_api:
            itens_normalizados = self.parse_and_normalize(itens_api)
            self.store(itens_normalizados)

    def fetch(self):
        raise NotImplementedError("O método 'fetch' deve ser implementado.")

    def parse_and_normalize(self, dados_brutos):
        raise NotImplementedError("O método 'parse_and_normalize' deve ser implementado.")

    def store(self, itens: list):
        for item in itens:
            # Pega o raw payload se existir, senão usa o dict vazio
            raw_payload = item.pop('raw_payload', {})
            
            raw_data = json.dumps({
                "source": self.fonte.nome,
                "source_id": item.get("source_id"),
                "titulo": item.get("titulo"),
                "orgao": item.get("orgao"),
                "data_publicacao": str(item.get("data_publicacao")),
            }, sort_keys=True)
            fingerprint = hashlib.sha256(raw_data.encode("utf-8")).hexdigest()

            obj, created = Licitacao.objects.update_or_create(
                fingerprint=fingerprint,
                defaults=item
            )

            if created:
                self.novos_itens += 1
            else:
                self.itens_atualizados += 1
        
        print(f"Fonte: {self.fonte.nome} | Novos: {self.novos_itens} | Atualizados: {self.itens_atualizados}")



# ===================================================================
# COLETORES ESPECIALISTAS
# ===================================================================
class ApiCollector(BaseCollector):
    tipo_coleta = "api"
    
    def fetch(self):
        """
        Busca os dados da API usando o endpoint e parâmetros confirmados pelo servidor.
        """
        modalidades = self.fonte.modalidades_a_coletar.all()
        if not modalidades:
            print(f"AVISO: Nenhuma modalidade configurada para a fonte {self.fonte.nome}. A coleta pode falhar.")
            return None

        todos_os_itens_api = []
        hoje_str = date.today().strftime('%Y%m%d')
        
        TAMANHO_PAGINA = 50
        print(f"Iniciando coleta para {len(modalidades)} modalidade(s)...")
        
        for modalidade in modalidades:
            print(f"Buscando modalidade: {modalidade.nome} (Cód: {modalidade.codigo})")
            pagina_atual = 1
            while True:
                print(f"  > Buscando página: {pagina_atual}")
                params = {
                    'pagina': pagina_atual,
                    'tamanhoPagina': TAMANHO_PAGINA,
                    'dataInicial': hoje_str,
                    'dataFinal': hoje_str,
                    'codigoModalidadeContratacao': modalidade.codigo,
                }

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
                }

                try:
                    response = requests.get(self.fonte.url, params=params, headers=headers, timeout=30)
                    if response.status_code == 204:
                        # 204 No Content (Sem dados para este dia/modalidade/página)
                        # print(f"    > Fim (204) na página {pagina_atual}.") # (Opcional)
                        break
                    
                    response.raise_for_status()

                    dados_da_pagina = response.json()
                    # Usamos o método auxiliar para extrair a lista de itens
                    itens_desta_pagina = self.get_itens_from_response(dados_da_pagina)

                    if not itens_desta_pagina:
                        # Se a API retornar uma lista vazia, saímos do loop de paginação
                        print(f"  > Fim da paginação para esta modalidade (página {pagina_atual} vazia).")
                        break # Sai do 'while True'

                    print(f"  > Encontrados {len(itens_desta_pagina)} itens na página {pagina_atual}.")
                    todos_os_itens_api.extend(itens_desta_pagina)

                    # Otimização: Se o número de itens for menor que o tamanho da página,
                    # sabemos que é a última página e não precisamos fazer mais uma chamada.
                    if len(itens_desta_pagina) < TAMANHO_PAGINA:
                        print(f"  > Esta era a última página para a modalidade.")
                        break # Sai do 'while True'

                    # Prepara para a próxima iteração
                    pagina_atual += 1

                except requests.RequestException as e:
                    print(f"  > Erro ao buscar página {pagina_atual} para a modalidade {modalidade.nome}: {e}")
                    # Se uma página der erro, paramos a paginação para esta modalidade
                    # e continuamos para a próxima.
                    break # Sai do 'while True'

        # O método fetch agora retorna uma lista de itens, e não o JSON bruto
        return todos_os_itens_api
    
    def get_itens_from_response(self, dados_brutos):
        """
        Método auxiliar para extrair a lista de itens da resposta da API.
        """
        if not dados_brutos:
            return []
        config = self.fonte.campos_disponiveis
        caminho_itens = config.get("caminho_itens")
        return get_nested_value(dados_brutos, caminho_itens) or []

    def parse_and_normalize(self, itens_api: list):
        """
        Traduz os dados da API e padroniza as modalidades,
        criando aliases pendentes para mapeamento manual.
        """
        if not itens_api:
            return []

        config = self.fonte.campos_disponiveis
        mapeamento = config.get("mapeamento")
        campo_api_modalidade = mapeamento.get('modalidade')

        itens_normalizados = []

        for item_api in itens_api:
            item_normalizado = { "source": self.fonte.nome, "raw_payload": item_api }
            
            # --- Loop 1: Mapeamento Básico (OK) ---
            for campo_modelo, campo_api in mapeamento.items():
                if campo_modelo == 'modalidade':
                    continue 
                valor = get_nested_value(item_api, campo_api)
                if "data" in campo_modelo and valor and isinstance(valor, str):
                    try:
                        dt_naive = parse_datetime(valor)
                        if dt_naive:
                            valor = timezone.make_aware(dt_naive)
                    except (ValueError, TypeError):
                        valor = None
                item_normalizado[campo_modelo] = valor
            
            
            # --- LÓGICA DE PADRONIZAÇÃO (COM AUTO-CRIAÇÃO DE ALIAS) ---
            
            modalidade_limpa_encontrada = None
            nome_sujo_modalidade_bruto = get_nested_value(item_api, campo_api_modalidade)
            
            # Garante que temos um texto para processar
            if nome_sujo_modalidade_bruto and isinstance(nome_sujo_modalidade_bruto, str):
                
                # Limpa espaços em branco
                nome_sujo_modalidade = nome_sujo_modalidade_bruto.strip()
                
                # Se a string não estiver vazia após a limpeza
                if nome_sujo_modalidade:
                    try:
                        # ETAPA 1: Tenta encontrar no Tradutor (Alias)
                        # Usamos select_related para otimizar a busca do FK
                        alias_encontrado = ModalidadeAlias.objects.select_related('modalidade_padrao').get(alias__iexact=nome_sujo_modalidade)
                        
                        # O alias existe. Ele pode ter uma modalidade (mapeada) ou ser None (pendente)
                        modalidade_limpa_encontrada = alias_encontrado.modalidade_padrao
                        
                    except ModalidadeAlias.DoesNotExist:
                        try:
                            # ETAPA 2: Se não é um alias, talvez seja um nome "limpo" direto
                            modalidade_limpa_encontrada = Modalidade.objects.get(nome__iexact=nome_sujo_modalidade)
                            
                            # (Opcional) Se é um match direto, podemos auto-criar o alias
                            # para otimizar a próxima busca, já apontando para o correto.
                            ModalidadeAlias.objects.create(
                                alias=nome_sujo_modalidade, 
                                modalidade_padrao=modalidade_limpa_encontrada
                            )
                            
                        except Modalidade.DoesNotExist:
                            # ETAPA 3: Falhou nos dois. É um nome 100% novo.
                            # CRIA AUTOMATICAMENTE O ALIAS PENDENTE (Sua sugestão!)
                            
                            # get_or_create é seguro contra repetições (race conditions)
                            alias_obj, created = ModalidadeAlias.objects.get_or_create(
                                alias__iexact=nome_sujo_modalidade,
                                defaults={
                                    'alias': nome_sujo_modalidade, # Salva o nome exato (após strip)
                                    'modalidade_padrao': None # Fica PENDENTE para você mapear
                                }
                            )
                            
                            if created:
                                # Loga APENAS UMA VEZ, na criação.
                                logger.info(
                                    f"Novo alias de modalidade descoberto e salvo como PENDENTE: '{nome_sujo_modalidade}'."
                                    f" Mapeamento manual necessário no Admin."
                                )
                            
                            # Como acabou de ser criado, a modalidade ainda é Nula
                            modalidade_limpa_encontrada = None
            

            url_final = item_normalizado.get('edital_url')

            # B. Fallback 1: Tenta o link do processo eletrônico (se existir na API)
            if not url_final:
                url_final = get_nested_value(item_api, 'linkProcessoEletronico')

            # C. Fallback 2: Constrói a URL baseada no template da Fonte (GENÉRICO)
            if not url_final:
                # Busca o template no JSON de configuração da fonte
                url_template = config.get("url_template")
                
                if url_template:
                    try:
                        # A mágica do Python: .format(**dict)
                        # Isso pega o template "site.com/{id}" e substitui {id} pelo valor do item_api['id']
                        # Nota: Isso funciona para chaves de primeiro nível. 
                        # Se precisar de chaves aninhadas, a lógica seria um pouco mais complexa,
                        # mas para o PNCP, 'numeroControlePNCP' e 'anoCompra' estão na raiz do item.
                        url_final = url_template.format(**item_api)
                    except KeyError:
                        # Se o template pedir um campo que não existe no item, não quebra, só ignora
                        logger.warning(f"Falha ao gerar URL pelo template para a fonte {self.fonte.nome}. Chave faltando no payload.")
                        url_final = None
                        
                        
                        
            # Atribui o resultado final (seja um objeto Modalidade ou None)
            item_normalizado['modalidade'] = modalidade_limpa_encontrada
            item_normalizado['local_cidade'] = get_nested_value(item_api, 'unidadeOrgao.municipioNome')
            item_normalizado['local_uf'] = get_nested_value(item_api, 'unidadeOrgao.ufSigla')
            item_normalizado['modo_disputa'] = get_nested_value(item_api, 'modoDisputaNome')
            item_normalizado['srp'] = get_nested_value(item_api, 'srp')
            item_normalizado['edital_url'] = url_final
            
            itens_normalizados.append(item_normalizado)
        
        return itens_normalizados
    
    
def get_collector_strategy(tipo: str):
    return BaseCollector.registry.get(tipo)