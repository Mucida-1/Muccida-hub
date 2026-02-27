from django.urls import path
from .views import EmpresaCNAEListCreateView, EmpresaCNAEDeleteView

urlpatterns = [
    path('cnaes/', EmpresaCNAEListCreateView.as_view(), name='cnae-list-create'),
    path('cnaes/<int:pk>/', EmpresaCNAEDeleteView.as_view(), name='cnae-delete'),
]