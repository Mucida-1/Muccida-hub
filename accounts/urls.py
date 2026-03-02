# accounts/urls.py
from django.urls import path
from .views import PerfilUsuarioView, MudarSenhaView, UpgradePlanoView, VitrinePlanosView

urlpatterns = [
    # Rota para ler (GET) e atualizar (PATCH/PUT) o perfil
    path('perfil/', PerfilUsuarioView.as_view(), name='perfil-usuario'),
    path('mudar-senha/', MudarSenhaView.as_view(), name='mudar-senha'),
    path('upgrade-plano/', UpgradePlanoView.as_view(), name='upgrade-plano'),
    path('produtos/<int:produto_id>/planos/', VitrinePlanosView.as_view(), name='vitrine-planos'),
]