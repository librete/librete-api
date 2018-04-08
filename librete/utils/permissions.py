from rest_framework import permissions


class IsAuthor(permissions.BasePermission):
    """
    Custom permission to only allow authors to access objects
    """

    def has_object_permission(self, request, view, obj):
        return obj.author == request.user
