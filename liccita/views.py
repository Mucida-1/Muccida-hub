from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import io
import docx
import PyPDF2
import os
import google.generativeai as genai
import json
from accounts.models import Assinatura
from .models import EmpresaCNAE, EmpresaPerfil, Licitacao, RaioXPersonalizado, AlertaLicitacao
from .serializers import EmpresaCNAESerializer, EmpresaPerfilSerializer, EditalSerializer, MeusRaioXSerializer, AlertaLicitacaoSerializer

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

        genai.configure(api_key=settings.GEMINI_API_KEY)
        
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
    
    
class AlternarEditalSalvoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        licitacao = get_object_or_404(Licitacao, pk=pk)
        usuario = request.user
        
        # Se já estiver nos favoritos, remove. Se não estiver, adiciona.
        if usuario in licitacao.favoritos.all():
            licitacao.favoritos.remove(usuario)
            salvo = False
        else:
            licitacao.favoritos.add(usuario)
            salvo = True
            
        return Response({"sucesso": True, "salvo": salvo})
    
    
class EditaisSalvosView(generics.ListAPIView):
    serializer_class = EditalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        usuario = self.request.user
        
        # Puxa apenas as licitações onde o usuário atual está na lista de favoritos
        # Ordenadas pela data que foram publicadas
        queryset = Licitacao.objects.filter(favoritos=usuario).order_by('-data_publicacao')
        
        # Vamos limitar a 10 resultados para não pesar a Home, o ideal é ter uma página "Meus Salvos" depois
        return queryset[:10]
    

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usuario = request.user
        
        # 1. Recupera as tags do usuário (igual fizemos na busca)
        empresas = EmpresaPerfil.objects.filter(utilizador=usuario)
        tags_busca = []
        for emp in empresas:
            if emp.palavras_chave:
                tags_busca.extend(emp.palavras_chave)
        
        tags_busca = list(set(tags_busca))
        
        # Se não tem tags, retorna tudo zerado
        if not tags_busca:
            return Response({"total": 0, "novos_hoje": 0, "valor_total": 0})
            
        # 2. Filtra as licitações compatíveis
        query_tags = Q()
        for tag in tags_busca:
            query_tags |= Q(titulo__icontains=tag) | Q(descricao__icontains=tag)
            
        editais_compativeis = Licitacao.objects.filter(query_tags)
        
        # 3. Calcula as métricas
        total = editais_compativeis.count()
        
        hoje = timezone.now().date()
        novos_hoje = editais_compativeis.filter(data_publicacao=hoje).count()
        
        # Agrupa o valor estimado total (ignora os nulos)
        soma_valor = editais_compativeis.aggregate(Sum('valor_estimado'))['valor_estimado__sum'] or 0
        
        # Formata o valor para a tela (ex: 1.2M, 500K)
        if soma_valor >= 1000000:
            valor_formatado = f"R$ {soma_valor/1000000:.1f}M"
        elif soma_valor >= 1000:
            valor_formatado = f"R$ {soma_valor/1000:.1f}K"
        else:
            valor_formatado = f"R$ {soma_valor:.2f}"

        return Response({
            "total": total,
            "novos_hoje": novos_hoje,
            "alto_match": min(total, 8), # Provisório até ativarmos a IA de Match
            "valor_formatado": valor_formatado
        })
        

class AnalisarEditalIAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        licitacao = get_object_or_404(Licitacao, pk=pk)
        usuario = request.user
        is_admin = usuario.is_superuser
        
        # ==========================================
        # 0. VERIFICA SE JÁ ESTÁ SALVO (Custo ZERO)
        # ==========================================
        raiox_existente = RaioXPersonalizado.objects.filter(licitacao=licitacao, utilizador=usuario).first()
        
        if raiox_existente:
            return Response({
                "sucesso": True, 
                "resumo": raiox_existente.relatorio_markdown,
                "cobrado": False 
            })
        
        # ==========================================
        # 1. RECEBE O ARQUIVO DO VUE.JS
        # ==========================================
        arquivo_enviado = request.FILES.get('pdf_edital') 
        if not arquivo_enviado:
            return Response(
                {"erro": "Nenhum arquivo (.pdf ou .docx) foi enviado na requisição."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # ==========================================
        # 2. O CAIXA: Verifica saldo e debita
        # ==========================================
        assinatura = None
        if not is_admin:
            assinatura = usuario.assinaturas.filter(status__in=['ativo', 'pendente']).first()
            if not assinatura or (not assinatura.is_cortesia and assinatura.creditos_ia_disponiveis <= 0):
                return Response(
                    {"erro": "Saldo de Tokens IA insuficiente. Faça um upgrade."}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if not assinatura.is_cortesia:
                assinatura.creditos_ia_disponiveis -= 1
                assinatura.save()

        try:
            # ==========================================
            # 3. LÊ O ARQUIVO (PDF ou WORD)
            # ==========================================
            texto_extraido = ""
            nome_arquivo = arquivo_enviado.name.lower()

            # Garante que vamos começar a ler o arquivo do byte 0
            arquivo_enviado.seek(0)

            if nome_arquivo.endswith('.pdf'):
                leitor = PyPDF2.PdfReader(arquivo_enviado)
                for i in range(min(len(leitor.pages), 100)): 
                    texto_extraido += leitor.pages[i].extract_text() + "\n"
                    
            elif nome_arquivo.endswith('.docx') or nome_arquivo.endswith('.doc'):
                # CORREÇÃO CRUCIAL AQUI: Usando io.BytesIO para ler da memória RAM
                documento = docx.Document(io.BytesIO(arquivo_enviado.read()))
                for paragrafo in documento.paragraphs:
                    texto_extraido += paragrafo.text + "\n"
            else:
                raise ValueError("Formato de arquivo inválido. A IA aceita apenas PDF ou DOCX.")

            if len(texto_extraido.strip()) < 50:
                raise ValueError("O documento parece estar vazio ou é uma imagem sem texto digital (escaneado).")
            
            # ==========================================
            # 4. PREPARA AS TAGS DO CLIENTE
            # ==========================================
            tags_usuario = []
            empresas = EmpresaPerfil.objects.filter(utilizador=usuario)
            for emp in empresas:
                if emp.palavras_chave:
                    tags_usuario.extend(emp.palavras_chave)
            
            perfil_str = ", ".join(set(tags_usuario)) if tags_usuario else "prestação de serviços e comércio"

            # ==========================================
            # 5. O CÉREBRO (Google Gemini)
            # ==========================================
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.5-flash') 

            prompt = f"""
            Você é um consultor estratégico de licitações trabalhando para uma empresa com o seguinte perfil: {perfil_str}.
            
            Leia o texto extraído do edital oficial "{licitacao.orgao}" e gere um Raio-X profundo.
            
            REGRAS OBRIGATÓRIAS DE RESPOSTA:
            - NÃO escreva introduções como "Aqui está o raio-x" ou "Com base no edital". Vá direto para os tópicos.
            - NÃO inclua tracinhos (---) separadores iniciais.
            
            1. 🎯 **Veredito de Participação:** Vale a pena disputar? (Responda objetivamente e explique em 1 linha o porquê).
            2. ⚠️ **Exigências Cruciais:** Liste de forma direta os atestados, índices contábeis ou certificações exigidas.
            3. 💰 **Penalidades e Prazos:** Tem multas severas? O prazo de entrega é curto?
            4. 📄 **Resumo do Objeto:** O que de fato eles querem comprar (traduza do juridiquês para linguagem de mercado).
            
            TEXTO DO EDITAL:
            {texto_extraido[:150000]}
            """
            
            resposta_ia = model.generate_content(prompt)
            texto_gerado = resposta_ia.text

            # ==========================================
            # 6. SALVA O RESULTADO NO BANCO PARA SEMPRE
            # ==========================================
            RaioXPersonalizado.objects.create(
                licitacao=licitacao,
                utilizador=usuario,
                relatorio_markdown=texto_gerado
            )
            
            return Response({
                "sucesso": True, 
                "resumo": texto_gerado,
                "cobrado": True 
            })

        except Exception as e:
            # ==========================================
            # 7. ROLLBACK: Devolve o token se algo falhar
            # ==========================================
            if not is_admin and assinatura and not assinatura.is_cortesia:
                assinatura.creditos_ia_disponiveis += 1
                assinatura.save()
            
            print(f"ERRO RAIO-X PROFUNDO: {str(e)}")
            
            # Ajustei a mensagem de erro para não falar só de PDF
            mensagem_erro = str(e) if "vazio" in str(e) or "inválido" in str(e) else "Falha ao extrair texto do documento (.pdf/.docx) ou erro na IA."
            
            return Response(
                {"erro": mensagem_erro}, 
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
            

class MeusRaioXListView(generics.ListAPIView):
    serializer_class = MeusRaioXSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Traz apenas os relatórios do usuário logado, do mais recente para o mais antigo
        return RaioXPersonalizado.objects.filter(
            utilizador=self.request.user
        ).select_related('licitacao', 'licitacao__modalidade').order_by('-data_geracao')
        

class AlertaLicitacaoViewSet(viewsets.ModelViewSet):
    serializer_class = AlertaLicitacaoSerializer
    permission_classes = [IsAuthenticated]

    # Garante que o usuário só veja os próprios alertas
    def get_queryset(self):
        return AlertaLicitacao.objects.filter(usuario=self.request.user).order_by('-criado_em')

    # Na hora de criar, injeta o usuário logado automaticamente
    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    # Rota customizada para aquele botãozinho de Ligar/Desligar
    @action(detail=True, methods=['patch'])
    def toggle(self, request, pk=None):
        alerta = self.get_object()
        alerta.ativo = not alerta.ativo
        alerta.save()
        return Response({'status': 'sucesso', 'ativo': alerta.ativo})