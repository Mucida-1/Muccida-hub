from rest_framework.generics import CreateAPIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from django.shortcuts import get_object_or_404
from .serializers import CustomTokenObtainPairSerializer, CadastroSerializer
from .permissions import HasProductAccess
from .models import Produto, Assinatura


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class CadastroView(CreateAPIView):
    # AllowAny permite que qualquer pessoa acesse essa rota sem estar logada
    permission_classes = [AllowAny]
    serializer_class = CadastroSerializer
    
    
class ProdutoPerfilView(APIView):
    # O nosso segurança dinâmico assume a porta
    permission_classes = [IsAuthenticated, HasProductAccess]

    def get(self, request, produto_id):
        # 1. Busca o produto no banco pelo ID para termos os nomes sempre atualizados
        produto = get_object_or_404(Produto, id=produto_id)
        
        assinatura = None
        if not request.user.is_superuser:
            # 2. Busca a assinatura do usuário focada neste produto específico
            assinatura = request.user.assinaturas.filter(
                plano__produto__id=produto_id, 
                status='ativo'
            ).first()
            
        # 3. Monta a resposta 100% dinâmica!
        return Response({
            "mensagem": f"Acesso Autorizado! Bem-vindo ao motor do {produto.nome}.",
            "produto_nome": produto.nome, # O Vue pode usar isso para exibir no cabeçalho!
            "usuario_nome": request.user.first_name,
            "usuario_email": request.user.email,
            "is_admin": request.user.is_superuser,
            "plano_nome": assinatura.plano.nome if assinatura else "Conta Mestre (Admin)",
            "creditos_ia_restantes": assinatura.creditos_ia_disponiveis if assinatura else "Ilimitado"
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