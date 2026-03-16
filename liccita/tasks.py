from celery import shared_task
from django.db.models import Q
from datetime import date, timedelta
import google.generativeai as genai
from django.conf import settings
from .models import FonteLicitacao, EmpresaPerfil, AlertaLicitacao, Licitacao, EditalEnviado
from .collectors import get_collector_strategy
from .notificacoes import enviar_email_resumo, enviar_whatsapp_resumo
import logging

logger = logging.getLogger(__name__)

@shared_task(name="coletar_todas_as_licitacoes")
def coletar_todas_as_licitacoes_task():
    fontes_ids = FonteLicitacao.objects.filter(ativo=True).values_list('id', flat=True)
    for fonte_id in fontes_ids:
        processar_fonte_task.delay(fonte_id)


@shared_task(name="processar_fonte_especifica")
def processar_fonte_task(fonte_id: int):
    try:
        fonte = FonteLicitacao.objects.get(id=fonte_id, ativo=True)
    except FonteLicitacao.DoesNotExist:
        logger.error(f"Fonte com id {fonte_id} não encontrada ou inativa.")
        return

    CollectorClass = get_collector_strategy(fonte.tipo)

    if not CollectorClass:
        logger.error(f"Estratégia de coleta não encontrada para o tipo: {fonte.tipo}")
        return
    
    try:
        coletor = CollectorClass(fonte=fonte)
        coletor.run()
        logger.info(f"Coleta finalizada com sucesso para a fonte: {fonte.nome}")
    except Exception as e:
        logger.exception(f"Erro ao executar a coleta para a fonte {fonte.nome}: {e}")
        raise e
    

@shared_task(name="disparar_alertas_inteligentes")
def disparar_alertas_inteligentes():
    alertas_ativos = AlertaLicitacao.objects.filter(ativo=True)
    ontem = date.today() - timedelta(days=1)
    
    for alerta in alertas_ativos:
        usuario = alerta.usuario
        
        # 1. USA A SUA LÓGICA DA VIEW PARA O PRÉ-FILTRO RÁPIDO
        queryset = Licitacao.objects.filter(data_publicacao__gte=ontem)
        
        if alerta.valor_minimo > 0:
            queryset = queryset.filter(valor_estimado__gte=alerta.valor_minimo)
            
        if alerta.ufs:
            lista_ufs = [uf.strip() for uf in alerta.ufs.split(',')]
            queryset = queryset.filter(local_uf__in=lista_ufs)

        # 2. PUXA AS TAGS DO CNAE DO USUÁRIO
        tags_busca = []
        empresas = EmpresaPerfil.objects.filter(utilizador=usuario)
        for emp in empresas:
            if emp.palavras_chave:
                tags_busca.extend(emp.palavras_chave)
        
        if not tags_busca:
            continue # Se o usuário não configurou a empresa, pula ele
            
        query_tags = Q()
        for tag in set(tags_busca):
            query_tags |= Q(titulo__icontains=tag) | Q(descricao__icontains=tag)
            
        queryset_com_tags = queryset.filter(query_tags)
        editais_ja_enviados = EditalEnviado.objects.filter(usuario=usuario).values_list('licitacao_id', flat=True)
        editais_pre_filtrados = queryset_com_tags.exclude(id__in=editais_ja_enviados)[:20]
        
        if not editais_pre_filtrados:
            continue

        # 3. A MÁGICA DA IA (Se o cliente ativou o Alto Match)
        editais_para_enviar = []
        perfil_str = ", ".join(set(tags_busca))
        
        if alerta.apenas_alto_match:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            for edital in editais_pre_filtrados:
                prompt = f"""
                    Você é um Consultor Estratégico Sênior de Licitações Públicas.
                    Sua missão é cruzar o perfil de uma empresa com o objeto de um edital e definir a chance de sucesso (Match).

                    PERFIL DA EMPRESA (CNAEs e Tags):
                    {perfil_str}

                    DADOS DO EDITAL:
                    Órgão: {edital.orgao}
                    Objeto: {edital.titulo}
                    Descrição: {edital.descricao}

                    REGRAS DE AVALIAÇÃO:
                    1. Penalize (nota baixa) se o edital exigir fornecimento de materiais/serviços que fogem totalmente do perfil da empresa.
                    2. Recompense (nota alta) se as palavras centrais do objeto forem sinônimos diretos ou a atividade fim do perfil.
                    3. Ignore exigências genéricas (ex: "contratação de empresa especializada") e foque no núcleo do que está sendo comprado.

                    SAÍDA OBRIGATÓRIA:
                    Forneça ESTRITAMENTE um número inteiro de 0 a 100. Não escreva nenhuma palavra, texto ou símbolo adicional. Apenas o número.
                    """
                    
                try:
                    resposta = model.generate_content(prompt)
                    nota = int(resposta.text.strip())
                    
                    if nota >= 80: # Só envia se for altíssima compatibilidade
                        editais_para_enviar.append(edital)
                except:
                    pass # Se a IA falhar em um, apenas ignora e segue a vida
        else:
            # Se ele não ativou o filtro de IA, envia todos os do pré-filtro
            editais_para_enviar = list(editais_pre_filtrados)

        # 4. DISPARO FINAL
        if editais_para_enviar:
            sucesso = False
            
            # Chama o carteiro correspondente
            if alerta.canal == 'email':
                sucesso = enviar_email_resumo(usuario, editais_para_enviar)
            elif alerta.canal == 'whatsapp':
                sucesso = enviar_whatsapp_resumo(usuario, editais_para_enviar)
            
            # Se o carteiro entregou, nós salvamos na Lista Negra para não mandar amanhã de novo
            if sucesso:
                registros_memoria = [
                    EditalEnviado(usuario=usuario, licitacao=edital) 
                    for edital in editais_para_enviar
                ]
                EditalEnviado.objects.bulk_create(registros_memoria)