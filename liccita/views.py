from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import Assinatura
from .models import EmpresaCNAE, EmpresaPerfil
from .serializers import EmpresaCNAESerializer, EmpresaPerfilSerializer
import os
import google.generativeai as genai
import json

class EmpresaCNAEListCreateView(generics.ListCreateAPIView):
    serializer_class = EmpresaCNAESerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EmpresaCNAE.objects.filter(utilizador=self.request.user).order_by('-data_adicao')

    def perform_create(self, serializer):
        user = self.request.user
        
        if not user.is_superuser:
            assinatura = Assinatura.objects.filter(
                utilizador=user, plano__produto_id=1, status='ativo'
            ).first()

            if not assinatura:
                raise ValidationError({"erro": "Você não tem uma assinatura ativa do FJL Liccita."})

            limite = assinatura.plano.limite_cnaes
            cadastrados = EmpresaCNAE.objects.filter(utilizador=user).count()

            if cadastrados >= limite:
                raise ValidationError({
                    "erro": f"Limite atingido! Seu plano atual permite no máximo {limite} CNAEs.",
                    "necessita_upgrade": True
                })

        serializer.save(utilizador=user)

class EmpresaCNAEDeleteView(generics.DestroyAPIView):
    serializer_class = EmpresaCNAESerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EmpresaCNAE.objects.filter(utilizador=self.request.user)
    

class EmpresaPerfilListCreateView(generics.ListCreateAPIView):
    serializer_class = EmpresaPerfilSerializer
    permission_classes = [IsAuthenticated]

    # Lista apenas as empresas do usuário logado
    def get_queryset(self):
        return EmpresaPerfil.objects.filter(utilizador=self.request.user)


class EmpresaPerfilDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmpresaPerfilSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EmpresaPerfil.objects.filter(utilizador=self.request.user)
    
    
class GerarTagsIAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        descricao = request.data.get('descricao', '')
        cnaes = request.data.get('cnaes', [])

        if len(descricao) < 10:
            return Response({'erro': 'Descrição muito curta.'}, status=400)

        # ATENÇÃO: Coloque sua chave de API nas variáveis de ambiente do seu .env depois!
        api_key = os.getenv("GEMINI_API_KEY", "AIzaSyCrIDF4oRm8UcF6R8dTPmAUb-BeJ5wkp54") 
        genai.configure(api_key=api_key)
        
        # O modelo Flash é o mais rápido e barato para textos curtos
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""
        Atue como um especialista em licitações públicas no Brasil.
        Vou te passar a descrição do negócio de uma empresa e seus CNAEs (códigos de atividade).
        Sua tarefa é gerar de 5 a 10 palavras-chave (tags) curtas, diretas e altamente relevantes que representem os produtos/serviços que essa empresa pode vender para o governo.
        As tags devem ser otimizadas para dar "match" em buscas dentro de editais do Diário Oficial.

        Descrição da Empresa: {descricao}
        CNAEs Vinculados: {', '.join(cnaes)}

        Responda APENAS com um array JSON válido contendo as strings das tags, sem markdown, sem crases e sem texto adicional. Exemplo: ["Vue.js", "Desenvolvimento Web", "SaaS"]
        """

        try:
            resposta_ia = model.generate_content(prompt)
            texto_limpo = resposta_ia.text.replace('```json', '').replace('```', '').strip()
            tags = json.loads(texto_limpo)
            
            return Response({'tags': tags})
        except Exception as e:
            print(e)
            return Response({'erro': 'Falha ao gerar tags na IA. Tente novamente.'}, status=500)