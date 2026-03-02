from django.urls import path
from .views import EmpresaCNAEListCreateView, EmpresaCNAEDeleteView, EmpresaPerfilListCreateView, EmpresaPerfilDetailView, GerarTagsIAView

urlpatterns = [
    path('cnaes/', EmpresaCNAEListCreateView.as_view(), name='cnae-list-create'),
    path('cnaes/<int:pk>/', EmpresaCNAEDeleteView.as_view(), name='cnae-delete'),
    path('empresas/', EmpresaPerfilListCreateView.as_view(), name='empresa-list'),
    path('empresas/<int:pk>/', EmpresaPerfilDetailView.as_view(), name='empresa-detail'),
    path('gerar-tags/', GerarTagsIAView.as_view(), name='gerar-tags'),
]