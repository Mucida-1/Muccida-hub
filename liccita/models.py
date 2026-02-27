from django.db import models
from accounts.models import CustomUser
    

class EmpresaCNAE(models.Model):
    utilizador = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='cnaes')
    codigo = models.CharField(max_length=20)
    descricao = models.CharField(max_length=255)
    data_adicao = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilizador', 'codigo') 

    def __str__(self):
        return f"{self.codigo} - {self.utilizador.email}"