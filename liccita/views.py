from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import Assinatura
from django.db.models import Q
from .models import EmpresaCNAE, EmpresaPerfil, Licitacao
from .serializers import EmpresaCNAESerializer, EmpresaPerfilSerializer, EditalSerializer
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
        api_key = os.getenv("GEMINI_API_KEY", "AIzaSyCGFaDdMCiDropXHBByhTHozWCmZUkTzMA") 
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
        
        
class StatusDisponiveisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Vai no banco e pega apenas os nomes únicos de status, ignorando os vazios
        status_unicos = Licitacao.objects.exclude(
            status__isnull=True
        ).exclude(
            status__exact=''
        ).values_list('status', flat=True).distinct().order_by('status')
        
        return Response(list(status_unicos))
    

class UFsDisponiveisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Vai no banco e pega apenas as siglas de estados únicas (SP, MG, RJ...), ignorando vazios
        ufs_unicas = Licitacao.objects.exclude(
            local_uf__isnull=True
        ).exclude(
            local_uf__exact=''
        ).values_list('local_uf', flat=True).distinct().order_by('local_uf')
        
        return Response(list(ufs_unicas))

        
class BuscarEditaisView(generics.ListAPIView):
    serializer_class = EditalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        usuario = self.request.user
        
        # 1. Começa pegando os editais ordenados do mais recente para o mais antigo
        queryset = Licitacao.objects.all().order_by('-data_publicacao')

        # 2. Pega os parâmetros enviados pelo Vue
        empresa_id = self.request.query_params.get('empresa_id', 'todos')
        termo = self.request.query_params.get('termo', '')
        valor_min = self.request.query_params.get('valor_min')
        valor_max = self.request.query_params.get('valor_max')
        status_filtro = self.request.query_params.get('status', 'todos')
        uf_filtro = self.request.query_params.get('uf', 'todas')
        ordenacao_filtro = self.request.query_params.get('ordenacao')

        # 3. FILTRO INTELIGENTE: O Matchmaker de CNPJs
        tags_busca = []
        cnae_destaque = "Múltiplos CNAEs"

        # Pega todas as empresas que pertencem a este usuário
        empresas_do_usuario = EmpresaPerfil.objects.filter(utilizador=usuario)

        if empresas_do_usuario.exists():
            if empresa_id == 'todos':
                # Combina as tags de TODAS as empresas dele
                for emp in empresas_do_usuario:
                    if emp.palavras_chave:
                        tags_busca.extend(emp.palavras_chave)
            else:
                # Pega as tags apenas da empresa selecionada
                try:
                    emp = empresas_do_usuario.get(id=empresa_id)
                    if emp.palavras_chave:
                        tags_busca.extend(emp.palavras_chave)
                    
                    primeiro_cnae = emp.cnaes.first()
                    if primeiro_cnae:
                        cnae_destaque = primeiro_cnae.codigo
                except EmpresaPerfil.DoesNotExist:
                    pass

            # Remove tags duplicadas da lista
            tags_busca = list(set(tags_busca))

            # Se achou alguma tag, filtra o banco. Se não, não traz nada (evita trazer lixo)
            if tags_busca:
                query_tags = Q()
                for tag in tags_busca:
                    query_tags |= Q(titulo__icontains=tag) | Q(descricao__icontains=tag)
                
                queryset = queryset.filter(query_tags)
            else:
                queryset = Licitacao.objects.none() # Se o usuário não tem tags, a tela fica vazia pedindo pra ele configurar
        else:
            # Se ele não cadastrou nenhuma empresa ainda, a tela fica vazia
            queryset = Licitacao.objects.none()

        # 4. FILTRO MANUAL: Termo digitado na barra de busca superior
        if termo:
            queryset = queryset.filter(
                Q(titulo__icontains=termo) | 
                Q(descricao__icontains=termo) | 
                Q(orgao__icontains=termo)
            )

        # 5. FILTRO FINANCEIRO: Valores
        if valor_min and valor_min.isdigit():
            queryset = queryset.filter(valor_estimado__gte=float(valor_min))
        if valor_max and valor_max.isdigit():
            queryset = queryset.filter(valor_estimado__lte=float(valor_max))
        if status_filtro != 'todos':
            queryset = queryset.filter(status__icontains=status_filtro)
        if ordenacao_filtro:
            campos_permitidos = ['-data_publicacao', '-valor_estimado', 'data_abertura']
            if ordenacao_filtro in campos_permitidos:
                queryset = queryset.order_by(ordenacao_filtro)
        if uf_filtro != 'todas':
            queryset = queryset.filter(local_uf__iexact=uf_filtro)

        # 6. Resolve a query limitando a 50 resultados para não pesar a API
        editais = list(queryset[:50])

        # 7. Injeta as tags e o CNAE em tempo real para o Serializer ler
        for edital in editais:
            edital.matched_tags = tags_busca[:3] # Manda no máximo 3 tags pro card não ficar gigante
            edital.matched_cnae = cnae_destaque

        return editais