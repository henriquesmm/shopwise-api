from rest_framework.permissions import BasePermission, SAFE_METHODS


class LeituraPublicaEscritaAdmin(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff


class LeituraPublicaEscritaAutenticada(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.is_authenticated


class LeituraPublicaCadastroSupermercado(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        usuario = request.user
        return usuario.is_authenticated and (
            usuario.is_staff or usuario.supermercados.exists()
        )
