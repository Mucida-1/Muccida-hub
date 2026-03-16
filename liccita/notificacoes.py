from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import requests
import json

def enviar_email_resumo(usuario, editais_para_enviar):
    # 1. Prepara as variáveis que o HTML vai usar
    contexto = {
        'nome_usuario': usuario.first_name or 'Empreendedor',
        'quantidade': len(editais_para_enviar),
        'editais': editais_para_enviar
    }
    
    # 2. Transforma o arquivo HTML em uma string gigante com os dados preenchidos
    html_mensagem = render_to_string('liccita/emails/email_alertas.html', contexto)
    texto_puro = strip_tags(html_mensagem) # Versão de fallback
    
    # 3. Dispara usando as variáveis corretas
    try:
        send_mail(
            subject=f"🚨 LicitaFácil: {len(editais_para_enviar)} oportunidades de Alto Match hoje!",
            message=texto_puro,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[usuario.email], # Puxa dinamicamente o e-mail do cliente
            html_message=html_mensagem,     # Usa o HTML bonitão renderizado
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail para {usuario.email}: {e}")
        return False
    

def enviar_whatsapp_resumo(usuario, editais_para_enviar):
    # Garante que o usuário tem telefone cadastrado
    if not hasattr(usuario, 'telefone') or not usuario.telefone:
        return False
        
    # 1. Monta a mensagem de texto com Emojis
    mensagem = f"Olá *{usuario.first_name}*! 🎯\n\nO robô da IA do LicitaFácil encontrou *{len(editais_para_enviar)} oportunidades* de Alto Match com o seu CNPJ hoje:\n\n"
    
    for edital in editais_para_enviar[:5]: # Limita a 5 no Zap para não virar um textão infinito
        mensagem += f"🔹 *{edital.orgao}*\n"
        mensagem += f"💰 Valor: R$ {edital.valor_estimado}\n"
        mensagem += f"🔗 Acesse no sistema para ler o Raio-X IA!\n\n"
        
    mensagem += "Acesse seu painel para ver a lista completa."

    # 2. Configuração da sua API de WhatsApp (Exemplo genérico)
    url_api = "https://sua-api-de-whatsapp.com/v1/messages/send"
    headers = {
        "Authorization": "Bearer SEU_TOKEN_AQUI",
        "Content-Type": "application/json"
    }
    payload = {
        "number": usuario.telefone, # Ex: "5511999999999"
        "body": mensagem
    }

    # 3. Dispara!
    try:
        resposta = requests.post(url_api, headers=headers, data=json.dumps(payload))
        return resposta.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar WhatsApp para {usuario.telefone}: {e}")
        return False