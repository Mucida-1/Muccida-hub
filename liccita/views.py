from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from accounts.models import Assinatura
from .models import EmpresaCNAE
from .serializers import EmpresaCNAESerializer

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