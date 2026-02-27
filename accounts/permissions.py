from rest_framework.permissions import BasePermission
from .models import Assinatura

class HasProductAccess(BasePermission):
    """
    Verifica dinamicamente se o usuário tem assinatura ativa para o Produto solicitado na URL.
    """
    message = "Acesso negado. O seu visto para este produto não está ativo ou não existe."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.user.is_superuser:
            return True
            
        # Pega o ID do produto que vem dinamicamente na URL
        produto_id = view.kwargs.get('produto_id')
        
        # Filtra usando o ID em vez do nome!
        return Assinatura.objects.filter(
            utilizador=request.user,
            plano__produto__id=produto_id,
            status='ativo'
        ).exists()