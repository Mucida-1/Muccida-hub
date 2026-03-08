from celery import shared_task
from .models import FonteLicitacao
from .collectors import get_collector_strategy
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