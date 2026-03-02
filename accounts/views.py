from rest_framework import generics
from rest_framework.generics import CreateAPIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from .serializers import CustomTokenObtainPairSerializer, CadastroSerializer, PerfilUsuarioSerializer, MudarSenhaSerializer
from .permissions import HasProductAccess
from .models import Produto, Assinatura, Fatura, Plano


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class CadastroView(CreateAPIView):
    # AllowAny permite que qualquer pessoa acesse essa rota sem estar logada
    permission_classes = [AllowAny]
    serializer_class = CadastroSerializer
    
    
class ProdutoPerfilView(APIView):
    permission_classes = [IsAuthenticated, HasProductAccess]

    def get(self, request, produto_id):
        produto = get_object_or_404(Produto, id=produto_id)
        
        assinatura = None
        faturas_data = []
        
        if not request.user.is_superuser:
            # Busca a assinatura ativa
            assinatura = request.user.assinaturas.filter(
                plano__produto__id=produto_id, 
                status__in=['ativo', 'pendente', 'atrasado'] # Pega a assinatura mesmo se estiver devendo
            ).first()
            
            # Se achou a assinatura, monta o histórico das últimas 10 faturas
            if assinatura:
                faturas = assinatura.faturas.all()[:10]
                for fatura in faturas:
                    faturas_data.append({
                        "id": f"FAT-{fatura.id:04d}",
                        "data": fatura.data_vencimento.strftime("%d/%m/%Y") if fatura.data_vencimento else "--",
                        "valor": f"R$ {fatura.valor}",
                        "metodo": fatura.metodo_pagamento or "Pendente",
                        "status": fatura.get_status_display(), # Pega o texto bonito (ex: "Pago")
                        "link": fatura.link_nota_fiscal or fatura.link_pagamento or "#"
                    })

        # --- REGRAS DE EXCEÇÃO (MASTER E CORTESIA) ---
        is_admin = request.user.is_superuser
        is_vip = assinatura.is_cortesia if assinatura else False

        # Monta a super resposta dinâmica!
        return Response({
            "mensagem": f"Acesso Autorizado! Bem-vindo ao motor do {produto.nome}.",
            "produto_nome": produto.nome,
            "usuario_nome": request.user.first_name,
            "usuario_email": request.user.email,
            "usuario_telefone": getattr(request.user, 'telefone', ''),
            "is_admin": is_admin,
            
            # --- DADOS DA ASSINATURA ---
            "plano_nome": "Conta Mestre (Admin)" if is_admin else (assinatura.plano.nome if assinatura else "Conta Gratuita"),
            "assinatura_status": "ativo" if is_admin or is_vip else (assinatura.status if assinatura else "ativo"),
            "assinatura_ciclo": "Vitalício" if is_admin else (assinatura.ciclo.capitalize() if getattr(assinatura, 'ciclo', None) else "Mensal"),
            "is_cortesia": is_vip, # 👈 O Vue precisa saber se é VIP
            "data_renovacao": assinatura.data_renovacao.strftime("%d/%m/%Y") if getattr(assinatura, 'data_renovacao', None) else None,
            
            # --- LIMITES DO PLANO (Admin tem 9999) ---
            "limite_cnpjs": 9999 if is_admin else (assinatura.plano.limite_cnpjs if assinatura else 1),
            "limite_cnaes": 9999 if is_admin else (assinatura.plano.limite_cnaes if assinatura else 3),
            "limite_tokens_ia": 9999 if is_admin else (assinatura.plano.limite_creditos_ia if assinatura else 0),
            "tokens_ia_disponiveis": 9999 if is_admin else (assinatura.creditos_ia_disponiveis if assinatura else 0),
            
            # --- FATURAS ---
            "faturas": faturas_data
        })


class LogoutView(APIView):
    # O usuário precisa estar logado para poder deslogar
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Pega o refresh token que o Vue vai enviar no corpo da requisição
            refresh_token = request.data["refresh"]
            
            # Instancia o token e o envia para a Lista Negra
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            return Response({"mensagem": "Logout realizado com sucesso no servidor."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"erro": "Token inválido ou já expirado."}, status=status.HTTP_400_BAD_REQUEST)
        
    
class PerfilUsuarioView(generics.RetrieveUpdateAPIView):
    serializer_class = PerfilUsuarioSerializer
    permission_classes = [IsAuthenticated]

    # A blindagem: O objeto a ser atualizado é SEMPRE o usuário logado no token
    def get_object(self):
        return self.request.user
    
    
class MudarSenhaView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        # Passamos o request no contexto para o serializer conseguir acessar o request.user
        serializer = MudarSenhaSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            user = request.user
            nova_senha = serializer.validated_data['nova']
            
            # A MÁGICA: set_password aplica o hash de segurança (Argon2/PBKDF2) antes de salvar
            user.set_password(nova_senha)
            user.save()
            
            return Response({"mensagem": "Senha alterada com sucesso."}, status=status.HTTP_200_OK)
            
        # Se a senha atual estiver errada, o is_valid() falha e cai aqui devolvendo o erro
        # Pegamos o primeiro erro do dicionário para jogar na tela do Vue
        primeiro_erro = list(serializer.errors.values())[0][0]
        return Response({"erro": primeiro_erro}, status=status.HTTP_400_BAD_REQUEST)
    

class UpgradePlanoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plano_id = request.data.get('plano_id') # 👈 Pega o ID
        is_anual = request.data.get('is_anual', False)
        
        # 1. Busca direto pela Chave Primária (muito mais seguro e rápido)
        plano_desejado = get_object_or_404(Plano, id=plano_id, produto_id=1)
        
        user = request.user
        
        assinatura, created = Assinatura.objects.get_or_create(
            utilizador=user,
            plano__produto_id=1,
            defaults={'plano': plano_desejado, 'status': 'ativo', 'ciclo': 'anual' if is_anual else 'mensal'}
        )
        
        if not created:
            assinatura.plano = plano_desejado
            assinatura.ciclo = 'anual' if is_anual else 'mensal'
            assinatura.status = 'ativo'
        
        assinatura.creditos_ia_disponiveis = plano_desejado.limite_creditos_ia
        dias_validade = 365 if is_anual else 30
        assinatura.data_renovacao = timezone.now() + timedelta(days=dias_validade)
        assinatura.save()

        valor_cobrado = plano_desejado.preco_anual if is_anual else plano_desejado.preco_mensal
        
        Fatura.objects.create(
            assinatura=assinatura,
            valor=valor_cobrado,
            status='pago', 
            metodo_pagamento='Cartão de Crédito',
            data_vencimento=timezone.now().date(),
            data_pagamento=timezone.now()
        )
        
        return Response({
            "mensagem": f"Upgrade para o plano {plano_desejado.nome} realizado!"
        }, status=status.HTTP_200_OK)
        
        
        
class VitrinePlanosView(APIView):
    permission_classes = [AllowAny] # Liberado para a Landing Page ver!

    def get(self, request, produto_id):
        # Busca os planos ativos daquele produto e já traz na ordem correta
        planos_db = Plano.objects.filter(produto_id=produto_id)
        
        dados = []
        for p in planos_db:
            dados.append({
                "id": p.id,
                "nome": p.nome,
                "descricao": p.descricao or "",
                # Transforma 29.90 em "29,90" pro Vue só fatiar e mostrar
                "precoMensal": f"{p.preco_mensal:.2f}".replace('.', ','),
                "precoAnual": f"{p.preco_anual:.2f}".replace('.', ','),
                "destaque": p.destaque,
                "cta": p.cta,
                "recursos": p.recursos # Já devolve a lista de dicionários perfeitamente formatada
            })
            
        return Response(dados)