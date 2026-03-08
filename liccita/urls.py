from django.urls import path
from .views import EmpresaCNAEListCreateView, EmpresaCNAEDeleteView, EmpresaPerfilListCreateView, EmpresaPerfilDetailView, GerarTagsIAView, BuscarEditaisView, StatusDisponiveisView, UFsDisponiveisView

urlpatterns = [
    path('cnaes/', EmpresaCNAEListCreateView.as_view(), name='cnae-list-create'),
    path('cnaes/<int:pk>/', EmpresaCNAEDeleteView.as_view(), name='cnae-delete'),
    path('empresas/', EmpresaPerfilListCreateView.as_view(), name='empresa-list'),
    path('empresas/<int:pk>/', EmpresaPerfilDetailView.as_view(), name='empresa-detail'),
    path('gerar-tags/', GerarTagsIAView.as_view(), name='gerar-tags'),
    path('buscar-editais/', BuscarEditaisView.as_view(), name='buscar-editais'),
    path('status-disponiveis/', StatusDisponiveisView.as_view(), name='status-disponiveis'),
    path('ufs-disponiveis/', UFsDisponiveisView.as_view(), name='ufs-disponiveis'),
]